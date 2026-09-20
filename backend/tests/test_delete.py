"""Deleting a decision: its paths and everything written for them go; the past does not.

Runs offline (LLM off, local store) on the `client` fixture, whose seeded test person has an open decision,
a small one, and one already decided.
"""

import pytest

from app import db
from app.models import Evidence, LifeEvent
from app.store import get_store

OPTIONS = [{"title": "Go to the party", "details": ""}, {"title": "Stay in", "details": ""}]


def make(client, situation="The party on Friday, or stay in?", **extra):
    res = client.post("/scenarios", json={"person_id": "demo", "situation": situation, "options": OPTIONS, **extra})
    assert res.status_code == 200, res.text
    return res.json()["scenario"]


def leave_traces(branch_id: str) -> None:
    """Something in every place a path writes to, so deleting has something to prove."""
    store = get_store()
    store.add_evidence([Evidence(id=f"ev-{branch_id}", person_id="demo", branch_id=branch_id, kind="researched", claim="a claim",
                                 source_title="a source", retrieved_at="2026-01-01")])
    store.append([LifeEvent(id=f"sim-{branch_id}", person_id="demo", source="simulated", branch_id=branch_id, date="2026-10-01",
                            domain="growth", event_type="x", text="a simulated moment")])
    db._exec("INSERT OR REPLACE INTO narration VALUES (?,?,?)", (f"n-{branch_id}", branch_id, "a line"))


def footprint(branch_id: str) -> dict[str, int]:
    c = db.conn()
    return {
        "branch": c.execute("SELECT COUNT(*) FROM branches WHERE id=?", (branch_id,)).fetchone()[0],
        "research": c.execute("SELECT COUNT(*) FROM research_steps WHERE branch_id=?", (branch_id,)).fetchone()[0],
        "narration": c.execute("SELECT COUNT(*) FROM narration WHERE branch_id=?", (branch_id,)).fetchone()[0],
        "evidence": len(get_store().evidence("demo", branch_id)),
        "events": len(get_store().events("demo", branch_id)),
    }


def delete(client, scenario_id, **kw):
    return client.post(f"/scenarios/{scenario_id}/delete", **kw)


def test_deleting_removes_the_decision_its_paths_and_everything_written_for_them(client):
    mine = make(client)
    for bid in mine["branch_ids"]:
        leave_traces(bid)
    before = {bid: footprint(bid) for bid in mine["branch_ids"]}
    assert all(all(n > 0 for n in f.values()) for f in before.values()), before

    other = next(s for s in client.get("/scenarios", params={"person_id": "demo"}).json()["scenarios"] if s["id"] != mine["id"] and s["status"] == "open")
    others_before = {bid: footprint(bid) for bid in other["branch_ids"]}
    main_before = [e.id for e in get_store().events("demo")]

    res = delete(client, mine["id"])
    assert res.status_code == 200 and res.json() == {"deleted": {"scenarios": 1, "branches": 2}}
    assert db.get_scenario(mine["id"]) is None
    assert mine["id"] not in [s["id"] for s in client.get("/scenarios", params={"person_id": "demo"}).json()["scenarios"]]
    assert not [v for v in client.get("/branches", params={"person_id": "demo"}).json()["branches"] if v["branch"]["scenario_id"] == mine["id"]]
    for bid in mine["branch_ids"]:
        assert footprint(bid) == {"branch": 0, "research": 0, "narration": 0, "evidence": 0, "events": 0}
    # nothing else was touched: not the other decision, and not main
    assert {bid: footprint(bid) for bid in other["branch_ids"]} == others_before
    assert [e.id for e in get_store().events("demo")] == main_before


def test_what_you_told_hereafter_stays_on_main(client):
    mine = make(client)
    get_store().append([LifeEvent(id="told-1", person_id="demo", source="told", branch_id="main", date="2026-09-20", domain="growth",
                                  event_type="answer", text="Do you want to go? — Yes")])
    assert delete(client, mine["id"]).status_code == 200
    assert "told-1" in [e.id for e in get_store().events("demo")]


def test_a_decision_made_inside_a_path_goes_with_it(client):
    outer = make(client)
    inner = make(client, "Once there: dance, or leave early?", assuming_branch_id=outer["branch_ids"][0])
    assert inner["assuming_branch_id"] == outer["branch_ids"][0]
    res = delete(client, outer["id"])
    assert res.json() == {"deleted": {"scenarios": 2, "branches": 4}}
    assert db.get_scenario(inner["id"]) is None and db.get_scenario(outer["id"]) is None


def test_deleting_the_inner_decision_leaves_the_outer_one(client):
    outer = make(client)
    inner = make(client, "Once there: dance, or leave early?", assuming_branch_id=outer["branch_ids"][0])
    assert delete(client, inner["id"]).json() == {"deleted": {"scenarios": 1, "branches": 2}}
    assert db.get_scenario(outer["id"]) is not None and all(footprint(b)["branch"] == 1 for b in outer["branch_ids"])


def test_a_decision_that_has_been_made_is_refused(client):
    decided = next(s for s in client.get("/scenarios", params={"person_id": "demo"}).json()["scenarios"] if s["status"] == "decided")
    res = delete(client, decided["id"])
    assert res.status_code == 409 and "past" in res.json()["detail"]
    assert db.get_scenario(decided["id"]) is not None


def test_a_decision_made_inside_it_that_is_decided_blocks_the_delete(client):
    outer = make(client)
    inner = make(client, "Once there: dance, or leave early?", assuming_branch_id=outer["branch_ids"][0])
    s = db.get_scenario(inner["id"])
    s.status = "decided"
    db.save_scenario(s)
    assert delete(client, outer["id"]).status_code == 409
    assert db.get_scenario(outer["id"]) is not None and db.get_scenario(inner["id"]) is not None


def test_paths_still_forming_or_being_researched_are_refused(client):
    mine = make(client)
    branch, _ = db.get_branch(mine["branch_ids"][0])
    branch.forming = True
    db.save_branch(branch)
    assert delete(client, mine["id"]).status_code == 409
    branch.forming, branch.research = False, "running"
    db.save_branch(branch)
    assert delete(client, mine["id"]).status_code == 409
    branch.research = "done"
    db.save_branch(branch)
    assert delete(client, mine["id"]).status_code == 200


def test_only_the_owner_can_delete_and_an_unknown_decision_is_a_404(client):
    mine = make(client)
    other = client.post("/people", json={"display_name": "Someone else"}).json()
    assert delete(client, mine["id"], headers={"Authorization": f"Bearer {other['token']}"}).status_code == 403
    assert db.get_scenario(mine["id"]) is not None
    assert delete(client, "nope").status_code == 404


def test_deleting_twice_is_a_404_not_a_crash(client):
    mine = make(client)
    assert delete(client, mine["id"]).status_code == 200
    assert delete(client, mine["id"]).status_code == 404


@pytest.mark.parametrize("branch_id", ["main", "", None])
def test_the_store_never_deletes_anything_on_main(client, branch_id):
    get_store().append([LifeEvent(id="keep-me", person_id="demo", source="told", branch_id="main", date="2026-09-20", domain="growth", event_type="note")])
    get_store().delete_branches("demo", [branch_id])
    assert "keep-me" in [e.id for e in get_store().events("demo")]
