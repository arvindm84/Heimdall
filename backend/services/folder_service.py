"""Folder access labels for the popup shown before an agent's first start.

Used by /api/folders (the popup's folder tree) and /api/folder-labels (load and save).

Each agent has its own file, data/agents/<agent>/folder_labels.json:
    {"/Users/you/Documents": "public", "/Users/you/Documents/Taxes": "confidential"}
Only the folders the user clicked are stored, and only those are shared with the agent
(see granted_folders). In the popup, any other folder shows the label of its nearest
stored parent, or "confidential" if it has none (the popup's default).
No file yet means the user hasn't been asked, so the popup shows.
"""

import json
from pathlib import Path
from typing import get_args

from agents import manager
from core.contracts.agents import FolderAccess

# From the shared contract, never retyped. Its order is least to most strict:
# ("public", "private", "confidential").
LABELS = get_args(FolderAccess.model_fields["label"].annotation)

# The tree starts here. The popup can't look outside it.
HOME = Path.home()
AGENTS_DIR = manager.AGENTS_DIR

# Not shown in the tree: macOS app data, which no agent should get.
SKIPPED = {"Library"}


def list_folders(path: str | None = None) -> dict:
    """The subfolders of a folder inside the home folder, by name.

    Returns {"path": the folder, "folders": [{"name", "path"}]}.
    Hidden folders (.git, .cache...), files and links are left out.
    Raises ValueError for a folder outside home, PermissionError if the system says no.
    """
    folder = (HOME / (path or "")).resolve()
    if folder != HOME.resolve() and HOME.resolve() not in folder.parents:
        raise ValueError("folder must be inside your home folder")
    if not folder.is_dir():
        raise ValueError(f"not a folder: {folder}")

    children = [
        child
        for child in folder.iterdir()
        if not child.name.startswith(".") and child.name not in SKIPPED
        and child.is_dir() and not child.is_symlink()
    ]
    children.sort(key=lambda child: child.name.lower())
    return {"path": str(folder), "folders": [{"name": c.name, "path": str(c)} for c in children]}


def get_labels(agent: str) -> dict | None:
    """The labels saved for this agent, or None if the user hasn't been asked yet."""
    manager.profile(agent)  # ValueError for an unknown agent
    file = AGENTS_DIR / agent / "folder_labels.json"
    if not file.exists():
        return None
    return json.loads(file.read_text(encoding="utf-8"))


def _inside_home(folder: Path) -> bool:
    """True for a folder the popup could show: strictly inside home, not in SKIPPED, and with
    no hidden part (.ssh, .aws, Projects/.git...). Checked after following links."""
    home, folder = HOME.resolve(), folder.resolve()
    if home not in folder.parents:
        return False
    parts = folder.relative_to(home).parts
    return parts[0] not in SKIPPED and not any(part.startswith(".") for part in parts)


def save_labels(agent: str, labels: dict) -> None:
    """Replace this agent's labels. labels: {folder path: "public" | "private" | "confidential"}."""
    manager.profile(agent)
    if not isinstance(labels, dict):
        raise ValueError("labels must be an object of folder path -> label")
    for path, label in labels.items():
        if label not in LABELS:
            raise ValueError(f"label for {path} must be one of: {', '.join(LABELS)}")
        # These paths become folders the agent can read (granted_folders), so the same
        # limits as the popup's tree apply: inside home, nothing hidden.
        folder = Path(path).expanduser()
        if not folder.is_absolute():
            raise ValueError(f"folder path must be absolute: {path}")
        if not _inside_home(folder):
            raise ValueError(f"folder must be inside your home folder, and not hidden: {path}")
    _check_names(agent, labels)

    file = AGENTS_DIR / agent / "folder_labels.json"
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(labels, indent=2), encoding="utf-8")


def _check_names(agent: str, labels: dict) -> None:
    """Refuse two shared folders with the same name, which would make every launch fail.

    The gateway mounts each shared folder by its name alone (~/Work/notes -> /data/folders/notes,
    see agents/manager.py), and one gateway serves every agent, so the names must differ
    across all agents' folders, not just this one's.
    """
    others = [f for other in manager.AGENTS if other != agent for f in granted_folders(other)]
    seen: dict[str, str] = {}
    for folder in [*_granted(labels), *others]:
        name = Path(folder["path"]).name
        first = seen.setdefault(name, folder["path"])
        if first != folder["path"]:
            raise ValueError(
                f"Two shared folders are both named \"{name}\": {first} and {folder['path']}"
                " (folders are shared by name, across all agents). Share only one of them."
            )


def granted_folders(agent: str) -> list[dict]:
    """The folders this agent gets at launch, from its saved labels. See _granted."""
    return _granted(get_labels(agent) or {})


def _granted(labels: dict) -> list[dict]:
    """The folders a set of saved labels grants.

    Returns [{"path", "label", "write": False}], the shape /api/launch takes as config["folders"].
    This is what makes the labels real: the firewall mounts exactly these folders for this
    agent and applies each one's label (placeholders, consent for Confidential...).

    How the popup's tree becomes the firewall's flat list:
    - Only folders the user marked are shared. A folder nobody marked is not shared at all:
      the agent can't see it. So marking just Projects/Heimdall/docs shares that one folder
      and nothing else in Projects.
    - The firewall has one label per shared folder, covering everything inside it. A marked
      folder inside another marked folder is reachable through the outer one, so the outer
      folder takes the strictest label found inside it. Private Documents holding
      Confidential Taxes is shared as Confidential: Taxes can never go out under the
      weaker label.
    - A marked folder with a weaker label than the folder around it is also shared by
      itself, under its own label. Confidential Projects with Public Projects/demo gives
      the agent `demo/...` as Public and `Projects/...` as Confidential. (Reading the same
      file as `Projects/demo/...` counts as Confidential: stricter, never weaker.)
    - Read only. The popup has no "may write" choice yet.
    - Folders deleted since, or outside home, are left out.
    """
    strictness = {label: rank for rank, label in enumerate(LABELS)}

    marked: dict[Path, str] = {}
    for path, label in labels.items():
        folder = Path(path).expanduser()
        if label not in strictness or not folder.is_dir() or not _inside_home(folder):
            continue
        folder = folder.resolve()
        # Two saved paths can be the same folder (a link): keep the stricter label.
        marked[folder] = max(label, marked.get(folder, label), key=strictness.get)

    # The label a folder is shared under: the strictest of its own and every marked folder inside it.
    shared_as = {
        folder: max([label, *(l for other, l in marked.items() if folder in other.parents)], key=strictness.get)
        for folder, label in marked.items()
    }

    granted = []
    for folder in sorted(marked):
        # The nearest marked folder around this one, if any (the longest path among its parents).
        around = max((other for other in marked if other in folder.parents), key=lambda p: len(p.parts), default=None)
        # Inside a folder shared under the same label: already reachable, nothing to add.
        if around is not None and strictness[shared_as[folder]] >= strictness[shared_as[around]]:
            continue
        granted.append({"path": str(folder), "label": shared_as[folder], "write": False})
    return granted
