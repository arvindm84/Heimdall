# Agents and ownership

Every coding agent on this team reads this file before each task. The full plan is docs/project-plan.md. The data shapes that cross between areas are pydantic models in core/contracts/.

## Team
Fill in at the first standup. One person builds the firewall, one gets the agents running, two build the app. Everyone builds the front end together from H12.

| Area | Person | GitHub login | Owns these paths |
|---|---|---|---|
| A: Firewall | | | core/firewall/, core/proxy/, core/gateway.py, images/gateway/ |
| B: Agents | | | core/runtime/, images/ (except gateway), compose.yaml |
| C: App back end (integration lead) | | | core/api/, core/keys/, core/contracts/, core/cli.py |
| D: App shell and red team | | | app/, attacks/, scripts/, docs/, pitch/ |
| Everyone (from H12) | | | app/ui/ screens, split as in project-plan.md section 11 |

## Seams (where two areas meet)
| Seam | Owners | Test |
|---|---|---|
| 1. Agent containers to gateway (MCP tools, model proxy) | B and A | tests/seams/test_agent_gateway.py |
| 2. Gateway to core (events, approvals, consent) | A and C | tests/seams/test_gateway_core.py |
| 3. Core to agent manager (open, stop, kill, restart_with) | C and B | tests/seams/test_core_runtime.py |
| 4. App to core (HTTP and WebSocket, generated types) | D and C | scripts/smoke.py |

- Never retype another area's data shapes. Import them from core/contracts/. The UI imports the generated types in app/ui/src/api/.
- Changing a contract model: pair with the other seam owner, change the model and its seam test in one PR labelled `contract-change`, and get a yes from both owners. The control API freezes at H10.
- `scripts/smoke.py` runs the walking skeleton (app to core to echo agent to gateway and back). It must pass before you merge to main.

## How we coordinate (no shared agent board)
- Each person runs their own Claude Code session and delegates inside their own area.
- Coordination happens on GitHub: issues, labels, PRs and the GitHub Project view. Humans also check in at H2, H4, H8, H12, H16, H20.
- Only edit your own paths. If you need a change in someone else's area, open a GitHub issue assigned to them with the `area:<theirs>` label. Seam tests belong to both owners of that seam.
- From H8 each person also owns demo scenes end to end (project-plan.md section 11) and files issues to whoever owns a broken part.

## Per task (inside your area)
1. Make or pick a GitHub issue. Write a 3-line spec in it.
2. Branch: `<area>/<short-task>` (example: `firewall/placeholder-vault`). Use `claude --worktree <task>` for parallel tasks.
3. Tests first, then code (Superpowers flow).
4. Run `python scripts/smoke.py`. `/code-review`, then open a PR that says `Closes #<issue>`. CI must pass.
5. Merge within the hour. Pull from main at least every two hours.
6. After merging, run the verifier subagent.

## Shared rules
- The demo flow in docs/demo-flow.md comes first for everyone.
- H3: the walking skeleton runs on main. If not, everyone fixes it before anything else.
- H8: the main flow works end to end from the command line, or we cut scope together at the standup.
- H12: back end done; front end starts. H18: front end done. H20: freeze, bug fixes only.
- Small commits under your own git name. Every member commits throughout the 24 hours.

## Subagents in .claude/agents/
- verifier: runs tests and the demo flow and reports what fails. Run after every merge to main.
- claims-auditor: checks every claim in the UI text, README, Devpost and pitch against the code. D runs it before submission and after any copy change.

## Skills
- Superpowers plugin: planning, TDD, debugging, review.
- frontend-design plugin: the app UI (from H12).
- humanizer (.claude/skills/humanizer): all public-facing text.
