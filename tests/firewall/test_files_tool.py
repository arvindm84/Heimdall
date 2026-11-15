"""File access inside the mounted folders: path checks, size and type limits."""

import os

import pytest

from core.firewall.permissions import load
from core.firewall.tools import files
from core.firewall.tools.files import Denied
from tests.firewall.helpers import FAKE_KEY, make_world, tiny_pdf


@pytest.fixture
def world(tmp_path):
    settings = make_world(tmp_path)
    return settings, load(settings.agents_dir, "openclaw", FAKE_KEY).permissions


def resolve(world, path):
    settings, permissions = world
    return files.resolve(path, permissions, settings.folders_dir)


def denied_rule(world, path) -> str:
    with pytest.raises(Denied) as error:
        resolve(world, path)
    return error.value.rule_id


def test_reads_a_text_file(world):
    assert "garden opens" in files.read_file(resolve(world, "docs/notes.txt"))


def test_backslashes_work_too(world):
    assert files.read_file(resolve(world, "docs\\sub\\plan.txt")) == "Made-up plan."


def test_reads_a_pdf(world):
    settings, _ = world
    (settings.folders_dir / "taxes" / "tax-2025.pdf").write_bytes(tiny_pdf("Made-up refund 1200"))
    assert "Made-up refund 1200" in files.read_file(resolve(world, "taxes/tax-2025.pdf"))


def test_folder_not_in_permissions_is_denied(world):
    settings, _ = world
    (settings.folders_dir / "secret").mkdir()
    (settings.folders_dir / "secret" / "a.txt").write_text("x")
    assert denied_rule(world, "secret/a.txt") == "folder_not_permitted"


@pytest.mark.parametrize("path", ["docs/../taxes/summary.txt", "docs/../../agents/openclaw/permissions.json"])
def test_dot_dot_cannot_leave_the_folder(world, path):
    assert denied_rule(world, path) == "path_escapes_folder"


@pytest.mark.parametrize("path", ["/etc/passwd", "C:\\Windows\\win.ini", "\\\\server\\share\\a.txt"])
def test_absolute_paths_are_denied(world, path):
    assert denied_rule(world, path) == "path_escapes_folder"


def test_symlink_out_of_the_folder_is_denied(world):
    settings, _ = world
    try:
        os.symlink(settings.folders_dir / "taxes" / "summary.txt", settings.folders_dir / "docs" / "link.txt")
    except OSError:
        pytest.skip("this machine does not allow creating symlinks")
    assert denied_rule(world, "docs/link.txt") == "path_escapes_folder"


def test_missing_file_is_not_found(world):
    with pytest.raises(Denied) as error:
        files.read_file(resolve(world, "docs/nothing.txt"))
    assert error.value.rule_id == "not_found"


def test_folder_permitted_but_not_mounted_is_not_found(tmp_path):
    settings = make_world(tmp_path)
    (settings.folders_dir / "docs" / "notes.txt").unlink()
    (settings.folders_dir / "docs" / "sub" / "plan.txt").unlink()
    (settings.folders_dir / "docs" / "sub").rmdir()
    (settings.folders_dir / "docs").rmdir()
    permissions = load(settings.agents_dir, "openclaw", FAKE_KEY).permissions
    with pytest.raises(Denied) as error:
        files.resolve("docs/notes.txt", permissions, settings.folders_dir)
    assert error.value.rule_id == "not_found"


def test_file_over_the_limit_is_denied(world):
    settings, _ = world
    (settings.folders_dir / "docs" / "big.txt").write_bytes(b"a" * (files.MAX_BYTES + 1))
    with pytest.raises(Denied) as error:
        files.read_file(resolve(world, "docs/big.txt"))
    assert error.value.rule_id == "file_too_large"


@pytest.mark.parametrize("content", [b"\xff\xfe\x00\x01binary", b"text with a \x00 null byte"])
def test_binary_file_is_denied(world, content):
    settings, _ = world
    (settings.folders_dir / "docs" / "blob.bin").write_bytes(content)
    with pytest.raises(Denied) as error:
        files.read_file(resolve(world, "docs/blob.bin"))
    assert error.value.rule_id == "not_text"


def test_broken_pdf_is_denied(world):
    settings, _ = world
    (settings.folders_dir / "docs" / "broken.pdf").write_bytes(b"%PDF-1.4 not really")
    with pytest.raises(Denied) as error:
        files.read_file(resolve(world, "docs/broken.pdf"))
    assert error.value.rule_id == "not_text"


def test_listing_folders_shows_label_and_write(world):
    _, permissions = world
    listing = files.list_folders(permissions)
    assert "docs (private, read only)" in listing
    assert "taxes (confidential, writable)" in listing


def test_listing_a_folder_shows_relative_paths(world):
    listing = files.list_files(resolve(world, "docs")).splitlines()
    assert listing == ["docs/notes.txt", "docs/sub/plan.txt"]


def test_write_creates_a_file(world):
    target = resolve(world, "taxes/new.txt")
    files.write_file(target, "Made-up draft.")
    assert target.path.read_text(encoding="utf-8") == "Made-up draft."


def test_write_needs_an_existing_parent(world):
    with pytest.raises(Denied) as error:
        files.write_file(resolve(world, "taxes/no/such/dir.txt"), "x")
    assert error.value.rule_id == "not_found"


def test_write_over_the_limit_is_denied(world):
    with pytest.raises(Denied) as error:
        files.write_file(resolve(world, "taxes/big.txt"), "a" * (files.MAX_BYTES + 1))
    assert error.value.rule_id == "file_too_large"
