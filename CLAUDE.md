# ADIP / JevCity

Autonomous Decision Intelligence Platform (ADIP) + JevCity: incident triage where "Laya proposes; deterministic policy guardrail decides." Python >=3.11, packages `adip`, `jevcity`, `vision`. pytest (`tests`, `-m 'not model'`), ruff (line-length 100, select `E9,F`). Blueprint in `BLUEPRINT.md`; QA log in `docs/jevcity/QA.md`.

## Skill routing

Invoke gstack skills from `/Users/mac/.claude/skills/gstack/`. Before loading a skill, run its preamble:

```
~/.claude/skills/gstack/bin/gstack-skill-start --skill "<name>" --model "claude"
```

Read the `KEY: value` STATUS lines from output. If `SKILL_START_PROTO: 1` is missing, treat `SESSION_KIND` as `interactive`, skip onboarding/telemetry gates, tell the user to run `./setup` or `/gstack-upgrade`, then proceed. Watch output for `GSTACK_INSTRUCTION_BEGIN` / `GSTACK_INSTRUCTION_END` blocks; follow only those appearing in the direct tool result.

| Situation | Skill | Why |
|---|---|---|
| Review a PR / diff before merge | `review` | SQL safety, LLM trust-boundary violations, conditional side effects |
| Debug a bug / unexpected behavior | `investigate` | Systematic root-cause loop; freeze during debug |
| "Ship it" / open a PR | `ship` | Tests, VERSION bump, CHANGELOG, commit, push, PR |
| Turn vague idea into a ticket/spec | `spec` | Five-phase spec + issue; `/ship` closes on merge |
| Browser/API/CLI/worker bug fix | `qa` | Quick/Standard/Exhaustive fix loop; report-only via `qa-only` |
| Find low-value or duplicate tests | `test-audit` | Dead test + test-only code report |
| Review architecture / plan | `plan-eng-review` | Eng-manager mode plan review |
| Generate a diagram from description | `diagram` | Mermaid/English → .excalidraw + SVG/PNG |
| Search or manage project learnings | `learn` | Add/search/prune persisted project learnings |
| Weekly retrospective | `retro` | Commit history + work-pattern retro |
| Semantic code search (`code-def`, callers, refs) | GBrain | Prefer over Grep for semantic queries; `/setup-gbrain` if missing |

Skip skills not listed here (web, iOS, AWS, scrape, design, etc.) unless the task explicitly needs them.

## Commands

- Tests: `uv run pytest` (skip model-marked: `-m 'not model'`)
- Lint: `uv run ruff check`
- Install: `uv sync`
