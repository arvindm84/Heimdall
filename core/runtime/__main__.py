import argparse

from core.contracts.agents import AgentPermissions, FolderAccess
from core.runtime import manager


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m core.runtime")
    commands = parser.add_subparsers(dest="command", required=True)
    open_parser = commands.add_parser("open", help="start an agent with permissions")
    open_parser.add_argument("agent")
    open_parser.add_argument("--tool", action="append", default=[], help="gateway tool to allow")
    open_parser.add_argument("--folder", action="append", default=[], help="folder to allow (read only)")
    for name in ("stop", "kill"):
        commands.add_parser(name).add_argument("agent")
    args = parser.parse_args()

    if args.command == "open":
        permissions = AgentPermissions(
            folders=[FolderAccess(path=path) for path in args.folder], tools=args.tool
        )
        opened = manager.open_agent(args.agent, permissions)
        print(f"chat:  {opened.chat_url}")
        print(f"user:  {opened.chat_user}")
        print(f"token: {opened.chat_token}")
    elif args.command == "stop":
        manager.stop_agent(args.agent)
    else:
        manager.kill_agent(args.agent)


if __name__ == "__main__":
    main()
