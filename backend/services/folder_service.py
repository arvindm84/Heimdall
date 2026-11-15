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

from agents import manager

LABELS = ("public", "private", "confidential")

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
    """True for a folder strictly inside the home folder and outside SKIPPED (after following links)."""
    home, folder = HOME.resolve(), folder.resolve()
    return home in folder.parents and folder.relative_to(home).parts[0] not in SKIPPED


def save_labels(agent: str, labels: dict) -> None:
    """Replace this agent's labels. labels: {folder path: "public" | "private" | "confidential"}."""
    manager.profile(agent)
    if not isinstance(labels, dict):
        raise ValueError("labels must be an object of folder path -> label")
    for path, label in labels.items():
        if label not in LABELS:
            raise ValueError(f"label for {path} must be one of: {', '.join(LABELS)}")
        # These paths become folders the agent can read (granted_folders), so the same
        # limit as the popup's tree applies: nothing outside home.
        if not _inside_home(Path(path)):
            raise ValueError(f"folder must be inside your home folder: {path}")

    file = AGENTS_DIR / agent / "folder_labels.json"
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(labels, indent=2), encoding="utf-8")


def granted_folders(agent: str) -> list[dict]:
    """The folders this agent gets at launch, from its saved labels.

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
    labels = get_labels(agent) or {}
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
