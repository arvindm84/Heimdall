"""Route tests for the folder-access popup: listing folders, and saving each agent's labels."""

from pathlib import Path

import pytest

from backend.app import app
from backend.services import folder_service


@pytest.fixture
def client():
    return app.test_client()


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A made-up home folder, and labels saved under tmp_path instead of data/."""
    home = tmp_path / "home"
    for name in ("Documents", "Documents/Taxes", "Photos", ".cache", "Library"):
        (home / name).mkdir(parents=True)
    (home / "notes.txt").write_text("not a folder")
    monkeypatch.setattr(folder_service, "HOME", home)
    monkeypatch.setattr(folder_service, "AGENTS_DIR", tmp_path / "agents")
    return home


def test_folders_lists_home_subfolders_without_hidden_ones_or_files(client, home):
    response = client.get("/api/folders")

    assert response.status_code == 200
    assert response.json == {
        "path": str(home),
        "folders": [
            {"name": "Documents", "path": str(home / "Documents")},
            {"name": "Photos", "path": str(home / "Photos")},
        ],
    }


def test_folders_lists_a_subfolder(client, home):
    response = client.get("/api/folders", query_string={"path": str(home / "Documents")})

    assert response.json["folders"] == [{"name": "Taxes", "path": str(home / "Documents" / "Taxes")}]


@pytest.mark.parametrize("path", ["/", "../outside"])
def test_folders_outside_home_get_a_400(client, home, path):
    response = client.get("/api/folders", query_string={"path": path})

    assert response.status_code == 400


def test_labels_are_null_until_saved_then_kept_per_agent(client, home):
    assert client.get("/api/folder-labels", query_string={"agent": "openclaw"}).json == {"labels": None}

    labels = {str(home / "Documents"): "confidential", str(home / "Photos"): "private"}
    saved = client.post("/api/folder-labels", json={"agent": "openclaw", "labels": labels})

    assert saved.status_code == 204
    assert client.get("/api/folder-labels", query_string={"agent": "openclaw"}).json == {"labels": labels}
    # Each agent has its own file, so Hermes still gets the popup.
    assert client.get("/api/folder-labels", query_string={"agent": "hermes"}).json == {"labels": None}


@pytest.mark.parametrize(
    "body",
    [
        {"labels": {}},
        {"agent": "openclaw"},
        {"agent": "nobody", "labels": {}},
        {"agent": "openclaw", "labels": ["not", "a", "dict"]},
        {"agent": "openclaw", "labels": {"/x": "secret"}},
    ],
)
def test_bad_label_saves_get_a_400(client, home, body):
    assert client.post("/api/folder-labels", json=body).status_code == 400


def test_labels_for_an_unknown_agent_get_a_400(client, home):
    assert client.get("/api/folder-labels", query_string={"agent": "nobody"}).status_code == 400


# Labels -> the folders an agent is granted at launch (folder_service.granted_folders).

from agents import manager
from backend.services import agent_service
from core.contracts.agents import OpenedAgent


def save(client, agent, labels):
    assert client.post("/api/folder-labels", json={"agent": agent, "labels": labels}).status_code == 204


def test_only_labelled_folders_are_granted_read_only(client, home):
    save(client, "openclaw", {str(home / "Photos"): "private"})
    assert folder_service.granted_folders("openclaw") == [
        {"path": str((home / "Photos").resolve()), "label": "private", "write": False}
    ]


def test_agent_that_was_never_asked_gets_no_folders(home):
    assert folder_service.granted_folders("hermes") == []


def test_outer_folder_takes_the_strictest_label_inside_it(client, home):
    # The firewall has one label per granted folder. Taxes is reachable through Documents,
    # so Documents must carry Taxes's label, and Taxes isn't granted a second time.
    save(client, "openclaw", {str(home / "Documents"): "private", str(home / "Documents" / "Taxes"): "confidential"})
    assert folder_service.granted_folders("openclaw") == [
        {"path": str((home / "Documents").resolve()), "label": "confidential", "write": False}
    ]


def test_weaker_label_inside_is_also_shared_by_itself_and_does_not_weaken_the_outer_folder(client, home):
    save(client, "openclaw", {str(home / "Documents"): "confidential", str(home / "Documents" / "Taxes"): "public"})
    assert folder_service.granted_folders("openclaw") == [
        {"path": str((home / "Documents").resolve()), "label": "confidential", "write": False},
        {"path": str((home / "Documents" / "Taxes").resolve()), "label": "public", "write": False},
    ]


def test_marking_only_a_subfolder_shares_nothing_else_in_its_parent(client, home):
    save(client, "openclaw", {str(home / "Documents" / "Taxes"): "public"})
    assert folder_service.granted_folders("openclaw") == [
        {"path": str((home / "Documents" / "Taxes").resolve()), "label": "public", "write": False}
    ]


def test_three_levels_keep_the_strictest_label_on_every_way_in(client, home):
    # Confidential Documents > Public Taxes > Private 2024: 2024 is reachable through Taxes,
    # so Taxes is shared as Private (weaker than Documents, so still shared by itself).
    (home / "Documents" / "Taxes" / "2024").mkdir()
    save(client, "openclaw", {
        str(home / "Documents"): "confidential",
        str(home / "Documents" / "Taxes"): "public",
        str(home / "Documents" / "Taxes" / "2024"): "private",
    })
    assert [(Path(f["path"]).name, f["label"]) for f in folder_service.granted_folders("openclaw")] == [
        ("Documents", "confidential"),
        ("Taxes", "private"),
    ]


def test_deleted_folder_is_left_out(client, home):
    save(client, "openclaw", {str(home / "Photos"): "public", str(home / "Documents"): "private"})
    (home / "Photos").rmdir()
    assert [f["path"] for f in folder_service.granted_folders("openclaw")] == [str((home / "Documents").resolve())]


@pytest.mark.parametrize("outside", ["/etc", "..", "Library/Mail"])
def test_labels_outside_home_are_refused(client, home, outside):
    path = outside if outside.startswith("/") else str(home / outside)
    response = client.post("/api/folder-labels", json={"agent": "openclaw", "labels": {path: "public"}})
    assert response.status_code == 400
    assert folder_service.get_labels("openclaw") is None


@pytest.fixture
def opened(monkeypatch):
    """Fake manager.open_agent that records the permissions each agent was opened with."""
    seen = {}

    def open_agent(agent, permissions, provider="gemini", model=None):
        seen[agent] = permissions
        return OpenedAgent(agent=agent, chat_url="http://127.0.0.1:7681/", chat_user="heimdall", chat_token="t")

    monkeypatch.setattr(manager, "open_agent", open_agent)
    monkeypatch.setattr(agent_service.key_service, "put_in_environment", lambda: None)
    return seen


def test_launch_gives_each_agent_its_own_folders(client, home, opened):
    save(client, "openclaw", {str(home / "Photos"): "public"})
    save(client, "hermes", {str(home / "Documents"): "confidential"})

    for agent in ("openclaw", "hermes"):
        assert client.post("/api/launch", json={"agent": agent, "config": {"tools": ["files_read"]}}).status_code == 201

    assert [(f.path, f.label) for f in opened["openclaw"].folders] == [(str((home / "Photos").resolve()), "public")]
    assert [(f.path, f.label) for f in opened["hermes"].folders] == [(str((home / "Documents").resolve()), "confidential")]


def test_folders_in_the_launch_request_win_over_saved_labels(client, home, opened):
    save(client, "openclaw", {str(home / "Photos"): "public"})
    client.post("/api/launch", json={"agent": "openclaw", "config": {"folders": []}})
    assert opened["openclaw"].folders == []


# Review fixes: hidden folders, relative paths and same-named folders are refused on save.

@pytest.mark.parametrize("hidden", [".cache", "Documents/.git"])
def test_hidden_folders_are_refused(client, home, hidden):
    response = client.post("/api/folder-labels", json={"agent": "openclaw", "labels": {str(home / hidden): "public"}})
    assert response.status_code == 400
    assert folder_service.get_labels("openclaw") is None


def test_relative_paths_are_refused(client, home):
    response = client.post("/api/folder-labels", json={"agent": "openclaw", "labels": {"Documents": "public"}})
    assert response.status_code == 400


def test_two_shared_folders_with_the_same_name_are_refused(client, home):
    for parent in ("Work", "School"):
        (home / parent / "notes").mkdir(parents=True)
    labels = {str(home / "Work" / "notes"): "public", str(home / "School" / "notes"): "private"}

    response = client.post("/api/folder-labels", json={"agent": "openclaw", "labels": labels})

    assert response.status_code == 400
    assert 'both named "notes"' in response.json["error"]


def test_same_name_is_refused_across_agents_too(client, home):
    # One gateway serves both agents, so their folder names must differ as well.
    for parent in ("Work", "School"):
        (home / parent / "notes").mkdir(parents=True)
    save(client, "openclaw", {str(home / "Work" / "notes"): "public"})

    response = client.post("/api/folder-labels", json={"agent": "hermes", "labels": {str(home / "School" / "notes"): "public"}})

    assert response.status_code == 400


def test_both_agents_may_share_the_same_folder(client, home):
    save(client, "openclaw", {str(home / "Photos"): "public"})
    save(client, "hermes", {str(home / "Photos"): "private"})
