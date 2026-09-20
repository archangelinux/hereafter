"""The app as a real person meets it on a first start: empty.

Nothing is seeded and nothing in the repo is loaded on anyone's behalf. (The test suite's own seeded
person lives in tests/seed_demo.py and is only ever created by the `client` fixture.)
"""

from pathlib import Path


def test_the_app_ships_no_seed_or_sample_data():
    import app

    root = Path(app.__file__).parent
    assert not (root / "seed.py").exists() and not (root / "seed_data").exists() and not (root / "seed_research.py").exists()
    assert not list((root / "agent").glob("fixtures/*.json")), "no built-in test people"


def test_a_fresh_start_holds_nobody_and_nothing(bare_client):
    from app import db

    assert bare_client.get("/health").json()["ok"] is True
    for table in ("people", "scenarios", "branches", "events", "evidence"):
        assert db.conn().execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table
    assert db.get_person("demo") is None


def test_the_old_demo_credentials_open_nothing(bare_client):
    for path in ("/trunk", "/branches", "/scenarios"):
        assert bare_client.get(path, params={"person_id": "demo"}, headers={"Authorization": "Bearer demo"}).status_code == 401


def test_a_new_person_starts_with_an_empty_main_and_no_decisions(bare_client):
    made = bare_client.post("/people", json={"display_name": "Someone"}).json()
    auth, pid = {"Authorization": f"Bearer {made['token']}"}, made["person_id"]
    assert bare_client.get("/trunk", params={"person_id": pid}, headers=auth).json()["events"] == []
    assert bare_client.get("/scenarios", params={"person_id": pid}, headers=auth).json()["scenarios"] == []
    assert bare_client.get("/branches", params={"person_id": pid}, headers=auth).json()["branches"] == []
