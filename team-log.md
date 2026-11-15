# MadHacks 2026 team log

Started Saturday, November 14, 2026. Running notes for the team: what we decided, what went wrong before, what is winning right now, and which tools we plan to use. Newest entries go at the top of the discussion log.

## 1. Event facts

- MadHacks 2026, November 14 to 15, Morgridge Hall, 1205 University Ave, Madison. 24 hours, teams of up to 4.
- Walk-in check-in 10:30 to 11:00 AM. Meals provided.
- Sponsors: American Family Insurance, TDS Telecom, Salesforce, UW-Madison CAI, Databricks, Qualcomm, N+1 Institute, SIG, Sparkles, Epic. Partners: Pepsi, Ryse, Red Bull.
- Tracks, prizes and judging criteria for 2026 were not on the website as of the morning of Nov 14. Waiting on the opening ceremony, Discord or Devpost.

Last year (Fall 2025) for comparison:
- 379 participants, 114 projects, 13 prizes (all non-cash).
- Overall: 1st 4x 4K TVs (3Docs, which turns PDF manuals into interactive 3D manuals), 2nd 4x Keychron keyboards, 3rd 4x headphones.
- Sponsor tracks and how many teams entered each: TDS networks track 30, Fish Audio 31, Capital One 31. 88 different teams entered at least one track; 26 entered none.
- Category awards: Hacker's Choice, Best Beginner, Best Community, Best AI, Most Dangerous, Most Social, Best Productive.
- Judged in person on creativity and execution, among other things.
- TDS is the only 2025 track sponsor back this year.

## 2. Discussion log

### Nov 14, late night (integration plan)
- Memory: one store per agent. Notes carry the label of the data they came from, and Confidential content needs the user's consent before it goes to a cloud model or the network. A local model needs no prompt.
- Chat: we use each agent's own interface (OpenClaw's web chat, Hermes through `ttyd`) instead of building our own. No task or session screen; the task is whatever the user types.
- One desktop app (`pywebview`, Electron as backup). No tray icon, no browser tab.
- Team split: A firewall, B agents, C app back end, D app shell and red team. Everyone on the front end from H12.
- Worry raised: the four parts were too separate and would be hard to join at H12. Fixes: contracts are pydantic models in `core/contracts/` that everyone imports; the UI's types are generated from the control API; four seams, each with two owners and a test; a walking skeleton through all four parts by H3; `scripts/smoke.py` must pass before every merge; integration checks at H4, H8, H12 on the demo laptop; C is integration lead; from H8 each person owns demo scenes end to end.
- Three processes: app, core (control API plus agent manager), gateway container (firewall plus proxy). All Python in one package.
- Per-person tech stack and the list of files every laptop gets are in project-plan.md sections 8 and 12.

### Nov 14, night (plan finalized)
- Rewrote project-plan.md around the whiteboard design: one container per agent, three guarded doors (files through an I/O tool, network through MCP, volumes through mounts), plus the outbound proxy for model calls.
- Tasks run in a fresh container with per-agent permissions; the container shuts down when the task ends.
- Area C now owns the tray icon and setup popup (app/ folder) as well as the dashboard.

### Nov 14, late evening (scope changes)
- First release: OpenClaw and Hermes only (both run in our containers). Claude Desktop and Muse later.
- App form: backend service + tray icon (Windows and macOS) + setup popup + dashboard as a localhost browser tab.
- Fresh setups only. Migrating existing OpenClaw/Hermes installs is paused for now.
- Memory leak plan: placeholders in memory, separate offline/online memory, labels that follow data, a check when permissions change.
- Old ideation docs moved to _archive/ so they don't steer the build. Name still open (shortlist: Escrow, Terrarium, Customs, Membrane, Floodgate).

### Nov 14, evening (project decided)
- Qualcomm is out (no Uno Q boards left). Dropped Dig Safe, Real Voice and Well Check. Explored Tripwire, Pinpoint, Receipts, Ghost Accounts, Says vs Does, Takeout Dig and Time Dig (docs/ideas-v3.md).
- Checked the Consensus research connector: useful for backing ideas and pitch numbers with papers, not for picking the idea.
- Team idea, chosen: one app to set up, run and connect all your AI agents, with a checkpoint on every bit of data they touch. TDS track plus General. Name not decided.
- Research: firewall pieces already exist for local agents (Claw Patrol, ClawShell, NemoClaw, Aviatrix); placeholder tools exist for developers (Skyflow, PrivAiTe). The gap: one checkpoint across local and cloud agents, for normal people. Muse accepts custom MCP connectors that Meta doesn't review; dots needs ChatGPT Business/Enterprise for custom MCP, so it's a roadmap slide.
- Chose the hybrid: the app runs agents in its own containers (option 1), with a setup wizard that finds already-installed agents and moves them in (from option 2).
- Dropped the hackathon agent board. Each person delegates inside their own area with their own Claude Code; coordination through GitHub issues, PRs, CODEOWNERS and a GitHub Project, plus 5-minute standups.
- Plan of record: docs/project-plan.md. AGENTS.md and CLAUDE.md updated to match.

### Nov 14, after opening ceremony
- 2026 theme: "Let's Dig In" (literal or figurative). Tracks: TDS Privacy & Security, N+1/Qualcomm (Arduino Uno Q, AI that runs fully on the board), Databricks (Free Edition). Everyone is in General; we may enter at most ONE of the three. Submit by Sun noon; judging 1 to 3 PM.
- Ran the ideation flow with real domain research. Full write-up in docs/ideas-v2.md.
- Top pick: Dig Safe (Qualcomm). A camera box on a shovel reads utility paint marks and buzzes before you hit a gas or power line. Works offline.
- Backup: Real Voice. Catches scam-call scripts on a grandparent's phone, on-device. Goes TDS if we don't get an Uno Q.
- Databricks option: Well Check (Wisconsin well nitrate and bacteria risk from DNR data). Only with strict number honesty.
- Dropped: dark-pattern and tracker browser extensions (crowded, free ones already exist).
- To do first thing: confirm we can get an Uno Q at the N+1 table, and get the exact Databricks prompt.

### Nov 14, night
- Saw the 2025 opening slides: opt into at most ONE sponsor track; every project is auto-entered for 1st, 2nd, 3rd and Hacker's Choice; two judging rounds (science fair, then top 6 present again).
- 2026 Devpost rules: no prewritten code; multiple commits within 24 hours with every member contributing; submit on time.
- Board script: do not pre-write it. Either keep the existing board in a separate, unsubmitted coordination repo, or have Claude write it after kickoff. Ask an organizer at check-in.
- Expanded research to 679 winners from 25 US hackathons plus YC and a16z speedrun (winners-research.md). Wrote a general-track shortlist of 8 ideas (idea-playbook.md). Top three: Real Voice, Hands-Free Agent, Room Sense.

### Nov 14, evening
- Decided: Superpowers is our workflow plugin. We want more structure; feature-dev is out.
- Wrote down why we skip ECC, Ruflo, agent teams and llm-council (setup-playbook.md).
- Considering free OpenRouter models (Nvidia Nemotron) for the product's AI calls and side jobs. Corrected one assumption: the data we send does matter in some cases (setup-playbook.md, OpenRouter section).
- Created the project folder `Projects/Hackathons/MadHacks 26` with CLAUDE.md, AGENTS.md, two subagents (verifier, claims-auditor), the humanizer skill, .gitignore, .env.example, and these docs in docs/.

### Nov 14, afternoon
- Checked the Fable 5.2 launch offer: Pro gets Fable included through Nov 16 at 11:59 PM PT, plus one Fable reset each. This covers the hackathon (section 6).
- Researched consensus (debate/council) and delegation agent workflows (section 6).
- Pulled every winner from five fall 2026 hackathons (Cal Hacks 13.0, MHacks 2026, HackGT 13, Knight Hacks IX, HackTX 2026), about 217 projects, and grouped them into idea patterns. Kept in a separate doc: idea-playbook.md.
- Plan for ideation: when the prompt drops, map it onto the winning patterns, but copy how a winner works (the mechanism and demo), not its topic. Line of Sight copied a topic.

### Nov 14, morning
- Agreed we cannot pick an idea until the official prompts or tracks are out. Ideation waits for kickoff.
- Goal for the build: a system that runs on its own as much as possible, with the idea and the presentation as the two things we push hardest.
- Everyone has Claude Pro (3 months). Nobody uses Cursor. So all tooling has to be Claude Code on a Pro plan.
- Decided to keep the humanizer skill on hand so outputs, the Devpost write-up and the pitch read as plain English.
- Audited Line of Sight and Urban Plot (section 3).
- Researched Claude Code tooling (section 6) and what has been winning from summer 2026 to now (section 4).

## 3. What went wrong before

Both projects failed at the same first step. We started from what we had access to (three APIs for Line of Sight, about six datasets for Urban Plot) instead of from the moment we wanted judges to see. Effort spread across many inputs and nothing got deep enough to explain in 90 seconds.

### Line of Sight (MadHacks 2025, Fish Audio track)
The problem was good. TreeHacks 2026's grand prize went to a smart cane for blind users, so the space was not the issue.
- The safety alert ("Stop! car ahead!") went through Fish Audio's cloud API, so the one message that needed to be instant waited on the network. Should have used the phone's built-in voice for alerts.
- The app only described things, every 15 to 30 seconds. Judges at a table could not feel it, so there was no demo moment.
- Two pipelines were built: python_service.dart and the environment-visual Python folder are not connected to the app, and fish_audio_service.dart contains two commented-out older copies.
- main.dart still contains an AI assistant's note: "I am truncating here for brevity, but keep your existing logic!" Code was pasted without being read.
- Logic bug at main.dart line 255: `null || (time > 3 && label != "person")`. The first alert skips the person filter.
- README timings (30s and 60s) do not match the code (15s and 30s).
- Shipped the medium YOLOv8 model (103 MB) on a phone. The nano model would have been faster.
- Devpost listed "combined three APIs" as the main accomplishment, which describes our effort, not what the user gains.

### Urban Plot (MadData 2026)
- No clear identity: folder says UrbanPlot, the repo, title and logo say MadData (the event's own name), the hero heading says "Home", and the README is 75 bytes.
- The site claimed more than the build did. It says sentiment comes from Yelp and Google Reviews; it actually came from Reddit, Isthmus and 2021 meeting transcripts. It promises a heatmap; the map shows dots. It says NLP sorts your business idea; venture.js matches keywords, so "bookstore" becomes "general business" with a demand score of 0.
- "Success Probability" was made up: `25 + raw x 65`, so every score lands between 25% and 90%, with hand-picked weights (60/40 in one script, 40/60 in another) and nothing to check it against. map.html has a hardcoded "Artisan Coffee Shop 94%".
- Bad data: the error log shows the city's average income as about -$15.8 million because Census "missing" codes were not filtered out. The same log shows the pipeline crashing near the end.
- Huge pipeline (370 MB parcels file, 66 MB meeting audio, several scrapers) produced scores for 104 vacant lots for one narrow kind of user.

### Patterns across both
1. Started from inputs, not from the demo.
2. Breadth over depth.
3. Claims ran ahead of the build.
4. The AI produced output to read; it never did anything.
5. No way to show the result was right.
6. Last hours went to firefighting.

## 4. What is winning (summer 2026 to now)

### The clearest current signal: Cal Hacks 13.0 (October 2026)
Presented by Anthropic. About 2,700 hackers, 652 projects, 90 winner labels in the gallery. Patterns among the winners:

- Agents that do a whole job, but ask a human before the risky step. The phrase shows up again and again: "posts only with approval", "asks before acting", "a human approves every action", "fixes it with their OK". Examples: Tariffic (tariff finance desk), DebtPilot (debt autopilot), Docket (caseworker for F-1 students), HAVEN (building safety), Skillsmith (robot skill patching).
- Agents that prove their work. Docket "proves it with the official rule". Quota "explains every number when questioned". Bursar: "nothing moves without proof". Credo: "Don't take its word for it. Watch it." This is the exact opposite of Urban Plot's 94%.
- Red-team agents attacking other agents, then a fix that holds. Fire Drill tricks invoice-paying agents into paying fraudsters, then fixes them. Red Ledger, Agent Credit Exchange ("can't be tricked"), Ender's Bench, Luyten (a Red Team agent critiques the books).
- Autonomous back-office finance: FreightLine, Tariffic, Bursar, Quota, Luyten, Pacioli, moa, Grid Pilot.
- Agentic shopping and negotiation: Fish Market (seller agents bid in sealed rounds), Yardsale (agents price, list and haggle), Hunter, Vouch, Niche.
- Care for older adults and people with disabilities: Rest Easy (agentic pillow), NightFall (dementia wandering), Re:collection (3D memory palace for Alzheimer's), Eleven (ALS), Pupil (eye tracking), Vision OS (blind navigation with touch feedback), Sophi (smart walker), TouchSpace, FortWatch.
- Real world to simulation for robots: RealiSIM (film a table, get a physics sim), Skillsmith, BrickBots.
- Consumer protection: Recount (finds overcharges on ER bills and drafts the letters), Family Shield (stops voice-clone scams), RefundHunter.

### Other recent winners
- HackMIT 2026 (September): grand prize went to Peel, a low-cost device that tests pills to catch fake antimalarial drugs. Healthcare plus hardware.
- Anthropic's Opus 4.8 Build Day (June 2026): 1st Tekton (3D rebuild of Tang Dynasty buildings, every part linked to its historical source, checked by separate verifier agents until 20 tests passed). 2nd Sim Francisco (10,000 synthetic residents from Census data, checked by a verifier agent and an adversarial agent). 3rd Custom Universe (one phone photo to an editable 3D scene for robot training).
- Anthropic's Built with Opus 4.6 (Feb 2026): 1st CrossBeam, by a lawyer, speeds up California housing permits with parallel subagents. Serves builders and city staff.
- TreeHacks 2026 (Feb): grand prize Shepherd, a motorized cane that steers blind users.

### What this means for us
- Autonomy is expected now. What stands out is autonomy you can trust: the agent shows its evidence, a second agent checks it, and a human approves the one step that matters.
- A red-team moment makes a strong live demo: show the attack, then show the system catching it.
- Physical or sensory demos still win grand prizes.

## 5. How judges decide (2026 sources)
- A working live demo beats a bigger idea shown on slides almost every time.
- Say what it does and for whom in the first sentence. Pick one sentence you want a judge to repeat to another judge.
- Show something working within about 90 seconds. One flow, one "this is now possible" moment.
- Remove stall points: mock slow calls, pre-fill forms.
- Be honest about limits. Have an answer ready for "what breaks first?"
- Record a 60-second backup video in case Wi-Fi fails.
- Polish beyond readability, stack choice and team credentials barely move scores.
- Time split that works (TAIKAI guide): about 60% core build, 20% polish, 20% presentation, plus a buffer. Work in 2-hour sprints and cut features when behind.

## 6. Tools for Claude Code

### Our limits
- Claude Pro: a 5-hour session limit and a weekly limit, shared between the Claude app and Claude Code. Each of the 4 of us has our own limits, so we have 4 budgets.
- Fable models are not included in Pro; they run on paid usage credits. Use Opus and Sonnet.
- Parallel agents (Projects threads, agent teams) use up limits much faster. Check with `/usage` and `/status`.
- Windows machines: bash scripts need Git Bash or WSL.

### Fable during the hackathon (limited time)
- Fable 5.2 launched Nov 9. Pro plans get all Fable models included in the plan's weekly limits through Nov 16, 2026 at 11:59 PM PT, up to 50% of the weekly limit. After that, Fable goes back to paid usage credits.
- Each of us also gets one Fable limit reset, which expires at the same time. A reset gives back the Fable usage spent this week and refills the whole 5-hour window, including usage on other models. So it doubles as an emergency refill of the 5-hour limit. Four teammates means four refills.
- Fable uses limits faster than other models. Watch Settings > Usage.
- Claude Code needs version 2.1.321 or later for Fable 5.2. Run `claude update` before kickoff.
- Plan: Fable 5.2 for the hour-1 plan, architecture and hard bugs. Opus or Sonnet for routine building. Each person saves their reset for the late-night crunch, and we stagger them so we never all run dry at once.

### Agent workflows: delegation and consensus
Delegation (split work across workers):
- Subagents: Claude hands a side task to a worker inside one session and gets a summary back.
- Agent view (`claude agents`): hand off independent tasks to background sessions and check one screen for which ones need you. Research preview.
- `/batch`: Claude splits one big change into 5 to 30 subagents, each in its own git worktree.
- Agent teams: a lead assigns work to teammates who share a task list and message each other. Experimental, off by default, teammates do not get separate worktrees.
- hackathon-agent-board: delegation between our four separate machines through a pinned GitHub issue.

Consensus (several agents weigh in, then one answer):
- Dynamic workflows, built into Claude Code: Claude writes a script that runs many subagents and cross-checks them, for example having agents adversarially review each other's findings or drafting a plan from several angles and weighing them. On Pro, turn on "Dynamic workflows" in `/config`. Start one by putting the word `ultracode` in a prompt or saying "use a workflow". On Pro the default size is small (under 5 agents). The built-in `/deep-research` cross-checks sources and votes on each claim. Runs pause and resume if they hit a usage limit.
- Karpathy's llm-council: several different models answer, rank each other's anonymized answers, then a Chairman model writes the final answer. Needs paid OpenRouter credits; not covered by Claude Pro.
- judge-with-debate (NeoLabHQ context-engineering-kit, about 1.7k stars): several judges debate in rounds until they agree.
- Conclave: same-model debate-to-consensus plugin for Claude Code with a visual viewer. New, 0 stars.
- Ruflo (formerly Claude Flow): queen-led swarms with named consensus protocols (Raft, Byzantine and others). A review notes its own audit says the hive-mind still runs in a single process. Heavy; skip for a 24-hour build.

What we will use: dynamic workflows for idea scoring and for the final "find what breaks" sweep, subagents for side tasks, worktrees plus the agent board between teammates. Skip agent teams, Ruflo and llm-council.

### Final setup
The full step-by-step setup, the reasons for each skipped tool, and the OpenRouter rules are in setup-playbook.md. Short version: Superpowers + code-review + frontend-design plugins, dynamic workflows for council decisions, worktrees and subagents on each laptop, hackathon-agent-board between laptops, verifier and claims-auditor subagents, humanizer for all public text. Free OpenRouter models only for the product's AI calls and side jobs, never with real people's data.

### Research notes behind the setup
1. Coordination between our four Claude Code sessions: hackathon-agent-board. One pinned GitHub issue that every teammate's agent posts to. Agents tag each other by GitHub name and `tools/board wait` wakes the tagged agent. Ownership of folders is written in AGENTS.md. Used at Knight Hacks (1,182 posts) and Cal Hacks (988 posts). Needs bash, git and the GitHub CLI. Small repo (2 stars), so read its script before using it.
2. One shared plan: a short PRD plus a ticket list written in hour 1, as Tekton's team did (about 50 tickets, split into parallel work).
3. One workflow plugin: Superpowers (decided). Install: `/plugin install superpowers@claude-plugins-official`. We do not also install feature-dev.
4. Separate checkouts so we never edit the same files: `claude --worktree <name>`.
5. Review before merging: Anthropic's code-review plugin.
6. Good-looking UI: Anthropic's frontend-design plugin.
7. Up-to-date library docs: Context7 MCP.
8. Browser testing of the demo flow: chrome-devtools-mcp or the webapp-testing skill.
9. Two custom subagents we write ourselves:
   - Verifier: runs the tests and the demo flow and reports what fails.
   - Claims auditor: compares every sentence in the UI, README, Devpost and pitch against the code. Fixes the Urban Plot problem.
10. Humanizer skill for the Devpost write-up, README and pitch script.

### Skip or limit
- ECC: about 302k stars, 71 agents, 314 skills, 98 commands. Too much context for a 24-hour build, and it overlaps with Superpowers. Its own docs recommend the plugin install with only `rules/common` if used at all. Do not stack it with Superpowers.
- Agent teams: experimental, off by default, uses limits fast on Pro, and teammates do not get separate worktrees.
- Stacking many plugins: they compete for context and slow Claude down.

## 7. Ideation rules for when the prompts drop
Every idea must pass all five, or we drop it:
1. One-sentence identity: what it does and for whom, under 15 words.
2. A 90-second demo moment judges can see happen.
3. Real autonomy: it does a job by itself; a person only approves.
4. Prize stacking: an overall prize, at least one sponsor track and a category award.
5. Buildable: one end-to-end flow done in about 14 hours.

Build rules:
- Write the demo moment first, then build backward.
- One input, used deeply.
- Every number on screen shows where it came from.
- No claim in the UI, Devpost or pitch that the build cannot back up. One teammate owns this.
- One flow working end to end by about hour 8, features after.
- Name and one-line pitch decided in hour 1. README written as the pitch.
- No pasted code that nobody has read. Tests written alongside features.

## 8. Open items
- Pick the project name at H1 (shortlist in project-plan.md, section 17).
- Fill in the owner table (names and GitHub logins) in AGENTS.md and project-plan.md.
- Create the repo at H0; write the contract models, seam tests and docs/demo-flow.md in hour 1; walking skeleton by H3.
- Run the five hour-1 checks in project-plan.md, section 14.
- Note: sections 6 and 7 above are history from before the project was chosen. The agent board was dropped; project-plan.md is the current plan.

## Sources
- MadHacks: https://www.madhacks.io/ , https://madhacks-fall-2025.devpost.com/project-gallery , https://cai.wisc.edu/2026/01/21/inside-madhacks-the-midwests-premier-hackathon/
- Line of Sight: https://devpost.com/software/line-of-sight
- Cal Hacks 13.0 gallery: https://cal-hacks-13-0.devpost.com/project-gallery
- Cal Hacks 12.0 gallery: https://cal-hacks-12-0.devpost.com/project-gallery
- TreeHacks 2026: https://stanforddaily.com/2026/02/15/12th-annual-treehacks/
- HackMIT 2026: https://www.rit.edu/startupny/news/rit-student-wins-hackmit-low-cost-medicine-testing-device
- Opus 4.8 Build Day winners: https://claude.com/blog/meet-the-winners-of-our-claude-opus-4-8-build-day-hackathon
- Built with Opus 4.6 winners: https://claude.com/resources/articles/meet-the-winners-of-our-built-with-opus-4-6-claude-code-hackathon
- Judging: https://blog.jetbrains.com/ai/2026/06/how-to-win-a-hackathon-notes-from-the-judging-table/ , https://dev.to/kurbaitaev/what-judges-actually-score-notes-from-a-year-of-hackathon-judging-3p4l
- TAIKAI setup guide: https://taikai.network/en/blog/claude-non-developers-hackathon-setup-guide
- hackathon-agent-board: https://github.com/azizu06/hackathon-agent-board
- ECC: https://github.com/affaan-m/ECC
- Claude Code parallel agents: https://code.claude.com/docs/en/agents.md , https://code.claude.com/docs/en/agent-teams
- Pro limits: https://support.claude.com/en/articles/11145838-use-claude-code-with-your-pro-or-max-plan , https://support.claude.com/en/articles/15424964-claude-fable-models-on-your-plan
- Fable 5.2 launch offers: https://support.claude.com/en/articles/17506494-claude-fable-5-2-launch-offers , limit resets: https://support.claude.com/en/articles/17007452-what-is-a-limit-reset
- Dynamic workflows: https://code.claude.com/docs/en/workflows
- llm-council: https://github.com/karpathy/llm-council ; judge-with-debate: https://claudeskills.info/skill/saddjudge-with-debate/ ; Conclave: https://github.com/dyubero/conclave ; Ruflo review: https://alphasignalai.substack.com/p/how-ruflo-turns-claude-code-into
- Fall 2026 galleries: https://mhacks-2026.devpost.com/project-gallery , https://hackgt13.devpost.com/project-gallery , https://knight-hacks-ix.devpost.com/project-gallery , https://hacktx26.devpost.com/project-gallery
- OpenRouter limits: https://openrouter.ai/docs/limits , privacy: https://openrouter.ai/docs/guides/privacy/provider-logging , Nemotron free models: https://openrouter.ai/models/nvidia/nemotron-3-ultra-550b-a55b:free , https://openrouter.ai/models/nvidia/nemotron-3-super-120b-a12b:free
- Plugin roundups: https://claudemarket.ai/blog/best-claude-code-plugins-2026 , https://bito.ai/ai-tools/claude-code-plugins/
