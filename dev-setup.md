# Dev setup (each person, about 25 minutes)

## Install
1. `claude update` (Fable 5.2 needs Claude Code 2.1.321 or later).
2. Docker Desktop. Windows: turn on WSL 2 when it asks. Check with `docker run hello-world`.
3. Python 3.11, uv, Node 22 LTS (npm comes with it), Git, and the GitHub CLI; run `gh auth login`. Windows: use Git Bash for the commands below.
4. Git: set your own name and email (`git config --global user.name`, `user.email`). Every commit must be under your own name.
5. In Claude Code:
   - `/plugin install superpowers@claude-plugins-official`
   - `/plugin install code-review@claude-plugins-official`
   - `/plugin install frontend-design@claude-plugins-official`
   - In `/config`, turn on Dynamic workflows.

## First run
```
git clone <team repo>
cd <repo>
uv sync                      # Python packages from uv.lock
cd app/ui && npm ci && cd ../..
cp .env.example .env         # then fill in your keys
docker compose build         # gateway and agent images
python scripts/dev.py        # opens the app with everything running
python scripts/smoke.py      # should end with "smoke test passed"
```
The `.claude/` folder (verifier, claims-auditor, humanizer) comes with the clone.

## Secrets
- `.env` holds API keys. Get them from your own account or the team's password-manager share. Never commit `.env`, never paste keys into chat or issues.
- The test Gmail OAuth client file goes in `data/credentials.json` (ignored by git). Only laptops that run the Gmail tool need it.
- No real people's data anywhere. Test Gmail account and made-up files only.

## Models and limits
- Fable 5.2 (included on Pro through Nov 16, 11:59 PM PT, up to 50% of the weekly limit): plans, architecture, hard bugs.
- Opus 5.5 or Sonnet 5.5: routine building.
- Check `/usage` every couple of hours. Each person's Fable reset refills the whole 5-hour window; save it for the night and stagger with teammates.

## Last four hours
1. "use a workflow to run the demo flow end to end, try to break it, and report the top five failures ranked by how likely a judge would hit them."
2. Claims-auditor subagent over UI text, README, Devpost and pitch.
3. Humanizer skill over the Devpost write-up and pitch script.
4. Record a 60-second backup demo video.

## Data rules for the product's AI calls
- The product reads emails and files, so any AI call it makes touches personal data. Use Claude (or another provider that doesn't keep prompts) for those calls.
- Free OpenRouter models are only for our own made-up test data and side jobs. Never send real emails, files, keys or `.env` contents to them.
