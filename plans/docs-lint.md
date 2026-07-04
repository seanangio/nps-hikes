# Adding markdownlint to the docs linting pipeline

## Context

The project already had Vale for prose linting (style, grammar, word choice) in both
pre-commit and CI. This conversation added markdownlint-cli2 for structural Markdown
checks (blank lines, code fences, heading levels, table formatting) and MkDocs strict
builds for link validation.

## Tool choice: markdownlint-cli2

There are three markdownlint implementations:

- **markdownlint-cli2** (Node.js, by DavidAnson) -- chosen. The recommended CLI by the
  original markdownlint author. Richest rule set, official pre-commit and GitHub Action
  support.
- **markdownlint-cli** (Node.js, by igorshubovych) -- older wrapper around the same
  library. Maintained but superseded by markdownlint-cli2.
- **pymarkdown** (Python, by jackdewinter) -- independent Python implementation with
  fewer rules and smaller community.

Pre-commit manages the Node environment in isolation, so no project-level Node
dependency is needed.

## VS Code extension

Install **markdownlint** by David Anson (`DavidAnson.vscode-markdownlint`). Same author,
same rules, picks up `.markdownlint-cli2.yaml` automatically for inline diagnostics.

## Configuration: .markdownlint-cli2.yaml

```yaml
config:
  MD013: false  # Line length -- impractical for prose

ignores:
  - ".venv/**"
  - "scratch/**"
  - "plans/**"
  - "reviews/**"
  - ".claude/**"
  - "styles/proselint/**"
  - ".pytest_cache/**"
```

MD013 (line length at 80 chars) was the only rule disabled. It accounted for ~200 of the
original 391 errors and is not practical for prose Markdown.

All other rules are enabled, including MD060 (table column style) after fixing separator
rows project-wide.

## Errors fixed

Starting from 391 errors across 20 files, down to 0 across 14 linted files.

| Fix | Files changed |
| --- | --- |
| MD031: blank line before code fence | CLAUDE.md, artifacts/README.md, tests/integration/README.md |
| MD032: blank line around lists | docs/api-tutorial.md, tests/integration/README.md |
| MD022: blank line below heading | tests/integration/README.md |
| MD040: add `text` language to code fences | docs/api-tutorial.md (6), docs/getting-started.md, docs/index.md, streamlit_app/README.md, tests/integration/PHASE3_SUMMARY.md |
| MD060: table separator rows `|---|` to `| --- |` | docs/api-tutorial.md, docs/data.md, docs/getting-started.md, docs/index.md, tests/integration/PHASE2_SUMMARY.md, tests/integration/PHASE3_SUMMARY.md |
| MD034: bare URL wrapped in `<>` | README.md |
| MD042: empty badge link filled in | README.md (manual fix) |
| MD009: trailing whitespace | tests/integration/PHASE2_SUMMARY.md |
| MD038: code span fix | .github/instructions/docs.instructions.md |

## Pre-commit hook

Added to `.pre-commit-config.yaml`:

```yaml
- repo: https://github.com/DavidAnson/markdownlint-cli2
  rev: v0.22.1
  hooks:
    - id: markdownlint-cli2
```

## CI workflow changes (.github/workflows/prose-lint.yml)

Renamed from "Prose Lint" to "Docs Lint". Now runs three parallel jobs:

| Job | Tool | What it catches |
| --- | --- | --- |
| `prose-lint` | Vale | Style, grammar, word choice |
| `markdown-lint` | markdownlint-cli2 | Formatting (blank lines, code fences, headings, tables) |
| `docs-build` | `mkdocs build --strict` | Broken links, missing nav entries, rendering errors |

Path triggers updated to also include `.markdownlint-cli2.yaml` and `mkdocs.yml`.

## Remaining to-do

- Review the changes to `.github/workflows/prose-lint.yml` before merging.

## Useful commands

```bash
# Run markdownlint locally (via npx, no install needed)
npx markdownlint-cli2 "**/*.md" "#.venv" "#scratch"

# Build docs locally with live reload
mkdocs serve

# Build docs with strict link checking
mkdocs build --strict
```
