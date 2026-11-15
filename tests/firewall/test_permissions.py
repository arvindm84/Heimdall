"""Loading an agent's permissions.json, as B's agent manager writes it."""

import pytest

from core.contracts.agents import AgentPermissions
from core.firewall.permissions import NoPermissions, folder_name, load
from tests.firewall.helpers import FAKE_KEY, write_permissions


def test_loads_permissions_and_run_id(tmp_path):
    write_permissions(tmp_path, AgentPermissions(tools=["files_read"]), run_id="run-7")
    run = load(tmp_path, "openclaw", FAKE_KEY)
    assert run.run_id == "run-7"
    assert run.permissions.tools == ["files_read"]


def test_missing_file_means_no_permissions(tmp_path):
    with pytest.raises(NoPermissions):
        load(tmp_path, "openclaw", FAKE_KEY)


def test_key_must_match_the_file(tmp_path):
    write_permissions(tmp_path, AgentPermissions(), key="sk-fake-other-01")
    with pytest.raises(NoPermissions):
        load(tmp_path, "openclaw", FAKE_KEY)


def test_broken_file_means_no_permissions(tmp_path):
    (tmp_path / "openclaw").mkdir()
    (tmp_path / "openclaw" / "permissions.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(NoPermissions):
        load(tmp_path, "openclaw", FAKE_KEY)


@pytest.mark.parametrize(
    "host_path, name",
    [
        ("C:\\Users\\user\\Documents\\taxes", "taxes"),
        ("C:\\Users\\user\\Documents\\taxes\\", "taxes"),
        ("/home/user/docs", "docs"),
        ("/home/user/docs/", "docs"),
    ],
)
def test_folder_name_is_the_last_part_of_the_host_path(host_path, name):
    assert folder_name(host_path) == name
