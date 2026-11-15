from pydantic import BaseModel


class FolderAccess(BaseModel):
    path: str
    write: bool = False


class AgentPermissions(BaseModel):
    folders: list[FolderAccess] = []
    tools: list[str] = []


class OpenedAgent(BaseModel):
    agent: str
    chat_url: str
    chat_user: str
    chat_token: str
