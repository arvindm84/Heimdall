"""python -m agents open|stop|kill <agent> | skill install|list | memory list|snapshot|rollback"""

import argparse
import json

from agents import manager, skills
from core.contracts.agents import AgentPermissions, FolderAccess


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m agents")
    commands = parser.add_subparsers(dest="command", required=True)
    open_parser = commands.add_parser("open", help="start an agent with permissions")
    open_parser.add_argument("agent", choices=manager.AGENTS)
    open_parser.add_argument("--tool", action="append", default=[], help="gateway tool to allow")
    open_parser.add_argument("--folder", action="append", default=[], help="folder to allow (read only)")
    open_parser.add_argument("--skill", action="append", default=[], help="installed skill to allow (openclaw)")
    open_parser.add_argument("--memory", action="store_true", help="let the agent keep notes (hermes)")
    open_parser.add_argument("--delegation", action="store_true", help="let the agent use subagents (hermes)")
    open_parser.add_argument("--provider", default="gemini", choices=list(manager.PROVIDERS))
    open_parser.add_argument("--model", help="model name; defaults to the small model of the provider")
    for name in ("stop", "kill"):
        commands.add_parser(name).add_argument("agent", choices=manager.AGENTS)
    skill = commands.add_parser("skill", help="scan and install skills").add_subparsers(dest="action", required=True)
    install = skill.add_parser("install", help="scan a skill folder; install it or quarantine it")
    install.add_argument("agent", choices=skills.SUPPORTED)
    install.add_argument("path")
    install.add_argument("--force", action="store_true", help="install even if the scan finds problems")
    skill.add_parser("list").add_argument("agent", choices=skills.SUPPORTED)
    mem = commands.add_parser("memory", help="hermes memory snapshots")
    mem.add_argument("action", choices=["list", "snapshot", "rollback"])
    mem.add_argument("agent", choices=["hermes"])
    mem.add_argument("snapshot", nargs="?", help="snapshot id for rollback")
    args = parser.parse_args()

    if args.command == "open":
        permissions = AgentPermissions(
            folders=[FolderAccess(path=path) for path in args.folder],
            tools=args.tool,
            skills=args.skill,
            memory=args.memory,
            delegation=args.delegation,
        )
        opened = manager.open_agent(args.agent, permissions, args.provider, args.model)
        print(f"chat:  {opened.chat_url}")
        print(f"user:  {opened.chat_user}")
        print(f"token: {opened.chat_token}")
    elif args.command == "skill" and args.action == "install":
        print(json.dumps(skills.install(args.agent, args.path, args.force), indent=2))
    elif args.command == "skill":
        print("\n".join(skills.installed(args.agent)))
    elif args.command == "memory":
        print(manager.memory(args.agent, args.action, *([args.snapshot] if args.snapshot else [])), end="")
    elif args.command == "stop":
        manager.stop_agent(args.agent)
    else:
        manager.kill_agent(args.agent)


if __name__ == "__main__":
    main()
