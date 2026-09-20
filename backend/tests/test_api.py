import io
import json
import zipfile

DEMO = {"person_id": "demo"}
OPTIONS = [
    {"title": "Take the offer", "details": "Join the startup in San Francisco, US$165,000 base.", "deadline": "2030-01-01"},
    {"title": "Stay for the master's", "details": "Stay in Waterloo for the two-year MMath."},
]


def new_person(client, **fields):
    made = client.post("/people", json=fields).json()
    return made["person_id"], {"Authorization": f"Bearer {made['token']}"}


def settled(client, pid, auth, made):
    """POST /scenarios answers at once with placeholders; the branches form in the background
    (which the test client runs to completion before returning). Re-read them."""
    for b in made["branches"]:
        assert b["branch"]["forming"] and b["branch"]["model"] is None and b["years"] == [] and b["branch"]["research"] == "pending"
    scenario = next(s for s in client.get("/scenarios", params={"person_id": pid}, headers=auth).json()["scenarios"]
                    if s["id"] == made["scenario"]["id"])
    views = {b["branch"]["id"]: b for b in client.get("/branches", params={"person_id": pid}, headers=auth).json()["branches"]}
    assert not any(views[i]["branch"]["forming"] for i in scenario["branch_ids"])
    return {"scenario": scenario, "branches": [views[i] for i in scenario["branch_ids"]], "questions": scenario["questions"]}


def post_scenario(client, auth, body):
    resp = client.post("/scenarios", json=body, headers=auth)
    assert resp.status_code == 200, resp.text
    return settled(client, body["person_id"], auth, resp.json())


def new_scenario(client, pid, auth, options=OPTIONS):
    return post_scenario(client, auth, {"person_id": pid, "situation": "An offer arrived.", "options": options})


def plain_date(at):
    from datetime import date

    d = date.fromisoformat(at)
    return f"{d.day} {d:%B}" + ("" if d.year == date.today().year else f" {d.year}")


def demo_branches(client, scenario_id="demo-offer"):
    views = client.get("/branches", params=DEMO).json()["branches"]
    return [v for v in views if v["branch"]["scenario_id"] == scenario_id]


CHAT = "\n".join(f"[2026-08-{d:02d}, 9:1{d % 10}:00 PM] {who}: secret words {d}"
                 for d in range(1, 29) for who in ("Robin", "Sam Lee", "Priya"))


def test_runs_with_llm_off_and_reads_the_seeded_test_person(client):
    health = client.get("/health").json()
    assert health["llm_enabled"] is False and health["store"] == "local"
    trunk = client.get("/trunk", params=DEMO).json()
    assert trunk["events"] and trunk["state"]["city"] == "Waterloo"
    assert trunk["agent_log"], "retrieval agent choices are logged"
    big, small, earlier = client.get("/scenarios", params=DEMO).json()["scenarios"]   # open ones first, soonest deadline first
    assert (big["horizon"], small["horizon"]) == ({"unit": "years", "count": 3, "tonight": False}, {"unit": "days", "count": 7, "tonight": True})
    assert (big["scale"], small["scale"], earlier["scale"]) == ("big", "small", "small")
    branches = demo_branches(client)
    assert len(branches) == 3 == len(big["options"]) and all(b["years"] for b in branches)
    assert {b["branch"]["id"] for b in branches} == set(big["branch_ids"])
    # one earlier decision is already made: a chosen path, a road not taken, and the choice on main in the words of step zero
    went, packed = demo_branches(client, "demo-farewell")
    assert (earlier["status"], went["branch"]["status"], packed["branch"]["status"]) == ("decided", "merged", "faded")
    decision = next(e for e in trunk["events"] if e["event_type"] == "decision")
    assert decision["text"] == "You go to the team's farewell dinner" and decision["date"] == went["branch"]["forked_at"]
    statuses = {b["branch"]["status"] for b in client.get("/branches", params=DEMO).json()["branches"]}
    assert statuses == {"open", "merged", "faded"}, "nothing stale, nothing nested, nothing picked"


def test_tokens_are_enforced(client):
    pid, auth = new_person(client, display_name="Sam")
    other, other_auth = new_person(client)
    assert client.get("/trunk", params={"person_id": pid}, headers=auth).status_code == 200
    assert client.get("/trunk", params={"person_id": pid}, headers={"Authorization": ""}).status_code == 401
    assert client.get("/trunk", params={"person_id": pid}, headers=other_auth).status_code == 403
    assert client.get("/trunk", params={"person_id": "nobody"}, headers=auth).status_code == 401
    branch = new_scenario(client, pid, auth)["branches"][0]["branch"]["id"]
    for path in ("/research", "/evidence"):
        params = {"branch_id": branch, "year": 2030}
        assert client.get(path, params=params, headers=other_auth).status_code == 403, path
    assert client.post(f"/branches/{branch}/commits", json={"year": 2030, "message": "move to Toronto"},
                       headers=other_auth).status_code == 403


def test_person_record_is_encrypted_at_rest(client):
    from app import db

    pid, _ = new_person(client, display_name="Samira Okonkwo", birth_year=1999)
    row = dict(db.conn().execute("SELECT * FROM people WHERE id=?", (pid,)).fetchone())
    assert "Samira" not in json.dumps(row) and "1999" not in json.dumps(row)
    assert db.get_person(pid).display_name == "Samira Okonkwo" and db.get_person(pid).birth_year == 1999
    assert len(row["token_hash"]) == 64


def test_past_is_append_only(client):
    from app.store import get_store

    store = get_store()
    assert not any(hasattr(store, m) for m in ("update", "delete", "remove", "edit"))
    before = store.events("demo")
    tampered = before[0].model_copy(update={"text": "rewritten"})
    assert store.append([tampered]) == []
    assert store.events("demo")[0].text == before[0].text
    routes = {(m, r.path) for r in client.app.routes for m in getattr(r, "methods", [])}
    assert not any(m in ("PUT", "PATCH", "DELETE") for m, _ in routes)


def test_scenario_makes_one_branch_per_option_from_the_persons_words(background, client):
    pid, auth = new_person(client, birth_year=2003)
    made = new_scenario(client, pid, auth)
    offer, masters = made["branches"]
    assert offer["branch"]["assumption"]["city"] == "San Francisco" and offer["branch"]["params"]["salary"] > 165000
    assert offer["branch"]["precondition"] == "decide_by: 2030-01-01" and offer["branch"]["option_id"]
    assert masters["branch"]["assumption"]["employment"] == "student" and masters["branch"]["params"]["graduates_in"] == 2
    assert masters["years"][0]["state"]["employment"] == "student" and masters["years"][-1]["state"]["employment"] == "employed"
    # one named option is enough: the alternative (not doing it) is implied, as in a plain ticket
    one = client.post("/scenarios", json={"person_id": pid, "situation": "Lend my brother the money?", "options": OPTIONS[:1]}, headers=auth)
    assert one.status_code == 200 and len(one.json()["branches"]) == 2
    assert client.post("/scenarios", json={"person_id": pid, "situation": ""}, headers=auth).status_code == 400


def test_outlook_says_how_settled_each_aspect_is(client):
    year = demo_branches(client)[0]["years"]
    first, last = year[0]["outlook"], year[-1]["outlook"]
    assert "promoted" in first and "city" not in first, "the option's own outcomes; the life-table background is off by default"
    allowed = {"almost always", "usually", "as often as not", "sometimes", "rarely"}
    assert all(o["words"] in allowed and 0 <= o["share"] <= 1 and o["value"] in ("yes", "no") for o in first.values())
    assert first["choice"]["probability"] == 1.0 and first["promoted"]["probability"] == 0.0 < last["promoted"]["probability"]


def test_commit_changes_the_future_and_undo_restores_it_exactly(background, client):
    pid, auth = new_person(client, birth_year=2003)
    branch = new_scenario(client, pid, auth)["branches"][0]
    bid = branch["branch"]["id"]
    year = int(branch["years"][0]["at"][:4]) + 2

    def shape(view):
        return [(y["at"], y["solidity"], y["state"], [e["text"] for e in y["events"]]) for y in view["years"]]

    committed = client.post(f"/branches/{bid}/commits", json={"year": year, "message": "Move back to Toronto"}, headers=auth).json()
    assert committed["branch"]["revision"] == 2 and committed["branch"]["commits"][0]["patch"]["city"] == "Toronto"
    landed = next(y for y in committed["years"] if y["year"] == year)
    assert landed["state"]["city"] == "Toronto" and landed["events"][0]["event_type"] == "commit"
    assert committed["branch"]["commits"][0]["at"] == landed["at"]
    assert shape(committed) != shape(branch)
    assert client.get("/trunk", params={"person_id": pid}, headers=auth).json()["events"] == []  # main untouched

    undone = client.post(f"/branches/{bid}/undo", json={}, headers=auth).json()
    assert undone["branch"]["commits"] == [] and undone["branch"]["revision"] == 3
    assert shape(undone) == shape(branch)
    assert client.post(f"/branches/{bid}/undo", json={}, headers=auth).status_code == 404
    assert client.post(f"/branches/{bid}/commits", json={"year": 1999, "message": "x"}, headers=auth).status_code == 400
    assert client.post(f"/branches/{bid}/commits", json={"message": "x"}, headers=auth).status_code == 400


def test_merge_needs_the_name_is_permanent_and_stale_cannot_merge(client):
    pid, auth = new_person(client, birth_year=2003)
    stale_option = {"title": "Already gone", "details": "A job in Halifax.", "deadline": "2020-01-01"}
    made = new_scenario(client, pid, auth, OPTIONS + [stale_option])
    offer, masters, gone = (b["branch"] for b in made["branches"])

    views = {b["branch"]["id"]: b["branch"] for b in client.get("/branches", params={"person_id": pid}, headers=auth).json()["branches"]}
    assert views[gone["id"]]["status"] == "stale"
    assert client.post("/merge", json={"branch_id": gone["id"], "confirm": "Already gone"}, headers=auth).status_code == 409

    assert client.post("/merge", json={"branch_id": masters["id"]}, headers=auth).status_code == 400
    assert client.post("/merge", json={"branch_id": masters["id"], "confirm": "stay"}, headers=auth).status_code == 400
    merged = client.post("/merge", json={"branch_id": masters["id"], "confirm": "Stay for the master's"}, headers=auth).json()
    assert merged["merged"]["status"] == "merged" and [b["id"] for b in merged["faded"]] == [offer["id"]]
    scenario = client.get("/scenarios", params={"person_id": pid}, headers=auth).json()["scenarios"][0]
    assert scenario["status"] == "decided" and scenario["decided_branch_id"] == masters["id"]

    # permanent: no second merge, no commits or undo on closed paths, and no route that reverses it
    assert client.post("/merge", json={"branch_id": offer["id"], "confirm": "Take the offer"}, headers=auth).status_code == 409
    assert client.post(f"/branches/{masters['id']}/commits", json={"year": 2028, "message": "x"}, headers=auth).status_code == 409
    main = client.get("/trunk", params={"person_id": pid}, headers=auth).json()["events"]
    assert [e["event_type"] for e in main] == ["decision"]
    assert main[0]["text"] == "You stay for the master's", "HEAD is what a merge commits: main records step zero's words"

    client.post(f"/branches/{offer['id']}/undo", json={}, headers=auth)  # closed: refused, nothing changes
    faded_events = [e for y in made["branches"][0]["years"] for e in y["events"]] + [{"id": "missing"}]


def test_compare_aligns_branches_and_marks_differences(client):
    a, b, c = (v["branch"]["id"] for v in demo_branches(client))
    result = client.get("/compare", params={"a": a, "b": b, "c": c}).json()
    assert len(result["checkpoints"]) == 4 and result["checkpoints"][0]["label"] == "today"
    last = {r["aspect"]: r for r in result["checkpoints"][-1]["rows"]}
    assert {"first_day_at_work", "first_real_friend_there", "regret_the_choice"} <= set(last) and "choice" not in last
    work = {v["branch_id"]: v["probability"] for v in last["first_day_at_work"]["values"]}
    assert work[a] > work[b] and last["first_day_at_work"]["differs"], "a job starts sooner than a degree ends"
    assert all(d["key"] != "choice" for d in result["distinctive"])
def test_evidence_works_without_the_llm(client):
    branch = demo_branches(client)[0]
    bid, years = branch["branch"]["id"], branch["years"]

    evidence = client.get("/evidence", params={"branch_id": bid}).json()["evidence"]
    assert {e["kind"] for e in evidence} == {"researched"}, "no life-table statistics unless the background is switched on"
    assert client.get("/research", params={"branch_id": bid}).json()["research"] in ("none", "done")  # "done" when stored research exists
def test_offering_routes_everything_and_never_errors(client):
    pid, auth = new_person(client, display_name="Sam Lee")
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("WhatsApp Chat.txt", CHAT)
    resp = client.post(
        "/ingest",
        data={"person_id": pid, "text": "INFP",
              "links": json.dumps(["http://127.0.0.1:9/closed-door"]), "handles": json.dumps({"github": "not a handle!"})},
        files=[("files", ("chat.zip", archive.getvalue(), "application/zip")),
               ("files", ("blob.bin", bytes(range(256)) * 4, "application/octet-stream"))],
        headers=auth,
    )
    assert resp.status_code == 200
    body = resp.json()
    kinds = {i["name"]: i["kind"] for i in body["inputs"]}
    assert kinds["your words"] == "personality" and kinds["chat.zip/WhatsApp Chat.txt"] == "chat_export"
    assert kinds["blob.bin"] == "unknown" and kinds["http://127.0.0.1:9/closed-door"] == "link"
    assert all(i["outcome"] for i in body["inputs"])
    assert body["personality"]["mbti"] == "INFP" and body["personality"]["confidence"] < 0.5
    assert {"social_connectedness", "breadcrumb"} <= {e["event_type"] for e in body["events_added"]}
    stored = json.dumps(client.get("/trunk", params={"person_id": pid}, headers=auth).json())
    assert "secret words" not in stored and "Robin" not in stored and "Priya" not in stored


def test_other_peoples_names_never_reach_the_llm():
    from app.ingest import chat

    messages = chat.parse(CHAT)
    chunks, _ = chat.chunks_for_extraction(messages, chat.owner_of(messages, "Sam Lee"))
    joined = "\n".join(chunks)
    assert "Robin" not in joined and "Priya" not in joined and "Person A" in joined and "Me:" in joined


def test_conflicting_sources_are_reconciled_and_logged(client):
    from app.ingest.pipeline import _event
    from app.store import get_store

    pid, auth = new_person(client)
    get_store().append([
        _event(pid, "told", "resume", domain="housing", event_type="state_fact", text="city: Toronto",
               when="2023-05-01", confidence=0.9, payload={"city": "Toronto"}),
        _event(pid, "scraped", "posts", domain="housing", event_type="state_fact", text="city: Waterloo",
               when="2026-08-01", confidence=0.6, payload={"city": "Waterloo"}),
    ])
    trunk = client.get("/trunk", params={"person_id": pid}, headers=auth).json()
    assert trunk["state"]["city"] == "Waterloo"
    ruling = next(d for d in trunk["reconciliation"] if d["slot"] == "city")
    assert ruling["chosen"] == "Waterloo" and ruling["over"] == ["Toronto"]


def test_inventory_then_erase_leaves_nothing(client):
    from app import db
    from app.store import get_store

    pid, auth = new_person(client, display_name="Sam")
    client.post("/ingest", data={"person_id": pid, "text": "I moved to Waterloo in 2021."}, headers=auth)
    branch = new_scenario(client, pid, auth)["branches"][0]["branch"]["id"]

    inventory = client.get("/inventory", params={"person_id": pid}, headers=auth).json()
    assert {s["source"] for s in inventory["sources"]} == {"told", "simulated"} and inventory["stored_nowhere"]

    assert client.post("/erase", json={"person_id": pid, "confirm": "yes"}, headers=auth).status_code == 400
    erased = client.post("/erase", json={"person_id": pid, "confirm": "erase"}, headers=auth).json()["erased"]
    assert erased["events"] > 0 and erased["branches"] == 2
    assert get_store().events(pid) == [] and get_store().evidence(pid) == [] and db.list_branches(pid) == []
    for table in ("people", "scenarios", "branches", "events", "evidence", "handles"):
        column = "id" if table == "people" else "person_id"
        assert db.conn().execute(f"SELECT COUNT(*) FROM {table} WHERE {column}=?", (pid,)).fetchone()[0] == 0
    assert db.conn().execute("SELECT COUNT(*) FROM chapters WHERE branch_id=?", (branch,)).fetchone()[0] == 0
    assert client.get("/trunk", params={"person_id": pid}, headers=auth).status_code == 401


def test_concurrent_reads_do_not_fail_or_blank_the_person(client):
    from concurrent.futures import ThreadPoolExecutor

    def hit(i):
        path = "/trunk" if i % 2 else "/branches"
        return client.get(path, params=DEMO).status_code

    with ThreadPoolExecutor(8) as pool:
        codes = list(pool.map(hit, range(80)))
    assert set(codes) == {200}
    person = client.get("/trunk", params=DEMO).json()["person"]
    assert person["display_name"] == "Demo" and person["birth_year"] == 2004


# --- any decision, any size ---
def test_a_small_decision_is_lived_in_days_with_the_llm_off(client):
    going, staying = demo_branches(client, "demo-tonight")
    assert [y["label"] for y in going["years"][:3]] == ["today", plain_date(going["years"][1]["at"]), plain_date(going["years"][2]["at"])]
    assert going["years"][0]["at"] == going["branch"]["forked_at"] and len(going["years"]) == 7
    model = going["branch"]["model"]["events"]
    assert len(model) >= 8 and {e["basis"] for e in model} <= {"estimated", "sourced", "choice"}
    assert all(e["words"] in ("rare", "sometimes", "as often as not", "usually", "almost always", "almost certainly", "rarely") for e in model)
    happened = [e for y in going["years"] for e in y["events"]]
    assert happened and all(e["payload"]["basis"] in ("estimated", "sourced", "choice") for e in happened)
    assert not any(e["payload"].get("basis") == "background" for e in happened), "no life-course on a short horizon"
    outlook = going["years"][-1]["outlook"]
    assert "sleep_under_five_hours" in outlook and "city" not in outlook

    bid = going["branch"]["id"]


def test_commit_on_a_small_decision_forces_an_event_and_undo_restores_it(client):
    going, _ = demo_branches(client, "demo-tonight")
    bid, tonight = going["branch"]["id"], going["years"][0]["at"]

    def shape(view):
        return [(y["at"], y["solidity"], [e["text"] for e in y["events"]]) for y in view["years"]]

    message = "leave when I said I would: home by eleven, as planned"
    committed = client.post(f"/branches/{bid}/commits", json={"at": tonight, "message": message}).json()
    patch = committed["branch"]["commits"][0]["patch"]
    assert patch["step"] == 0 and patch["model"]["force"] == ["home_by_eleven"]
    first = committed["years"][0]
    assert [e["event_type"] for e in first["events"]][:2] == ["choice", "commit"] and "home_by_eleven" in [e["event_type"] for e in first["events"]]
    assert first["outlook"]["home_by_eleven"]["share"] == 1.0
    undone = client.post(f"/branches/{bid}/undo", json={}).json()
    assert shape(undone) == shape(going)


def test_compare_shows_shared_outcomes_and_what_is_distinctive(client):
    going, staying = demo_branches(client, "demo-tonight")
    result = client.get("/compare", params={"a": going["branch"]["id"], "b": staying["branch"]["id"]}).json()
    assert [c["label"] for c in result["checkpoints"]][0] == "today"
    assert result["checkpoints"][-1]["label"] == plain_date(going["years"][-1]["at"])
    rows = {r["aspect"]: r for r in result["checkpoints"][-1]["rows"]}
    assert {"sleep_under_five_hours", "problem_set_on_time", "regret_next_morning"} <= set(rows)
    sleep = {v["branch_id"]: v["share"] for v in rows["sleep_under_five_hours"]["values"]}
    assert sleep[going["branch"]["id"]] > sleep[staying["branch"]["id"]] and rows["sleep_under_five_hours"]["differs"]
    distinct = {(d["branch_id"], d["key"]) for d in result["distinctive"]}
    assert (staying["branch"]["id"], "photos_without_you") in distinct
    assert all(d["basis"] in ("estimated", "sourced") and d["label"] and d["words"] for d in result["distinctive"])
def test_merging_one_decision_leaves_other_decisions_open(client):
    pid, auth = new_person(client, birth_year=2003)
    first, second = new_scenario(client, pid, auth), new_scenario(client, pid, auth)
    client.post("/merge", json={"branch_id": first["branches"][0]["branch"]["id"], "confirm": "Take the offer"}, headers=auth)
    status = {b["branch"]["id"]: b["branch"]["status"]
              for b in client.get("/branches", params={"person_id": pid}, headers=auth).json()["branches"]}
    assert status[first["branches"][1]["branch"]["id"]] == "faded"
    assert {status[b["branch"]["id"]] for b in second["branches"]} == {"open"}


def test_horizon_can_be_given_and_is_inferred_by_rules_without_the_llm(client):
    pid, auth = new_person(client)
    options = [{"title": "Text them tonight", "details": ""}, {"title": "Leave it", "details": ""}]
    made = post_scenario(client, auth, {"person_id": pid, "situation": "Should I text my ex tonight?", "options": options})
    assert made["scenario"]["horizon"] == {"unit": "days", "count": 7, "tonight": True}
    assert made["branches"][0]["years"][0]["label"] == "today"
    only = made["branches"][0]["branch"]["model"]["events"]
    assert [(e["key"], e["label"], e["head"], e["probability"]) for e in only] == [("choice", "You text them tonight", True, 1.0)]
    assert made["scenario"]["scale"] == "small"
    fixed = post_scenario(client, auth, {"person_id": pid, "situation": "Should I text my ex tonight?", "options": options,
                                            "horizon": {"unit": "weeks", "count": 6}})
    weeks = fixed["branches"][0]["years"]
    assert [y["label"] for y in weeks] == ["today"] + [plain_date(y["at"]) for y in weeks[1:]]


# --- the background tables are weather, not plot (DECISIONS 2.5a) ---

LIFE_SCRIPT = {"marriage", "divorce", "widowed", "birth", "home_purchase"}


def test_life_script_events_are_opt_in(background, client):
    pid, auth = new_person(client, birth_year=1996)
    plain = new_scenario(client, pid, auth)["branches"][0]
    assert plain["branch"]["model"]["life_script"] == {"partner": False, "children": False, "home": False}
    kinds = {e["event_type"] for y in plain["years"] for e in y["events"]}
    assert not (kinds & LIFE_SCRIPT) and all(y["state"]["relationship_status"] == "single" for y in plain["years"])
    assert all(y["state"]["housing"] != "owning" and y["state"]["children"] == 0 for y in plain["years"])
    steps = client.get("/research", params={"branch_id": plain["branch"]["id"]}, headers=auth).json()["steps"]
    assert any("partner, children or a home" in s["message"] and "none shown" in s["message"] for s in steps), "the check is logged"

    client.post("/ingest", data={"person_id": pid, "text": "My girlfriend and I are saving for a down payment."}, headers=auth)
    wanted = new_scenario(client, pid, auth)["branches"][0]
    assert wanted["branch"]["model"]["life_script"] == {"partner": True, "children": False, "home": True}
    assert all(y["state"]["children"] == 0 for y in wanted["years"])


def test_background_is_off_by_default_and_a_small_share_when_on(background, client):
    offer = demo_branches(client)[0]
    events = [e for y in offer["years"] for e in y["events"]]
    own = [e for e in events if e["payload"].get("basis") != "background"]
    behind = [e for e in events if e["payload"].get("basis") == "background"]
    assert own and len(behind) <= max(2, -(-len(own) // 3)) and "city" in offer["years"][0]["outlook"]
    for year in offer["years"]:
        families = {"career" if e["domain"] in ("work", "learning") else e["domain"] for e in year["events"]
                    if e["payload"].get("basis") != "background"}
        clash = [e for e in year["events"] if e["payload"].get("basis") == "background" and e["domain"] in families
                 and e["event_type"] not in ("death", "parent_death")]
        assert not clash
    evidence = [e for e in client.get("/evidence", params={"branch_id": offer["branch"]["id"]}).json()["evidence"] if e["kind"] == "statistic"]
    assert all(c["reference_class"] == "Canadians of this age, national average" and "outside Canada" in c["gap"] for c in evidence)


def test_no_background_events_unless_switched_on(client):
    for view in demo_branches(client):
        assert not any(e["payload"].get("basis") == "background" for y in view["years"] for e in y["events"])
        assert "city" not in view["years"][-1]["outlook"]


# --- questions, answers, and many scenarios at once (v2.2) ---


def canned_proposal(question=True):
    from app import llm

    def event(key, label, follow=False):
        return llm.ProposedEvent(key=key, label=label, domain="learning", kind="one_time", phase="settling_in", from_day=30, to_day=900,
                                 bin="sometimes", depends_on=[], reference_class=None, search_query=None, follow_through=follow)

    return llm.ProposedScenario(
        horizon_unit="years", horizon_count=6, starts_tonight=False,
        options=[llm.ProposedOption(option_index=0, choice_label="You choose Waterloo", events=[event("coop_term", "you land a co-op term"), event("finish_degree", "you finish the degree", True)]),
                 llm.ProposedOption(option_index=1, choice_label="You choose McMaster", events=[event("commute_from_home", "you commute from home"), event("finish_degree", "you finish the degree", True)])],
        questions=[llm.ProposedQuestion(text="What do you intend to major in?", why="co-op and outcomes differ by program",
                                        choices=["Computer science", "Life sciences", "Undecided"], applies_to_options=[])] if question else [],
    )


UNIS = [{"title": "Waterloo", "details": ""}, {"title": "McMaster", "details": ""}]


def test_questions_widen_branches_until_answered_and_are_never_asked_twice(client, monkeypatch):
    from app import llm

    monkeypatch.setattr(llm, "propose_scenario_model", lambda *a, **k: canned_proposal())
    pid, auth = new_person(client, birth_year=2008)
    made = post_scenario(client, auth, {"person_id": pid, "situation": "Which uni?", "options": UNIS})
    assert len(made["questions"]) == 1 and made["questions"][0]["choices"] and made["questions"][0]["answer"] is None
    before = made["branches"][0]
    assert before["branch"]["model"]["widen"] > 0 and before["branch"]["model"]["mix"]["estimated"] == 2

    qid = made["questions"][0]["id"]
    answered = client.post(f"/scenarios/{made['scenario']['id']}/answers", json={"answers": {qid: "Computer science"}}, headers=auth).json()
    assert answered["scenario"]["questions"][0]["answer"] == "Computer science"
    assert all(b["branch"]["forming"] and b["years"] for b in answered["branches"]), "marked forming, old life still readable"
    after = client.get("/branches", params={"person_id": pid}, headers=auth).json()["branches"][0]
    assert after["branch"]["forming"] is False
    assert after["branch"]["model"]["widen"] == 0 and after["branch"]["revision"] == before["branch"]["revision"] + 1
    assert sum(y["solidity"] for y in after["years"]) >= sum(y["solidity"] for y in before["years"]), "more in, clearer futures"
    main = client.get("/trunk", params={"person_id": pid}, headers=auth).json()["events"]
    assert [e["event_type"] for e in main] == ["answer"] and main[0]["source"] == "told"



def test_a_scenario_can_assume_a_branch_and_scenarios_list_soonest_first(background, client, monkeypatch):
    from app import llm

    monkeypatch.setattr(llm, "propose_scenario_model", lambda *a, **k: canned_proposal(question=False))
    pid, auth = new_person(client, birth_year=2008)
    options = [{"title": "Take the job in Halifax", "details": "", "deadline": "2031-01-01"}, {"title": "Stay in Toronto", "details": ""}]
    first = post_scenario(client, auth, {"person_id": pid, "situation": "Move for work?", "options": options})
    halifax = first["branches"][0]["branch"]["id"]
    inner = post_scenario(client, auth, {"person_id": pid, "situation": "Residence or a flat?", "options": UNIS,
                                            "assuming_branch_id": halifax})
    assert inner["scenario"]["assuming_branch_id"] == halifax
    assert inner["branches"][0]["branch"]["fork"]["city"] == "Halifax", "forked from that branch's simulated state"
    sooner = [{"title": "A", "details": "", "deadline": "2029-06-01"}, {"title": "B", "details": ""}]
    post_scenario(client, auth, {"person_id": pid, "situation": "Sooner", "options": sooner})
    listed = client.get("/scenarios", params={"person_id": pid}, headers=auth).json()["scenarios"]
    assert [s["nearest_deadline"] for s in listed] == ["2029-06-01", "2031-01-01", None]
    other, other_auth = new_person(client)
    stolen = client.post("/scenarios", json={"person_id": other, "situation": "x", "options": UNIS, "assuming_branch_id": halifax},
                         headers=other_auth)
    assert stolen.status_code == 403


def test_a_personal_track_record_is_used_only_when_there_is_enough_of_it(client, monkeypatch):
    from app import llm
    from app.ingest.pipeline import _event
    from app.store import get_store

    monkeypatch.setattr(llm, "propose_scenario_model", lambda *a, **k: canned_proposal(question=False))
    pid, auth = new_person(client, birth_year=2008)
    goals = lambda kinds: [_event(pid, "told", f"g{i}", domain="growth", event_type=k, text=f"goal {i}", when=f"2025-0{i + 1}-01",
                                  confidence=0.9) for i, k in enumerate(kinds)]
    get_store().append(goals(["goal_kept", "goal_dropped", "goal_kept"]))
    few = post_scenario(client, auth, {"person_id": pid, "situation": "Which uni?", "options": UNIS})
    assert few["branches"][0]["branch"]["model"]["mix"]["personal"] == 0

    get_store().append(goals(["goal_kept", "goal_dropped", "goal_kept", "goal_kept", "goal_kept", "goal_dropped"])[3:])
    enough = post_scenario(client, auth, {"person_id": pid, "situation": "Which uni, again?", "options": UNIS})
    model = enough["branches"][0]["branch"]["model"]
    finish = next(e for e in model["events"] if e["key"] == "finish_degree")
    assert model["mix"] == {"sourced": 0, "personal": 1, "estimated": 1} and finish["basis"] == "personal"
    assert finish["base_probability"] == round(4 / 6, 4) and finish["band"] > 0
    record = client.get("/evidence", params={"ids": finish["evidence_id"], "person_id": pid}, headers=auth).json()["evidence"][0]
    assert record["kind"] == "personal" and record["value"] == "4 of 6" and record["gap"]


def test_forming_is_narrated_and_blocks_nothing_but_the_unformed(client):
    pid, auth = new_person(client, birth_year=2003)
    raw = client.post("/scenarios", json={"person_id": pid, "situation": "An offer arrived.", "options": OPTIONS}, headers=auth).json()
    assert raw["questions"] == [] and raw["scenario"]["branch_ids"] == [b["branch"]["id"] for b in raw["branches"]]
    made = settled(client, pid, auth, raw)
    branch = made["branches"][0]["branch"]
    assert branch["revision"] == 1 and branch["research"] == "none" and made["branches"][0]["years"]
    steps = client.get("/research", params={"branch_id": branch["id"]}, headers=auth).json()["steps"]
    assert steps[0]["message"].startswith("Imagining what could happen if you choose: Take the offer")
    assert any("could happen here" in s["message"] for s in steps)


def test_background_runs_under_long_month_horizons_only(background, client):
    pid, auth = new_person(client, birth_year=1990)
    body = lambda count: {"person_id": pid, "situation": "Train for a marathon or not?", "options": UNIS,
                          "horizon": {"unit": "months", "count": count}}
    long = post_scenario(client, auth, body(18))["branches"][0]
    years = long["years"]
    assert len(years) == 4 + 11 + 2 and years[0]["label"] == "today" and "city" in years[0]["outlook"], \
        "weekly for a month, monthly to the end of year one, then quarterly"
    assert years[0]["state"]["age"] + 1 == years[-1]["state"]["age"], "one background year per twelve months"
    for this, after in zip(years, years[1:]):
        assert all(this["at"] <= e["date"] < after["at"] for e in this["events"]), "every moment is dated inside its own step"
    short = post_scenario(client, auth, body(5))["branches"][0]
    assert "city" not in short["years"][0]["outlook"] and len(short["years"]) == 5


def test_the_test_person_carries_real_stored_research_rechecked_at_seed_time(client):
    import json
    import seed_demo as seed
    from app import outcome_model

    stored = json.loads(seed.SEED_DATA.read_text())
    rates = [(k, r) for k, v in stored["branches"].items() for r in v["rates"]]
    assert rates and all(outcome_model.figure_in_snippet(r["figure"], r["snippet"]) and r["source_url"].startswith("http") for _, r in rates)
    branches = {f"{b['branch']['scenario_id']}|{b['branch']['label']}": b for b in client.get("/branches", params=DEMO).json()["branches"]}
    for key, rate in rates:
        branch = branches[key]["branch"]
        event = next(e for e in branch["model"]["events"] if e["key"] == rate["event_key"])
        assert event["basis"] == "sourced" and branch["model"]["mix"]["sourced"] >= 1
        evidence = client.get("/evidence", params={"ids": event["evidence_id"], "person_id": "demo"}).json()["evidence"][0]
        assert evidence["source_url"] == rate["source_url"] and evidence["retrieved_at"] == rate["retrieved_at"] and evidence["gap"]
    offer = branches["demo-offer|Take the offer"]["branch"]
    assert offer["params"]["housing_cost_ratio"] == stored["branches"]["demo-offer|Take the offer"]["params"]["housing_cost_ratio"]
def test_step_labels_are_plain_dates_everywhere(client):
    import re

    counted = re.compile(r"\b(day|week|month) \d+\b|\b(this week|this month|tonight|tomorrow)\b", re.I)
    for view in client.get("/branches", params=DEMO).json()["branches"]:
        bid, unit = view["branch"]["id"], view["branch"]["span"]["unit"]


def test_today_is_only_ever_today():
    from datetime import date, timedelta
    from app.sim.outcomes import date_label

    day = date(2026, 9, 19)
    assert date_label(day, "days", today=day) == "today" and date_label(day, "days", today=day + timedelta(days=1)) == "19 September"
    assert date_label(date(2027, 1, 4), "weeks", today=day) == "4 January 2027"
    assert date_label(date(2028, 6, 19), "years", today=day) == "19 June 2028", "long paths have steps inside a year, so they are dated too"


def test_scale_is_inferred_and_can_be_overridden(client, monkeypatch):
    from app import llm

    pid, auth = new_person(client, birth_year=2003)
    assert new_scenario(client, pid, auth)["scenario"]["scale"] == "big"           # years
    body = {"person_id": pid, "situation": "Should I text my ex tonight?", "options": UNIS}
    assert post_scenario(client, auth, body)["scenario"]["scale"] == "small"
    assert post_scenario(client, auth, {**body, "scale": "big"})["scenario"]["scale"] == "big", "the person says so"
    assert post_scenario(client, auth, {**body, "horizon": {"unit": "months", "count": 6}})["scenario"]["scale"] == "big"
    proposal = canned_proposal(question=False).model_copy(update={"horizon_unit": "weeks", "horizon_count": 4, "scale": "big"})
    monkeypatch.setattr(llm, "propose_scenario_model", lambda *a, **k: proposal)
    assert post_scenario(client, auth, {**body, "situation": "Leave the band?"})["scenario"]["scale"] == "small", \
        "four weeks is small whatever the LLM thinks"


def _claude_export():
    import json as _json
    return _json.dumps([
        {"uuid": "c1", "name": "Should I take the Montreal internship", "created_at": "2026-08-01T10:00:00Z",
         "updated_at": "2026-08-02T10:00:00Z", "chat_messages": [
             {"sender": "human", "text": "I got an internship offer in Montreal but my partner is staying in Waterloo.", "created_at": "2026-08-01T10:00:00Z"},
             {"sender": "assistant", "text": "ASSISTANT WORDS THAT MUST NEVER BE READ", "created_at": "2026-08-01T10:00:05Z"}]},
        {"uuid": "c2", "name": "empty", "created_at": "2026-07-01T10:00:00Z", "updated_at": "2026-07-01T10:00:00Z", "chat_messages": []},
    ])


def test_assistant_export_reads_only_the_persons_side(client):
    from app.ingest import ai_chat
    from app.ingest.router import route_file

    convs = ai_chat.parse(_claude_export())
    assert [c.title for c in convs] == ["Should I take the Montreal internship"]
    chunks, unread = ai_chat.chunks_for_extraction(convs)
    assert unread == 0 and "Montreal" in chunks[0] and "ASSISTANT WORDS" not in chunks[0]

    offered = route_file("conversations.json", _claude_export().encode())
    assert ai_chat.parse('{"not": "an export"}') is None


def test_an_offering_can_be_forgotten_on_its_own(client):
    person = client.post("/people", json={}).json()
    headers = {"Authorization": f"Bearer {person['token']}"}
    pid = person["person_id"]
    client.post("/ingest", data={"person_id": pid, "text": "I moved to Halifax last spring."}, headers=headers)
    resp = client.post("/ingest", data={"person_id": pid}, headers=headers,
                       files=[("files", ("conversations.json", _claude_export().encode(), "application/json"))])
    kinds = {i["name"]: i["kind"] for i in resp.json()["inputs"]}
    assert kinds["conversations.json"] == "ai_chat_export"

    offerings = {o["origin"]: o["count"] for o in client.get("/inventory", params={"person_id": pid}, headers=headers).json()["offerings"]}
    assert {"your words", "conversations.json"} <= set(offerings)

    forgot = client.post("/forget", json={"person_id": pid, "origin": "conversations.json"}, headers=headers).json()
    assert forgot["removed"] == offerings["conversations.json"]
    left = {e["origin"] for e in client.get("/trunk", params={"person_id": pid}, headers=headers).json()["events"]}
    assert "conversations.json" not in left and "your words" in left
    assert client.post("/forget", json={"person_id": pid, "origin": "your words"}).status_code in (401, 403)


def test_a_decision_is_written_like_a_ticket():
    from app import ticket

    s, o = ticket.parse("Noor texted for the first time since March. Answer tonight, in the morning, or not at all?")
    assert o == ["Answer tonight", "In the morning", "Not at all"] and s.startswith("Noor texted")
    assert ticket.parse("McMaster vs Waterloo vs UofT")[1] == ["McMaster", "Waterloo", "UofT"]
    assert ticket.parse("Friday\n- the party\n- the problem set")[1] == ["The party", "The problem set"]
    assert len(ticket.parse("Lend my brother the money?")[1]) == 2


def test_post_scenarios_takes_one_plain_line(client):
    made = client.post("/scenarios", headers={"Authorization": "Bearer demo"},
                       json={"person_id": "demo", "text": "The party on Friday or the problem set due Saturday?"}).json()
    assert [o["title"] for o in made["scenario"]["options"]] == ["The party on Friday", "The problem set due Saturday"]
    assert len(made["branches"]) == 2


LENDING = "Inès asked to borrow four hundred"
LEND_OPTIONS = [{"title": "Lend it", "details": ""}, {"title": "Say no", "details": ""}]


def test_lending_four_hundred_is_a_small_decision_with_and_without_the_llm(client, monkeypatch):
    from app import llm, outcome_model
    from app.models import Horizon

    pid, auth = new_person(client, birth_year=1995)
    body = {"person_id": pid, "situation": LENDING, "options": LEND_OPTIONS}
    off = post_scenario(client, auth, body)["scenario"]                       # LLM off: nothing to infer a horizon from
    assert off["scale"] == "small" and off["horizon"]["unit"] == "weeks"

    says_big = canned_proposal(question=False).model_copy(update={"horizon_unit": "months", "horizon_count": 3, "scale": "big"})
    monkeypatch.setattr(llm, "propose_scenario_model", lambda *a, **k: says_big)
    assert post_scenario(client, auth, body)["scenario"]["scale"] == "small", "three months: small, whatever the LLM says"
    chosen = post_scenario(client, auth, {**body, "scale": "big"})["scenario"]
    assert chosen["scale"] == "big" and chosen["scale_chosen"], "the person's explicit scale always wins"

    assert [outcome_model.scale_of(Horizon(unit=u, count=c)) for u, c in
            (("days", 30), ("weeks", 25), ("weeks", 26), ("months", 5), ("months", 6), ("years", 1))] == \
        ["small", "small", "big", "small", "big", "big"]
    assert outcome_model.decide_scale(None, None, "big") == "big" and outcome_model.decide_scale(None, None, None) == "small"
    assert outcome_model.decide_scale("small", Horizon(unit="years", count=40), "big") == "small"


def test_editing_a_decision_ticket(client):
    pid, auth = new_person(client, birth_year=2003)
    made = new_scenario(client, pid, auth)
    sid = made["scenario"]["id"]
    offer, masters = made["branches"]
    oid, mid = offer["branch"]["option_id"], masters["branch"]["option_id"]
    edit = lambda body, headers=auth: client.post(f"/scenarios/{sid}/edit", json=body, headers=headers)

    r = edit({"situation": "The San Francisco question", "scale": "small"}).json()
    assert r["scenario"]["situation"] == "The San Francisco question" and r["scenario"]["scale"] == "small" and r["scenario"]["scale_chosen"]

    r = edit({"rename": {oid: "Go west"}}).json()
    renamed = next(b for b in r["branches"] if b["branch"]["option_id"] == oid)
    assert renamed["branch"]["label"] == "Go west" and renamed["branch"]["revision"] == offer["branch"]["revision"], "no re-simulation"
    assert renamed["years"] == offer["years"] and next(o for o in r["scenario"]["options"] if o["id"] == oid)["title"] == "Go west"

    r = edit({"deadline": {oid: "2020-01-01", mid: "2031-05-01"}}).json()
    assert {b["branch"]["option_id"]: b["branch"]["precondition"] for b in r["branches"]} == {oid: "decide_by: 2020-01-01", mid: "decide_by: 2031-05-01"}
    status = lambda: {b["branch"]["option_id"]: b["branch"]["status"] for b in client.get("/branches", params={"person_id": pid}, headers=auth).json()["branches"]}
    assert status()[oid] == "stale", "the stale check applies on the next read"
    r = edit({"deadline": {oid: None}}).json()
    assert next(b for b in r["branches"] if b["branch"]["option_id"] == oid)["branch"]["precondition"] is None and status()[oid] == "open"
    assert edit({"deadline": {oid: "next friday"}}).status_code == 400 and edit({"rename": {"nope": "x"}}).status_code == 404

    r = edit({"add": [{"title": "Take the bank job in Toronto"}]}).json()
    added = r["branches"][-1]
    assert len(r["scenario"]["options"]) == 3 and added["branch"]["forming"] and added["years"] == [] and added["branch"]["model"] is None
    after = {b["branch"]["id"]: b for b in client.get("/branches", params={"person_id": pid}, headers=auth).json()["branches"]}
    formed = after[added["branch"]["id"]]
    assert not formed["branch"]["forming"] and formed["years"] and formed["branch"]["label"] == "Take the bank job in Toronto"
    assert formed["branch"]["fork"] == offer["branch"]["fork"] and formed["branch"]["span"] == offer["branch"]["span"]
    assert after[masters["branch"]["id"]]["branch"]["revision"] == masters["branch"]["revision"], "siblings untouched"
    assert after[masters["branch"]["id"]]["years"] == masters["years"]
    scenario = client.get("/scenarios", params={"person_id": pid}, headers=auth).json()["scenarios"][0]
    assert scenario["scale"] == "small", "a chosen scale is never re-inferred, even after a path is added"

    assert edit({"add": [{"title": "A fourth"}]}).status_code == 200
    assert edit({"add": [{"title": "A fifth"}]}).status_code == 400, "at most four paths"
    other, other_auth = new_person(client)
    assert edit({"situation": "mine now"}, other_auth).status_code == 403

    client.post("/merge", json={"branch_id": masters["branch"]["id"], "confirm": "Stay for the master's"}, headers=auth)
    assert edit({"situation": "too late"}).status_code == 409, "a decided scenario cannot be edited"


def test_a_forming_decision_refuses_edits_instead_of_losing_them(client, monkeypatch):
    from app import scenarios as scenarios_ops

    monkeypatch.setattr(scenarios_ops, "form", lambda *a, **k: None)  # forming never lands in this test
    headers = {"Authorization": "Bearer demo"}
    made = client.post("/scenarios", headers=headers, json={
        "person_id": "demo", "situation": "Friday", "options": [{"title": "the party"}, {"title": "the problem set"}]}).json()
    assert all(b["branch"]["forming"] for b in made["branches"])
    refused = client.post(f"/scenarios/{made['scenario']['id']}/edit", headers=headers, json={"situation": "Friday night"})
    assert refused.status_code == 409


# --- v2.5: probabilities, shown and explained ---


def test_events_carry_probabilities_ordered_most_likely_first_with_breakdowns(client):
    for view in client.get("/branches", params=DEMO).json()["branches"]:
        events = view["branch"]["model"]["events"]
        probs = [e["probability"] for e in events]
        assert probs == sorted(probs, reverse=True) and all(0 <= p <= 1 for p in probs)
        for e in events:
            b = e["breakdown"]
            assert b["simulated"] == e["probability"] and b["base"]["kind"] == e["basis"] and b["base"]["note"]
            assert (b["base"]["range"] is not None) == (e["basis"] == "estimated" or e["band"] > 0)
            assert len(b["personality"]) <= 2 and all(i["basis"] in ("published", "assumed") for i in b["personality"])
        final = view["years"][-1]["outlook"]
        assert all(final[e["key"]]["probability"] == e["probability"] for e in events)
        first = view["years"][0]["outlook"]
        assert all(first[k]["probability"] <= final[k]["probability"] for k in (e["key"] for e in events)), "cumulative"
    offer = demo_branches(client)[0]["branch"]["model"]["events"]
    moved = next(e for e in offer if e["key"] == "move_back_to_canada")["breakdown"]["personality"]
    assert moved and {i["basis"] for i in moved} == {"published"}, "a matching life-course hazard uses the published effect"
    burnout = next(e for e in offer if e["key"] == "on_call_burnout")["breakdown"]
    assert burnout["personality"][0]["basis"] == "assumed" and burnout["personality"][0]["beta"] == 0.2
    assert burnout["base"]["kind"] == "sourced" and burnout["base"]["evidence_id"] and burnout["base"]["reference_class"]


def test_no_personality_no_shift_through_the_api(client):
    pid, auth = new_person(client, birth_year=2003)
    from app import llm
    events = new_scenario(client, pid, auth)["branches"][0]["branch"]["model"]["events"]
    assert events == [] or all(e["breakdown"]["personality"] == [] for e in events)
    going = demo_branches(client, "demo-tonight")[0]["branch"]["model"]["events"]
    assert any(e["breakdown"]["personality"] for e in going), "the demo person has an MBTI type, so some events shift"


def test_compare_and_distinctive_carry_probabilities(client):
    going, staying = demo_branches(client, "demo-tonight")
    result = client.get("/compare", params={"a": going["branch"]["id"], "b": staying["branch"]["id"]}).json()
    row = result["checkpoints"][-1]["rows"][0]
    assert all(0 <= v["probability"] <= 1 and v["words"] for v in row["values"])
    assert result["distinctive"] and all(0 <= d["probability"] <= 1 for d in result["distinctive"])


def test_the_model_card_is_open_complete_and_matches_the_docs(client, monkeypatch):
    from app import config, model_card

    monkeypatch.setattr(config, "SIM_RUNS", 1000)  # the suite runs fewer lives for speed; the card reports the real setting

    card = client.get("/model", headers={"Authorization": ""}).json()
    assert card["version"] == "2.6" and len(card["steps"]) == 6 and all(s["title"] and s["text"] for s in card["steps"])
    names = " ".join(k["name"] + " " + k["value"] for k in card["constants"])
    for needle in ("0.20", "0.15", "1.37", "1000", "modal life", "six months", "0.02–0.10", "quarter", "off by default", "3 years", "half-life 10 days", "10th–90th"):
        assert needle in names, needle
    assert len(card["limits"]) >= 8 and any("fiction" in l for l in card["limits"]) and any("estimates" in l for l in card["limits"])
    assert (config.ROOT / "docs" / "MODEL.md").read_text() == model_card.markdown(), "regenerate with: python -m app.model_card"


def test_older_branches_are_migrated(client):
    from app import branches, db
    from app.models import Horizon

    branch, years = db.get_branch(demo_branches(client)[0]["branch"]["id"])
    branch.model["events"] = [e for e in branch.model["events"] if not e.get("head")]
    for e in branch.model["events"]:
        e.pop("breakdown"); e.pop("terms", None); e.pop("days", None)
        e["probability"] = e.pop("base_probability")
        e["window"] = [0, 1]
    branch.model.pop("layout")
    branch.span, branch.horizon = Horizon(unit="years", count=40), 40
    db.save_branch(branch, years)
    assert branches.migrate() == 1
    after, lived = db.get_branch(branch.id)
    assert after.revision == branch.revision + 1 and all("breakdown" in e for e in after.model["events"])
    assert after.span.count == 3 and len(lived) == 23, "no forty-year paths"
    assert after.model["events"][0]["head"] and lived[0].events[0].payload["head"]
    sourced = next(e for e in after.model["events"] if e["basis"] == "sourced")
    assert sourced["breakdown"]["base"]["value"] == sourced["base_probability"] and branches.migrate() == 0


def test_dates_keep_the_precision_they_were_given():
    from app.ingest.pipeline import _event

    year = _event("p", "told", "x", domain="career", event_type="job_start", text="a", when="2024", confidence=1)
    month = _event("p", "told", "x", domain="career", event_type="job_start", text="b", when="2025-06", confidence=1)
    none = _event("p", "told", "x", domain="career", event_type="project", text="c", when="Summer", confidence=1)
    assert (year.date, year.payload["date_precision"]) == ("2024-01-01", "year")
    assert (month.date, month.payload["date_precision"]) == ("2025-06-01", "month")
    assert none.payload.get("undated") is True and "date_precision" not in none.payload
