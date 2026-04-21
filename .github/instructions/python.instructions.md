---
applyTo: "**/*.py"
---

# Python Code Review Instructions

Review Python code changes for the issues below. Do NOT flag issues already
covered by the project's Ruff linter (formatting, import order, unused imports)
or mypy (type errors). Focus on what an LLM can catch that static analysis cannot.

## Correctness

- Flag logic errors, off-by-one mistakes, or unhandled edge cases.
- Flag SQL queries that may be vulnerable to injection (all queries should use
  parameterized inputs via SQLAlchemy `text()` with `:param` syntax).
- Flag potential runtime errors (e.g., accessing a key that may not exist,
  dividing by zero without a guard).

## API Consistency

- New endpoints should follow existing patterns: SQLAlchemy `text()` queries in
  `api/queries.py`, Pydantic response models with Field descriptions and examples,
  router functions in the appropriate `api/routers/` file.
- Query parameters should use consistent naming conventions (snake_case) and
  include sensible defaults where appropriate.

## Test Coverage

- If the PR adds new functionality, flag if corresponding tests are missing.
- Tests should use `unittest.mock.patch` on `api.queries.get_db_engine` with
  `namedtuple` fixtures, consistent with existing tests.
