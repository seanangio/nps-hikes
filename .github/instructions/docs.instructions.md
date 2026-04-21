---
applyTo: "docs/**/*.md"
---

# Documentation Review Instructions

Review documentation changes for the issues below. Do NOT flag issues already
covered by the project's Vale linter (prose quality, passive voice, weasel words,
clichés, terminology like "PostgreSQL" vs "Postgres"). Focus on what an LLM can
catch that a rule-based linter cannot.

## Accuracy

- Flag instructions, commands, or URLs that may be outdated or inconsistent with
  code changes in the same PR.
- Flag example output (JSON, shell output) that no longer matches the current API
  or CLI behavior based on other files in the PR.
- Flag references to endpoints, parameters, or environment variables that don't
  exist or have been renamed.

## Completeness

- If the PR adds a new feature, endpoint, or configuration option, flag missing or
  incomplete documentation for it.
- Flag missing prerequisites or steps that a reader would need to follow the guide.

## Clarity and Structure

- Flag explanations that assume knowledge not established earlier in the document.
- Flag inconsistent heading hierarchy or document structure compared to sibling
  pages.
- Flag code blocks missing a language identifier (```bash, ```json, etc.).

## Style

- Use second person ("you") to address the reader, not third person ("the user").
- Use active voice and direct imperatives ("Run the command", not "The command
  should be run").
- Keep sentences concise. Flag sentences longer than ~30 words that could be split.
- Prefer plain language over jargon. If a technical term is necessary, it should be
  defined on first use or be widely known to the target audience (developers
  familiar with Python, Docker, and GIS basics).
