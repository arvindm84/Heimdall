"""python -m agents open|stop|kill <agent>"""

import argparse

from agents import manager
from agents.permissions import AgentPermissions, FolderAccess


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m agents")
    commands = parser.add_subparsers(dest="command", required=True)
    open_parser = commands.add_parser("open", help="start an agent with permissions")
    open_parser.add_argument("agent", choices=manager.AGENTS)
    open_parser.add_argument("--tool", action="append", default=[], help="gateway tool to allow")
    open_parser.add_argument("--folder", action="append", default=[], help="folder to allow (read only)")
    open_parser.add_argument("--memory", action="store_true", help="let the agent keep notes (hermes)")
    open_parser.add_argument("--delegation", action="store_true", help="let the agent use subagents (hermes)")
    open_parser.add_argument("--provider", default="gemini", choices=list(manager.PROVIDERS))
    open_parser.add_argument("--model", help="model name; defaults to the small model of the provider")
    for name in ("stop", "kill"):
        commands.add_parser(name).add_argument("agent", choices=manager.AGENTS)
    args = parser.parse_args()

    if args.command == "open":
        permissions = AgentPermissions(
            folders=[FolderAccess(path=path) for path in args.folder],
            tools=args.tool,
            memory=args.memory,
            delegation=args.delegation,
        )
        opened = manager.open_agent(args.agent, permissions, args.provider, args.model)
        print(f"chat:  {opened.chat_url}")
        print(f"user:  {opened.chat_user}")
        print(f"token: {opened.chat_token}")
    elif args.command == "stop":
        manager.stop_agent(args.agent)
    else:
        manager.kill_agent(args.agent)


if __name__ == "__main__":
    main()
