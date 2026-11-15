"""Folder access labels for the popup shown before an agent's first start.

Used by /api/folders (the popup's folder tree) and /api/folder-labels (load and save).

Each agent has its own file, data/agents/<agent>/folder_labels.json:
    {"/Users/you/Documents": "public", "/Users/you/Documents/Taxes": "confidential"}
Only the folders the user clicked are stored. Any other folder takes the label of its
nearest stored parent, or "public" if it has none (the popup's default).
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


def save_labels(agent: str, labels: dict) -> None:
    """Replace this agent's labels. labels: {folder path: "public" | "private" | "confidential"}."""
    manager.profile(agent)
    if not isinstance(labels, dict):
        raise ValueError("labels must be an object of folder path -> label")
    for path, label in labels.items():
        if label not in LABELS:
            raise ValueError(f"label for {path} must be one of: {', '.join(LABELS)}")

    file = AGENTS_DIR / agent / "folder_labels.json"
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(labels, indent=2), encoding="utf-8")
