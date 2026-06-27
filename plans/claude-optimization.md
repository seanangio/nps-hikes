# Claude Code Optimization for NPS Hikes

Ideas and recommendations for getting more out of Claude Code on this project.

---

## 1. Expand CLAUDE.md

The current CLAUDE.md is minimal (just points to README and the virtualenv activation).
Adding more context improves Claude Code's output from the start of every session.

### What to add

- **Build/test commands**: `pytest tests/`, `pre-commit run --all-files`
- **Architecture overview**: FastAPI + PostGIS, SQLAlchemy `text()` queries (no ORM), Pydantic response models with Field descriptions
- **Coding conventions**: parameterized queries only, `namedtuple` fixtures for test mocking, `unittest.mock.patch` on `api.queries.get_db_engine`
- **File organization**: queries in `api/queries.py`, NLQ logic in `api/nlq/`, tests in `tests/`
- **Key gotchas**: trail deduplication CTE with >70% `similarity()` threshold, TNM preferred over OSM

### Target

~50-100 lines. Don't duplicate the README — link to it with `@README.md` syntax.

---

## 2. Fix Permission Reapproval

Create `.claude/settings.json` to pre-approve common commands:

```json
{
  "permissions": {
    "allow": [
      "Bash(source ~/.virtualenvs/nps-hikes/bin/activate *)",
      "Bash(pytest *)",
      "Bash(python -m pytest *)",
      "Bash(pre-commit run *)",
      "Bash(git status)",
      "Bash(git diff *)",
      "Bash(git log *)"
    ],
    "deny": [
      "Read(.env*)",
      "Bash(rm *)"
    ]
  }
}
```

### Permission modes

| Mode | Behavior | Best for |
|------|----------|----------|
| `default` | Ask for everything | Sensitive work |
| `acceptEdits` | Auto-approve file reads/edits, ask for bash/network | General dev (recommended) |
| `plan` | Read-only, propose changes first | Complex refactors |

Set default mode by adding `"defaultMode": "acceptEdits"` to the permissions block.

### Settings file locations (highest precedence first)

1. `.claude/settings.local.json` — personal, not committed
2. `.claude/settings.json` — project, committed to git
3. `~/.claude/settings.json` — user-global, all projects

---

## 3. Skills (Custom Slash Commands)

Skills are reusable workflow instructions stored as Markdown in `.claude/skills/<name>/SKILL.md` with YAML frontmatter.

### Potential skills for this project

- `/validate-sql` — check parameterized queries for injection risks and PostGIS correctness
- `/test-coverage` — run pytest with `--cov` on a module and suggest missing test cases
- `/add-endpoint` — scaffold a new API endpoint following existing patterns

### Example skill file

`.claude/skills/test-coverage/SKILL.md`:

```yaml
---
name: test-coverage
description: Analyze test coverage for a module and suggest missing tests.
allowed-tools: Read, Grep, Bash(pytest *)
---

Analyze test coverage:

1. Run pytest with coverage: `pytest --cov=ARGUMENTS --cov-report=term-missing`
2. Identify untested code paths
3. Suggest edge cases and test scenarios
4. Generate test code using unittest.mock.patch on get_db_engine with namedtuple fixtures
```

---

## 4. Hooks

Auto-run shell commands on lifecycle events. Configured in `.claude/settings.json` under `"hooks"`.

### Useful hooks for this project

**Auto-run pre-commit after file edits:**

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "cd \"$CLAUDE_PROJECT_DIR\" && pre-commit run --files $(git diff --name-only) 2>/dev/null || true"
          }
        ]
      }
    ]
  }
}
```

**Virtualenv reminder at session start:**

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup",
        "hooks": [
          {
            "type": "command",
            "command": "echo 'Reminder: activate virtualenv with: source ~/.virtualenvs/nps-hikes/bin/activate'"
          }
        ]
      }
    ]
  }
}
```

---

## 5. MCP Servers

Connect external tools to Claude Code. Potential use:

- **Read-only PostGIS connection** — let Claude query the database directly during development
- **GitHub integration** — interact with issues and PRs without leaving the session

```bash
claude mcp add --transport stdio postgres -- npx -y @bytebase/dbhub \
  --dsn "postgresql://readonly:pass@localhost:5432/nps_hikes"
```

---

## 6. Other Useful Features

- **`@` file references** — type `@api/queries.py` in prompts to include file contents directly
- **`/compact`** — summarize conversation history to free up context window space
- **Plan mode** — press `Shift+Tab` to switch; Claude researches and proposes changes without making them
- **Memory files** — Claude saves project notes to `~/.claude/projects/<project>/memory/MEMORY.md`; viewable with `/memory`

---

## Priority Order

1. **Create `.claude/settings.json`** with permission allowlists (eliminates reapproval friction)
2. **Expand CLAUDE.md** with architecture, commands, and conventions
3. **Add hooks** for auto pre-commit and virtualenv reminders
4. **Create 1-2 skills** for common workflows (test coverage, SQL validation)
5. **Explore MCP** for direct database access
