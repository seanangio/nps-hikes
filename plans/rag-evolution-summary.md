# RAG Evolution Summary

This document is a conceptual retrospective on how the retrieval pipeline in this project evolved.

It is meant for future me: a reminder of what I built, why I built it, and what each stage taught me about retrieval-augmented generation, structured data, text data, and the role of LLMs in a real application.

## The high-level arc

The project did not begin as a RAG system.

It began as a natural-language interface over an already-structured API. The earliest goal was modest: let a user say "short hikes in Yosemite" and translate that into existing endpoint parameters. The LLM was not the answer engine. It was a parser.

That first phase mattered because it established an important principle that carried through the rest of the work:

- the LLM should do the fuzzy language work
- deterministic code should do the data work
- existing domain logic should remain authoritative

Over time, that design ran into a limit. Some questions are easy to express as filters on columns like `park_code`, `length_miles`, `hiked`, or `visited`. But many interesting park questions are not naturally stored as fields. They live inside descriptive text.

That is where the project moved from "natural language over structured data" into actual retrieval work. RAG entered the picture not because I wanted a chatbot, but because the dataset contained useful meaning that the relational model did not expose directly.

The system ultimately evolved through four major stages:

1. `NLQ translation`: use an LLM to turn plain English into parameters for existing endpoints.
2. `Semantic retrieval`: collect text from NPS content endpoints, chunk it, embed it, and search it by meaning.
3. `Semantic-to-structured bridging`: connect semantically matched content back to actual trail records.
4. `Hybrid retrieval`: support queries that mix semantic intent and structured constraints in one flow.

That progression is the real story. The project became more "RAG-like" each time I found a new gap between what users want to ask and what the current data model could express.

## Phase 1: NLQ before RAG

The first version was not RAG in the usual sense. It did not retrieve documents and then ground an LLM answer in them. Instead, it used a local LLM through Ollama to interpret a question and choose one of several existing operations:

- trail search
- park search
- aggregate stats
- park summary

Conceptually, this was closer to tool calling or semantic routing than to document retrieval.

The important insight was that natural language is valuable even when the backend is completely structured. A user does not think in parameter names like `max_length=3` or `visit_month=fall`. A user thinks in phrases like:

- "short hikes in Yosemite"
- "parks I visited in October"
- "trails I haven't hiked yet"

The LLM's job was to absorb that ambiguity and produce something the rest of the application already knew how to execute safely.

This phase taught several durable lessons.

### 1. LLMs are useful well before they become answer generators

The model did not need to summarize, reason over documents, or compose long responses. It only needed to map language to intent and arguments.

That made the system much safer and easier to validate. Instead of letting the LLM invent facts, I constrained it to known tools and known parameters. The application still got all of its results from ordinary Python query functions.

This is one of the clearest examples in the project of where LLMs fit well:

- they are strong at interpreting messy human input
- they are weaker than deterministic code at enforcing rules
- they become much more reliable when asked to produce structure instead of prose

### 2. Prompting alone is not enough

The NLQ endpoint ended up using a "belt-and-suspenders" pattern:

- teach the model with explicit prompt rules
- then normalize and repair the output in code

Examples from the project:

- state mentions like "Colorado" needed to stay as `state=CO` rather than collapsing to one park
- "under 5 miles" needed to become `max_length=5`, not `min_length=5`
- "haven't hiked" needed deterministic post-processing because small-model negation was shaky
- park names needed both prompt-time lookup guidance and post-LLM fuzzy resolution

This became a general design philosophy for the later RAG work too. LLMs are best used in partnership with ordinary software, not as a replacement for it.

### 3. Evaluation matters more than intuition

The golden query set and eval script were central. They turned prompt changes from guesswork into measurable iteration. That discipline set up the later retrieval work well, because the project already had the habit of treating LLM behavior as something to test instead of merely admire.

## Why NLQ was not enough

The structured NLQ system was good at questions whose meaning could be reduced to existing filters.

Examples:

- "trails over 5 miles in Zion"
- "parks I visited in summer"
- "show me overall trail stats"

But it could not answer questions like:

- "which parks have slot canyons?"
- "where are the best winter activities?"
- "find waterfall hikes in California"

Those questions depend on semantic content, not just schema.

This is the key reason RAG became necessary in this project. The limitation was not that the LLM was too weak. The limitation was that the underlying dataset had useful information trapped in text fields and extra API endpoints that were not part of the original structured interface.

In other words, the project hit the classic RAG problem:

- the knowledge exists
- the knowledge is relevant
- but the knowledge is not represented in a form that exact filtering can use directly

## Phase 2: Introducing retrieval through text

The next step was to collect richer NPS content from endpoints like `/thingstodo` and `/places`, store it locally, and make it searchable by meaning.

This was the point where the system became recognizably RAG-shaped.

The pipeline followed the standard pattern:

1. collect raw text
2. clean it and normalize it
3. split it into chunks
4. generate embeddings
5. store vectors in PostgreSQL via pgvector
6. embed the user's query at runtime
7. retrieve nearest chunks by cosine similarity

The conceptual shift here was important.

The NLQ phase interpreted a user request into structured filters over known fields. The semantic search phase represented text itself as searchable knowledge. Instead of asking "which rows match these conditions?", the system could now ask "which passages are closest in meaning to this query?"

### Why this counts as RAG even before full answer generation

The project initially stopped at retrieval. The `/search` endpoint returned ranked chunks instead of immediately turning them into a long natural-language answer.

That is still meaningful RAG work.

Retrieval is the hard grounding layer. Once useful passages are being retrieved reliably, generation becomes optional and composable. Without retrieval quality, answer generation is decoration.

This project made that distinction very clear:

- semantic retrieval was the new capability
- answer generation was a possible later layer

That ordering reflects a healthy way to build RAG systems. First make the system find the right evidence. Then decide how much language generation you actually need.

### A simple Phase 2 example

If I want a concrete example of what this phase looked like in practice, the closest current equivalent is a raw semantic search that returns content chunks without resolving them to structured trail objects.

For example:

```bash
curl "http://localhost:8001/search?q=waterfalls+hikes&resolve_trails=false" | python3 -m json.tool
```

That is basically the Phase 2 shape:

- take a semantic query like "waterfalls hikes"
- embed it
- retrieve the nearest content chunks
- return ranked text evidence

If I want to narrow that retrieval-only search, the most faithful filters are still content-level ones such as `park_code` or `source_type`:

```bash
curl "http://localhost:8001/search?q=waterfalls+hikes&park_code=yose&source_type=thingstodo&resolve_trails=false" | python3 -m json.tool
```

One subtle but important distinction: `state`, `hiked`, and trail length filters belong to the later hybrid/trail-resolution flow. In the current API, those filters only apply when `resolve_trails=true`, which means they are more representative of Phase 3 or Phase 4 than of Phase 2.

### What the text added

The NPS content endpoints contained things the original schema could not express cleanly:

- activity descriptions
- seasonal recommendations
- scenic highlights
- interpretive descriptions of trails and places
- topics like waterfalls, slot canyons, viewpoints, ranger programs, and winter use

This is one of the deeper lessons of the project: text is not just "unstructured leftovers." It is often where the most human-meaningful information lives.

The relational schema was still essential for hard facts and filtering. But the text corpus captured the descriptive layer that people often care about first.

## Phase 3: From semantic chunks to useful trail results

Standalone semantic search was valuable, but it revealed another product gap.

A query like "waterfall hikes in California" might retrieve highly relevant text chunks, but chunk retrieval alone is not the same thing as delivering a usable trail result set. Users of this application care about trails as mapped, filterable objects. They want:

- trail records
- lengths
- hiked status
- source data
- map display
- table display

Raw passages are informative, but they are not the primary interaction model of the app.

That led to an important architectural move: bridge semantic content back to structured trail entities.

The project did this by precomputing content-to-trail mappings during indexing. If a content item like "Hike the Narrows" or "Vernal Fall Footbridge" could be matched confidently to a trail record, then semantic retrieval could become trail retrieval rather than just document retrieval.

### A simple Phase 3 example

One concrete example is Yosemite's `Bridalveil Fall Trailhead` content item.

That title exists in the collected NPS places data and describes the short paved walk to the base of Bridalveil Fall. In Phase 2, a query about waterfall hikes could retrieve that chunk as relevant text. In Phase 3, the system went one step further: during indexing, it precomputed a mapping from that content item to a structured Yosemite trail record and stored the relationship in `content_trail_mapping`.

Conceptually, the bridge looks like this:

```text
content_embeddings.title = "Bridalveil Fall Trailhead"
            |
            v
content_trail_mapping
            |
            v
tnm_hikes / osm_hikes trail row for the Yosemite trail
```

If I want to inspect that bridge directly, the useful debugging query is something like:

```sql
SELECT
  ce.park_code,
  ce.title AS content_title,
  ctm.trail_name,
  ctm.trail_source,
  ctm.trail_id,
  ctm.name_similarity_score,
  ctm.match_confidence
FROM content_trail_mapping ctm
JOIN content_embeddings ce
  ON ce.id = ctm.content_embedding_id
WHERE ce.park_code = 'yose'
  AND ce.title ILIKE '%Bridalveil%';
```

The important idea is that this linkage was not invented at query time. It was computed ahead of time by fuzzy-matching content titles against trail names within the same park and saving the best confident match. That is what made later semantic search results feel like normal trail search results instead of isolated text snippets.

Once that mapping existed, a semantic query could retrieve Bridalveil-related content, join through the mapping table, and return a normal trail object with fields like trail name, length, source, and hiked status. That is the essence of Phase 3: the retrieved text became evidence, but the returned object could still be a trail.

This was a big conceptual upgrade.

Instead of treating RAG as "retrieve text, then make the LLM talk about it," the project started using retrieval as an intermediate layer that improved a structured application. The retrieved text was evidence. The returned object could still be a trail.

That pattern feels especially important in hindsight:

- semantic retrieval found meaning
- deterministic linking connected meaning to application entities
- the final user experience stayed grounded in the app's existing object model

This is a strong fit for many real-world RAG systems. Users often do not ultimately want documents. They want actions, records, or objects informed by documents.

## Phase 4: Hybrid search as the unification point

Once semantic trail search existed, a final limitation became obvious: the system could answer structural questions or semantic questions, but not both at once.

That is not how users think.

Users naturally combine descriptive intent with concrete constraints:

- "slot canyons I hiked"
- "waterfall hikes over 5 miles in California"
- "short trails in Texas"

These are hybrid queries. They contain both:

- semantic content: waterfall hikes, slot canyons, winter activities
- structured constraints: state, hiked status, minimum length, maximum length, source

Hybrid search was the point where the project's retrieval architecture started to feel complete.

The system no longer had to choose between two separate modes of thought. It could:

1. interpret the user query with the LLM
2. identify that a semantic component exists
3. run semantic matching to find relevant trail-linked content
4. apply structured filters to the resulting trail candidates
5. return a normal trail result set with preserved semantic intent

This is probably the cleanest expression of what RAG became in this project.

RAG was not a chatbot feature bolted onto the side. It became a retrieval layer that made the core trail application more expressive.

## Full circle: the `/query` endpoint grew up

There is a satisfying symmetry in where the project ended.

The original `/query` endpoint was the first natural-language interface in the system, but in the beginning it was limited to structured operations. It could translate a request like "short hikes in Yosemite" into known parameters and dispatch one of the existing query functions. That was useful, but narrow.

After semantic retrieval, content-to-trail linking, and hybrid search were added, the same endpoint became something much more capable. It was no longer just a parser for structured filters. It became a unified natural-language front door to all the retrieval modes behind the application:

- structured trail and park search
- semantic topic search
- hybrid semantic-plus-structured search
- grounded answer generation from retrieved context

That last piece matters. By the mature stage of the system, `/query` could return not only structured results but also a `generated_answer` grounded in the retrieved chunks or topic context. In other words, the endpoint that originally helped users reach deterministic query functions eventually became the place where the full retrieval architecture came back together.

So I do not think of this as a separate formal phase so much as the project coming full circle. The system started with natural language as an interface convenience. It ended with natural language as the top layer over a much richer retrieval stack.

## The bigger picture: what this project says about RAG

Looking across all four phases, a few broader ideas stand out.

### RAG is not one thing

It is tempting to think of RAG as a standard recipe:

- stuff documents into a vector store
- retrieve a few chunks
- send them to an LLM
- get an answer

This project suggests a more useful definition.

RAG is any architecture where external knowledge is retrieved and used to improve what the system can do at response time. That improvement can serve different ends:

- better natural-language answers
- better routing
- better entity selection
- better filtering
- better application results

In this project, RAG evolved from document retrieval into hybrid entity retrieval. The LLM mattered, but so did PostgreSQL, pgvector, chunking, fuzzy matching, query design, and UI behavior.

### Text becomes useful when it is operationalized

The project had access to rich park text, but text only became productively useful after several transformations:

1. collection from APIs
2. cleaning and HTML stripping
3. chunking into meaningful passages
4. embedding into a comparable vector space
5. indexing for retrieval
6. linking to application entities
7. exposing the results through endpoints and UI

That is an important practical truth about RAG. The text itself is not the product. The retrieval pipeline is what turns text into a feature.

### LLMs are one layer, not the whole architecture

The role of LLMs in this project stayed fairly disciplined:

- for NLQ, the LLM translated language into structured intent
- for semantic retrieval, an embedding model translated text into vectors
- for topic queries, an LLM could optionally generate a summary, but only after retrieval had already found grounded context

Most of the system's actual usefulness came from the interaction between LLM-powered components and conventional software:

- prompt rules
- normalization code
- SQL queries
- vector indexes
- content-trail linking
- response shaping
- frontend state management

That balance is worth remembering. A good RAG system is rarely "just the model." It is usually a carefully assembled collaboration between statistical language tools and deterministic application logic.

### Structured and semantic retrieval are complements

One of the strongest lessons from the project is that structured retrieval and semantic retrieval solve different problems.

Structured retrieval is best when:

- the user knows the constraint
- the data has a clean column for it
- precision matters more than interpretation

Semantic retrieval is best when:

- the user is describing a concept or theme
- the data expresses that meaning in prose
- exact keywords or schema fields are insufficient

Hybrid search works because real user questions often need both at the same time.

## Concrete examples of the evolution

Here are a few example queries that illustrate how the system changed over time.

### Example 1: "short hikes in Yosemite"

Early NLQ could already do this well.

- LLM extracts `park_code=yose`
- "short" becomes `max_length=3`
- existing trail query function returns the results

No RAG needed. This is structured translation.

### Example 2: "things to do in winter at Yosemite"

This pushed beyond the original structured model.

- "winter" is partly semantic, not just a numeric or categorical filter
- useful information lives in NPS content descriptions
- semantic retrieval finds winter-related chunks for Yosemite

This is where embeddings and content search add value.

### Example 3: "waterfall hikes in California"

This is where standalone semantic retrieval is not quite enough.

- "waterfall" is semantic
- "California" is structured
- users want trails, not just text snippets

The mature system can resolve the topic semantically, bridge matched content to trails, and apply the state filter.

### Example 4: "slot canyons I hiked"

This is the hybrid case in its purest form.

- "slot canyons" requires semantic understanding
- "I hiked" is a structured boolean filter

This kind of query captures the full arc of the project. It would have been impossible in the first phase, partially answerable in the middle phases, and naturally supported only after hybrid retrieval was added.

## Architectural summary by stage

For memory, here is the shortest accurate summary of each stage.

### Stage 1: NLQ parameter extraction

- LLM used as a tool router and argument extractor
- existing Python query functions remained authoritative
- structured API became easier to access through natural language

### Stage 2: Semantic content retrieval

- new NPS text sources collected and embedded
- pgvector enabled meaning-based search over park content
- the system could answer descriptive/topic-based questions

### Stage 3: Semantic retrieval linked to trails

- content chunks were mapped to trail entities
- semantic matches could produce structured trail records
- retrieval became more useful inside the app's main UX

### Stage 4: Hybrid search

- semantic intent and structured filters could work together
- one query could express both theme and constraints
- the application moved closer to how users naturally ask for things

## What I would want to remember

If I had to compress the whole project into a few takeaways, they would be these:

- The first valuable use of an LLM in an application is often interpretation, not generation.
- RAG became necessary when the meaningful parts of the dataset lived in text rather than columns.
- Retrieval quality mattered more than flashy answer generation.
- The best results came from combining embeddings, SQL, entity linking, and careful normalization.
- Hybrid search was the real destination, because real user questions mix semantics and structure.

Most importantly, this project showed that "building a RAG pipeline" does not have to mean "building a chatbot." It can mean teaching an application to make better use of its own knowledge.
