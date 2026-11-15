"""The user's files, as mounted into the gateway by B's agent manager.

Each allowed folder is at <folders_dir>/<name>, where <name> is the last part of
its host path. Agents address files as "<name>/<path inside it>". Every path is
resolved (following `..` and symlinks) and must stay inside its folder. Only text
and PDF files up to MAX_BYTES are read or written.
"""

import io
import re
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

from core.contracts.agents import AgentPermissions, FolderAccess
from core.firewall.permissions import folder_name

MAX_BYTES = 2 * 1024 * 1024
LIST_LIMIT = 200
WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")


class Denied(Exception):
    """A file operation the gateway refuses. rule_id goes into the event."""

    def __init__(self, rule_id: str, reason: str):
        super().__init__(reason)
        self.rule_id = rule_id
        self.reason = reason


@dataclass(frozen=True)
class Target:
    """Where an agent's path points, after every check passed."""

    path: Path  # resolved, inside base
    folder: str  # the folder's name, as the agent writes it
    access: FolderAccess  # its label and write flag
    base: Path  # the folder's resolved root


def resolve(path: str, permissions: AgentPermissions, root: Path) -> Target:
    """Turn "<folder>/<path>" into a checked Target, or raise Denied."""
    cleaned = path.strip().replace("\\", "/")
    if cleaned.startswith("/") or WINDOWS_DRIVE.match(cleaned):
        raise Denied("path_escapes_folder", "absolute paths are not allowed; use <folder>/<path>")
    parts = [part for part in cleaned.split("/") if part not in ("", ".")]
    if not parts:
        raise Denied("folder_not_permitted", "no folder given; use <folder>/<path>")
    folder, inside = parts[0], parts[1:]
    access = {folder_name(allowed.path): allowed for allowed in permissions.folders}.get(folder)
    if access is None:
        raise Denied("folder_not_permitted", f"{folder} is not one of this agent's folders")
    mount = root / folder
    if not mount.is_dir():
        raise Denied("not_found", f"folder {folder} is not available")
    base = mount.resolve()
    # resolve() follows `..` and symlinks, so this one check covers both ways out.
    target = base.joinpath(*inside).resolve()
    if not target.is_relative_to(base):
        raise Denied("path_escapes_folder", f"{path} points outside folder {folder}")
    return Target(path=target, folder=folder, access=access, base=base)


def list_folders(permissions: AgentPermissions) -> str:
    """One line per allowed folder: name, label, and whether the agent may write to it."""
    lines = [
        f"{folder_name(folder.path)} ({folder.label}, {'writable' if folder.write else 'read only'})"
        for folder in permissions.folders
    ]
    return "\n".join(lines) or "(no folders allowed)"


def list_files(target: Target) -> str:
    """Files under a folder (or a subfolder), as paths the agent can pass to files_read."""
    if not target.path.is_dir():
        raise Denied("not_found", f"{target.folder} has no such folder")
    paths = []
    for entry in sorted(target.path.rglob("*")):
        # Skip folders, and symlinks that lead outside the folder.
        if entry.is_file() and entry.resolve().is_relative_to(target.base):
            paths.append(f"{target.folder}/{entry.relative_to(target.base).as_posix()}")
    if len(paths) > LIST_LIMIT:
        return "\n".join([*paths[:LIST_LIMIT], f"... and {len(paths) - LIST_LIMIT} more files"])
    return "\n".join(paths) or "(empty)"


def read_file(target: Target) -> str:
    """The file's text. PDFs are converted to text; other binary files are refused."""
    if not target.path.is_file():
        raise Denied("not_found", "no such file")
    if target.path.stat().st_size > MAX_BYTES:
        raise Denied("file_too_large", f"file is over {MAX_BYTES // (1024 * 1024)} MB")
    data = target.path.read_bytes()
    if target.path.suffix.lower() == ".pdf":
        return pdf_text(data)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise Denied("not_text", "not a text file") from error
    # Valid UTF-8 can still be binary; a null byte is the usual sign.
    if "\x00" in text:
        raise Denied("not_text", "not a text file")
    return text


def pdf_text(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    # The file comes from the user's disk and may be malformed in any way; pypdf
    # raises many different errors for that. Any failure means "can't read it".
    except Exception as error:  # noqa: BLE001
        raise Denied("not_text", "PDF could not be read") from error


def write_file(target: Target, text: str) -> None:
    """Create or replace a text file. The folder above it must already exist."""
    data = text.encode("utf-8")
    if len(data) > MAX_BYTES:
        raise Denied("file_too_large", f"text is over {MAX_BYTES // (1024 * 1024)} MB")
    if target.path.is_dir():
        raise Denied("not_found", "that path is a folder, not a file")
    if not target.path.parent.is_dir():
        raise Denied("not_found", "the folder for this file does not exist")
    try:
        target.path.write_bytes(data)
    except OSError as error:
        # For example a read-only mount: refuse rather than crash the tool.
        raise Denied("write_failed", "the file could not be written") from error
