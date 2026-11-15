"""Route tests for the folder-access popup: listing folders, and saving each agent's labels."""

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
