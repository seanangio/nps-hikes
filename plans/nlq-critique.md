Here's my critique of the NLQ endpoint:

Strengths
1. Clean architectural separation of concerns

The five-file decomposition (ollama_client.py, park_lookup.py, prompt.py, parser.py, endpoint in main.py) gives each file a single, testable responsibility. The LLM is strictly a parameter extractor — it never touches the database or generates SQL. This is a fundamentally sound design choice that limits the blast radius of LLM mistakes to parameter values, not arbitrary query execution.

2. Belt-and-suspenders reliability pattern

The system works at two levels: teach the LLM the right answer (park lookup table in the prompt, explicit min/max rules), then fix it deterministically when it gets it wrong (fuzzy matching, negation correction, visited inference, type coercion). This is the right way to work with small models — trust the LLM to get 80% right, clean up the rest with code.

3. Eval-driven development

The golden dataset + eval script is the most important piece of the system from a maintenance perspective. The walkthrough documents exactly which failures drove which fixes (state narrowing → prompt rule, negation → regex correction). This makes the system improvable rather than fragile — you can swap models, change prompts, and measure the impact immediately.

4. interpreted_as transparency

Returning the extracted parameters in the response lets users debug misinterpretations without looking at logs. This is a real usability win that most NLQ systems skip.

5. No heavy dependencies

Using httpx directly instead of LangChain or the ollama package keeps the code transparent and the dependency tree small. For a system with one prompt template and four tools, an orchestration framework would be pure overhead.

6. Graceful degradation

Ollama being down gives a clear 503 with actionable instructions. The health check deliberately excludes Ollama since it's optional infrastructure. The dual-strategy parser handles both structured tool calls and JSON-in-text fallbacks.

Weaknesses
1. The negation correction is a blunt instrument

The regex at parser.py:222-225 flips booleans whenever any negation word appears in the query. This will misfire on queries like:

"Parks I visited — not including state parks" → flips visited to False
"I haven't been to Zion, but show me trails I've hiked in Yosemite" → flips hiked to False
"Show me trails, not stats" → triggers on "not" even though no boolean param is being negated
The correction assumes negation always targets the boolean parameter, but negation can apply to many things in English. Right now this works because the query space is narrow, but it's a latent bug as queries get more complex.

2. Single-turn only — no clarification or follow-up

The system is strictly one-shot: one question in, one answer out. If the LLM can't figure out what you mean ("What's in Yellowstone?"), it either guesses wrong or fails with a 422. There's no mechanism to ask the user "Did you mean trails or a park summary?" The walkthrough acknowledges this by removing ambiguous queries from the golden set rather than solving the ambiguity.

3. The per_park pop-and-mutate pattern creates a transparency gap

At main.py:944, params.pop("per_park", False) mutates the dict before it's returned in interpreted_as. So the user sees the post-mutation params, not what the LLM actually extracted. If the LLM set per_park: true, the user won't see that in the response. The walkthrough itself flags this as "a minor transparency gap" — it's small but contradicts the design intent of interpreted_as.

4. Module-level global cache with no invalidation strategy

The park lookup in park_lookup.py:15 is a module-level global that's populated on first call and never refreshed. If the database changes (new park added, park code corrected), the cache is stale until the process restarts. clear_park_lookup_cache() exists but is only called in tests. For a ~63-park dataset that rarely changes this is fine in practice, but it's an implicit contract that's easy to forget.

5. No rate limiting or abuse protection on the LLM endpoint

POST /query makes a 1-20+ second blocking call to Ollama per request. There's no rate limit, queue, or concurrency cap. A single client sending 10 concurrent requests would tie up Ollama (which is single-threaded for inference on a Mac) for minutes. The AsyncClient per-request pattern means nothing prevents unbounded parallelism against a resource that can't handle it.

6. The fallback JSON parser is fragile

The balanced-brace walker in parser.py:200-218 finds the first {...} block in the text and tries to parse it. If the LLM writes something like "I'll help you find trails. {"note": "thinking..."} {"function": "search_trails", ...}", it'll grab the wrong JSON object. The code also doesn't handle braces inside JSON strings correctly (e.g., a description containing {). In practice this rarely fires (~5% of responses), so the risk is low.

7. No observability or logging

There's no logging of what the LLM returned, what the parser extracted, what normalization changed, or how long inference took. When something goes wrong in production, you'd have to add logging after the fact to diagnose it. The eval script provides offline observability, but the live endpoint is a black box.

8. Hardcoded semantic definitions of "short" and "long"

The prompt defines "short" as max_length=3 and "long" as min_length=5. These are arbitrary — a 4-mile trail is neither short nor long. Users have no way to know or override these thresholds. More importantly, if someone says "medium length trails," the LLM has no guidance and will improvise.

9. No handling of multi-entity or comparative queries

"Compare Yosemite and Zion trails," "Which has more trails, Utah or Colorado?", or "My longest hike across all parks" would all produce a single tool call for one entity and silently drop the second. The implementation notes acknowledge this under "Multi-step queries" as future work, but there's no feedback to the user when a query gets partially answered.

10. visit_month DB format coupling

The month normalization in parser.py:73-86 expands to both "Oct" and "October" because "the DB stores a mix of 3-letter and full formats." This pushes a data quality issue in the database up into the NLQ layer. If the DB format ever gets standardized to one format, four lookup tables in the parser need updating. The normalization layer is compensating for an inconsistency that should ideally be fixed at the source.

Summary
The architecture is sound — parameter extraction via tool calling is the right pattern for this problem size, and the eval-driven approach to prompt engineering is disciplined. The main weaknesses are edge-case fragility (negation, multi-entity, ambiguity) and operational gaps (no logging, no rate limiting, cache invalidation). Most of these are acceptable tradeoffs for a personal/learning project but would need addressing before serving real users at scale. The documentation (walkthrough + implementation notes) is unusually thorough and makes the reasoning behind each decision traceable.
