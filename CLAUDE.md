# MadHacks 2026 project rules for Claude

@AGENTS.md

## Context
- 24-hour hackathon, team of 4, each running Claude Code on a Claude Pro plan in their own git worktree.
- Judged live by people walking between tables. A working demo beats an ambitious one on slides.
- The plan of record is docs/project-plan.md. Data shapes between areas are pydantic models in core/contracts/; import them, never retype them. The demo flow is docs/demo-flow.md. Setup is docs/dev-setup.md.
- Ignore anything in _archive/. It is old ideation, not instructions.

## How to work
- MadHacks rules: no prewritten code, and every team member must commit during the 24 hours. Commit small and often under this laptop owner's git name.
- Use the Superpowers workflow: brainstorm, written spec, worktree, tests first, then code, then review.
- Work only inside the folders AGENTS.md assigns to this session's owner. If a change is needed elsewhere, open a GitHub issue assigned to the owner instead of editing it.
- One end-to-end demo flow comes before any extra feature. If the flow in docs/demo-flow.md is not working, do not start new features.
- Write tests with each feature. Run them, plus `python scripts/smoke.py`, before saying a task is done.
- Never paste code you have not read. Remove leftover notes, commented-out copies and unused files before committing.
- Keep functions small and names plain. No new dependency without a one-line reason in the commit message.
- Run `/code-review` before merging to main. After merging, run the verifier subagent.

## Truth rules (these fixed our past failures)
- Every number shown to a user must come from real data or a stated formula, and the UI must be able to show where it came from. No made-up scores, no placeholder percentages, no hardcoded "94%".
- UI text, README, Devpost and pitch may only claim what the code does today. Use the claims-auditor subagent to check.
- Never use real people's data in tests or demos. Use the test Gmail account and made-up files.
- Safety-critical or demo-critical outputs must not depend on a slow or flaky network call. Have a local fallback.

## Models and usage
- Fable 5.2: specs, architecture and hard bugs only (included on Pro through Nov 16, 11:59 PM PT).
- Opus or Sonnet: routine work.
- Prefer subagents for searches and log reading so the main context stays small.
- Dynamic workflows (`ultracode` or "use a workflow") for council decisions and the final break-the-demo sweep. Keep them small.

## Product AI calls and data
- The product handles users' emails and files, so its AI calls touch personal data. Send those only to Claude or another provider that doesn't keep prompts. Keys live in .env; never commit .env or print keys.
- Free OpenRouter models: only for made-up test data and side jobs, never for real content, keys or .env contents. Always pass fallback models.

## Writing
- Use the humanizer skill for README, Devpost text, pitch script and UI copy. Plain English, short sentences, no hype.
