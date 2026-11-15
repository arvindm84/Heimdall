from typing import Literal

from pydantic import BaseModel


class FolderAccess(BaseModel):
    path: str
    label: Literal["public", "private", "confidential"] = "private"
    write: bool = False


class AgentPermissions(BaseModel):
    folders: list[FolderAccess] = []
    tools: list[str] = []
    memory: bool = False
    delegation: bool = False


class OpenedAgent(BaseModel):
    agent: str
    chat_url: str
    chat_user: str
    chat_token: str
