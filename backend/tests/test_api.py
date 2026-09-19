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


def demo_branches(client, scenario_id="demo-offer"):
    views = client.get("/branches", params=DEMO).json()["branches"]
    return [v for v in views if v["branch"]["scenario_id"] == scenario_id]


def test_runs_with_llm_off_and_seeds_a_demo(client):
    health = client.get("/health").json()
    assert health["llm_enabled"] is False and health["store"] == "local"
    trunk = client.get("/trunk", params=DEMO).json()
    assert trunk["events"] and trunk["state"]["city"] == "Waterloo"
    assert trunk["agent_log"], "retrieval agent choices are logged"
    big, small = client.get("/scenarios", params=DEMO).json()["scenarios"]
    assert (big["horizon"]["unit"], small["horizon"]) == ("years", {"unit": "days", "count": 7, "tonight": True})
    branches = demo_branches(client)
    assert len(branches) == 2 == len(big["options"]) and all(b["years"] for b in branches)
    assert {b["branch"]["id"] for b in branches} == set(big["branch_ids"])
    assert client.get("/narration", params={"branch_id": branches[0]["branch"]["id"]}).json()["lines"] == {}


def test_tokens_are_enforced(client):
    pid, auth = new_person(client, display_name="Sam")
    other, other_auth = new_person(client)
    assert client.get("/trunk", params={"person_id": pid}, headers=auth).status_code == 200
    assert client.get("/trunk", params={"person_id": pid}, headers={"Authorization": ""}).status_code == 401
    assert client.get("/trunk", params={"person_id": pid}, headers=other_auth).status_code == 403
    assert client.get("/trunk", params={"person_id": "nobody"}, headers=auth).status_code == 401
    branch = new_scenario(client, pid, auth)["branches"][0]["branch"]["id"]
    for path in ("/chapters", "/research", "/narration", "/evidence"):
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


def test_scenario_makes_one_branch_per_option_from_the_persons_words(client):
    pid, auth = new_person(client, birth_year=2003)
    made = new_scenario(client, pid, auth)
    offer, masters = made["branches"]
    assert offer["branch"]["assumption"]["city"] == "San Francisco" and offer["branch"]["params"]["salary"] > 165000
    assert offer["branch"]["precondition"] == "decide_by: 2030-01-01" and offer["branch"]["option_id"]
    assert masters["branch"]["assumption"]["employment"] == "student" and masters["branch"]["params"]["graduates_in"] == 2
    assert masters["years"][0]["state"]["employment"] == "student" and masters["years"][3]["state"]["employment"] == "employed"
    too_few = client.post("/scenarios", json={"person_id": pid, "situation": "x", "options": OPTIONS[:1]}, headers=auth)
    assert too_few.status_code == 422


def test_outlook_says_how_settled_each_aspect_is(client):
    year = demo_branches(client)[0]["years"]
    first, last = year[0]["outlook"], year[-1]["outlook"]
    assert {"alive", "city", "employment", "income_band", "relationship", "housing", "children"} <= set(first)
    assert "promoted_to_senior" in first, "the option's own outcomes sit beside the background aspects"
    allowed = {"almost always", "usually", "as often as not", "sometimes", "rarely"}
    assert all(o["words"] in allowed and 0 <= o["share"] <= 1 and o["value"] for o in first.values())
    assert first["alive"]["words"] == "almost always" and first["alive"]["share"] > last["alive"]["share"]


def test_commit_changes_the_future_and_undo_restores_it_exactly(client):
    pid, auth = new_person(client, birth_year=2003)
    branch = new_scenario(client, pid, auth)["branches"][0]
    bid = branch["branch"]["id"]

    def shape(view):
        return [(y["year"], y["solidity"], y["state"], [e["text"] for e in y["events"]]) for y in view["years"]]

    committed = client.post(f"/branches/{bid}/commits", json={"year": 2031, "message": "Move back to Toronto"}, headers=auth).json()
    assert committed["branch"]["revision"] == 2 and committed["branch"]["commits"][0]["patch"]["city"] == "Toronto"
    in_2031 = next(y for y in committed["years"] if y["year"] == 2031)
    assert in_2031["state"]["city"] == "Toronto" and in_2031["events"][0]["event_type"] == "commit"
    assert committed["branch"]["commits"][0]["at"] == "2031-01-01"
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
    assert client.post(f"/branches/{masters['id']}/commits", json={"year": 2030, "message": "x"}, headers=auth).status_code == 409
    main = client.get("/trunk", params={"person_id": pid}, headers=auth).json()["events"]
    assert [e["event_type"] for e in main] == ["decision"]

    faded_events = [e for y in made["branches"][0]["years"] for e in y["events"]]
    carried = client.post("/carry", json={"branch_id": offer["id"], "event_id": faded_events[0]["id"]}, headers=auth)
    assert carried.status_code == 200 and carried.json()["goal_event"]["event_type"] == "goal"
    assert client.post("/carry", json={"branch_id": offer["id"], "event_id": faded_events[1]["id"]}, headers=auth).status_code == 409


def test_compare_aligns_branches_and_marks_differences(client):
    a, b = (v["branch"]["id"] for v in demo_branches(client))
    result = client.get("/compare", params={"a": a, "b": b}).json()
    assert [c["year"] - result["checkpoints"][0]["year"] for c in result["checkpoints"][:3]] == [0, 5, 10]
    first = {r["aspect"]: r for r in result["checkpoints"][0]["rows"]}
    assert first["city"]["differs"] and {v["value"] for v in first["city"]["values"]} == {"San Francisco", "Waterloo"}
    assert not first["alive"]["differs"] and all(v["words"] for v in first["alive"]["values"])


def test_chapters_and_evidence_work_without_the_llm(client):
    branch = demo_branches(client)[0]
    bid, first_year = branch["branch"]["id"], branch["years"][0]["year"]
    opening = client.get("/chapters", params={"branch_id": bid, "year": first_year}).json()
    assert opening["status"] == "ready" and (opening["from_year"], opening["to_year"]) == (first_year, first_year + 1)
    later = client.get("/chapters", params={"branch_id": bid, "year": first_year + 4}).json()
    assert (later["from_year"], later["to_year"]) == (first_year + 2, first_year + 6) and len(later["paragraphs"]) == 5

    evidence = client.get("/evidence", params={"branch_id": bid}).json()["evidence"]
    kinds = {e["kind"] for e in evidence}
    assert {"researched", "statistic"} <= kinds
    stat = next(e for e in evidence if e["kind"] == "statistic")
    assert "Statistics Canada" in stat["source_title"] and stat["source_url"].startswith("https://www150.statcan")
    cited = {i for ch in (opening, later) for p in ch["paragraphs"] for i in p["evidence_ids"]}
    assert cited <= {e["id"] for e in evidence}
    assert client.get("/research", params={"branch_id": bid}).json()["research"] in ("none", "done")  # "done" when stored research exists


def test_chapter_prose_is_encrypted_at_rest(client):
    from app import db

    branch = demo_branches(client)[0]
    chapter = client.get("/chapters", params={"branch_id": branch["branch"]["id"], "year": branch["years"][0]["year"]}).json()
    stored = db.conn().execute("SELECT doc FROM chapters").fetchone()["doc"]
    assert chapter["paragraphs"][0]["text"][:12] not in stored


CHAT = "\n".join(f"[2026-08-{d:02d}, 9:1{d % 10}:00 PM] {who}: secret words {d}, says Robin"
                 for d in range(1, 29) for who in ("Robin", "Sam Lee", "Priya"))


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
    client.get("/chapters", params={"branch_id": branch, "year": 2030}, headers=auth)

    inventory = client.get("/inventory", params={"person_id": pid}, headers=auth).json()
    assert {s["source"] for s in inventory["sources"]} == {"told", "simulated"} and inventory["stored_nowhere"]

    assert client.post("/erase", json={"person_id": pid, "confirm": "yes"}, headers=auth).status_code == 400
    erased = client.post("/erase", json={"person_id": pid, "confirm": "erase"}, headers=auth).json()["erased"]
    assert erased["events"] > 0 and erased["evidence"] > 0 and erased["branches"] == 2
    assert get_store().events(pid) == [] and get_store().evidence(pid) == [] and db.list_branches(pid) == []
    for table in ("people", "scenarios", "branches", "events", "evidence", "handles"):
        column = "id" if table == "people" else "person_id"
        assert db.conn().execute(f"SELECT COUNT(*) FROM {table} WHERE {column}=?", (pid,)).fetchone()[0] == 0
    assert db.conn().execute("SELECT COUNT(*) FROM chapters WHERE branch_id=?", (branch,)).fetchone()[0] == 0
    assert client.get("/trunk", params={"person_id": pid}, headers=auth).status_code == 401
    assert client.post("/erase", json={"person_id": "demo", "confirm": "erase"}).status_code == 409


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
    assert [y["label"] for y in going["years"][:3]] == ["tonight", "tomorrow", "day 3"]
    assert going["years"][0]["at"] == going["branch"]["forked_at"] and len(going["years"]) == 7
    model = going["branch"]["model"]["events"]
    assert len(model) >= 8 and {e["basis"] for e in model} <= {"estimated", "sourced"}
    assert all(e["words"] in ("rare", "sometimes", "as often as not", "usually", "almost always", "rarely") for e in model)
    happened = [e for y in going["years"] for e in y["events"]]
    assert happened and all(e["payload"]["basis"] in ("estimated", "sourced") for e in happened)
    assert not any(e["payload"].get("basis") == "background" for e in happened), "no life-course on a short horizon"
    outlook = going["years"][-1]["outlook"]
    assert "sleep_under_five_hours" in outlook and "city" not in outlook

    bid = going["branch"]["id"]
    night = client.get("/chapters", params={"branch_id": bid, "at": going["years"][0]["at"]}).json()
    assert night["status"] == "ready" and night["from_at"] == going["years"][0]["at"] and len(night["paragraphs"]) == 7
    assert night["paragraphs"][0]["text"].startswith("tonight — ")


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
    assert first["events"][0]["event_type"] == "commit" and "home_by_eleven" in [e["event_type"] for e in first["events"]]
    assert first["outlook"]["home_by_eleven"]["share"] == 1.0
    undone = client.post(f"/branches/{bid}/undo", json={}).json()
    assert shape(undone) == shape(going)


def test_compare_shows_shared_outcomes_and_what_is_distinctive(client):
    going, staying = demo_branches(client, "demo-tonight")
    result = client.get("/compare", params={"a": going["branch"]["id"], "b": staying["branch"]["id"]}).json()
    assert [c["label"] for c in result["checkpoints"]][0] == "tonight" and result["checkpoints"][-1]["label"] == "day 7"
    rows = {r["aspect"]: r for r in result["checkpoints"][-1]["rows"]}
    assert {"sleep_under_five_hours", "problem_set_on_time", "regret_next_morning"} <= set(rows)
    sleep = {v["branch_id"]: v["share"] for v in rows["sleep_under_five_hours"]["values"]}
    assert sleep[going["branch"]["id"]] > sleep[staying["branch"]["id"]] and rows["sleep_under_five_hours"]["differs"]
    distinct = {(d["branch_id"], d["key"]) for d in result["distinctive"]}
    assert (staying["branch"]["id"], "photos_without_you") in distinct
    assert all(d["basis"] in ("estimated", "sourced") and d["label"] and d["words"] for d in result["distinctive"])


def test_the_rare_life_is_a_different_coherent_life(client):
    going, _ = demo_branches(client, "demo-tonight")
    bid = going["branch"]["id"]
    typical = client.get("/lives", params={"branch_id": bid}).json()
    rare = client.get("/lives", params={"branch_id": bid, "which": "rare"}).json()
    events = lambda life: [e["event_type"] for y in life["years"] for e in y["events"]]
    assert typical["years"] == going["years"] and rare["which"] == "rare" and "rarest" in rare["rarity_words"]
    assert len(events(rare)) >= 2 and events(rare) != events(typical)
    chapter = client.get("/chapters", params={"branch_id": bid, "at": going["years"][0]["at"], "which": "rare"}).json()
    assert chapter["which"] == "rare" and chapter["status"] == "ready"


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
    assert made["branches"][0]["years"][0]["label"] == "tonight" and made["branches"][0]["branch"]["model"]["events"] == []
    fixed = post_scenario(client, auth, {"person_id": pid, "situation": "Should I text my ex tonight?", "options": options,
                                            "horizon": {"unit": "weeks", "count": 6}})
    assert [y["label"] for y in fixed["branches"][0]["years"]] == ["this week", "week 2", "week 3", "week 4", "week 5", "week 6"]


# --- the background tables are weather, not plot (DECISIONS 2.5a) ---

LIFE_SCRIPT = {"marriage", "divorce", "widowed", "birth", "home_purchase"}


def test_life_script_events_are_opt_in(client):
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


def test_background_stays_a_small_share_and_gives_way_to_the_options_own_events(client):
    offer = demo_branches(client)[0]
    events = [e for y in offer["years"] for e in y["events"]]
    own = [e for e in events if e["payload"].get("basis") != "background"]
    background = [e for e in events if e["payload"].get("basis") == "background"]
    assert own and background and len(background) <= max(2, -(-len(own) // 3))
    for year in offer["years"]:
        families = {"career" if e["domain"] in ("work", "learning") else e["domain"] for e in year["events"]
                    if e["payload"].get("basis") != "background"}
        clash = [e for e in year["events"] if e["payload"].get("basis") == "background" and e["domain"] in families
                 and e["event_type"] not in ("death", "parent_death")]
        assert not clash
    evidence = {e["id"]: e for e in client.get("/evidence", params={"branch_id": offer["branch"]["id"]}).json()["evidence"]}
    cited = [evidence[e["payload"]["evidence_id"]] for e in background if e["payload"].get("evidence_id") in evidence]
    assert cited and all(c["reference_class"] == "Canadians of this age, national average" and c["gap"] for c in cited)
    assert "outside Canada" in cited[0]["gap"], "San Francisco: the Canadian tables stay on only with the gap stated"


# --- questions, answers, and many scenarios at once (v2.2) ---


def canned_proposal(question=True):
    from app import llm

    def event(key, label, follow=False):
        return llm.ProposedEvent(key=key, label=label, domain="learning", kind="one_time", first_step=0, last_step=3,
                                 bin="sometimes", depends_on=[], reference_class=None, search_query=None, follow_through=follow)

    return llm.ProposedScenario(
        horizon_unit="years", horizon_count=6, starts_tonight=False,
        options=[llm.ProposedOption(option_index=0, events=[event("coop_term", "you land a co-op term"), event("finish_degree", "you finish the degree", True)]),
                 llm.ProposedOption(option_index=1, events=[event("commute_from_home", "you commute from home"), event("finish_degree", "you finish the degree", True)])],
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

    later = post_scenario(client, auth, {"person_id": pid, "situation": "Residence or commute?", "options": UNIS})
    assert later["questions"] == [], "main now knows the major, so it is not asked again"


def test_a_scenario_can_assume_a_branch_and_scenarios_list_soonest_first(client, monkeypatch):
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
    assert finish["probability"] == round(4 / 6, 4) and finish["band"] > 0
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


def test_background_runs_under_long_month_horizons_only(client):
    pid, auth = new_person(client, birth_year=1990)
    body = lambda count: {"person_id": pid, "situation": "Train for a marathon or not?", "options": UNIS,
                          "horizon": {"unit": "months", "count": count}}
    long = post_scenario(client, auth, body(18))["branches"][0]
    assert len(long["years"]) == 18 and long["years"][0]["label"] == "this month" and "city" in long["years"][0]["outlook"]
    assert long["years"][11]["state"]["age"] + 1 == long["years"][12]["state"]["age"], "one background year per twelve steps"
    dated = [(y["at"][:7], e["date"][:7]) for y in long["years"] for e in y["events"]]
    assert all(a == b for a, b in dated)
    short = post_scenario(client, auth, body(6))["branches"][0]
    assert "city" not in short["years"][0]["outlook"]


def test_the_demo_carries_real_stored_research_rechecked_at_seed_time(client):
    import json
    from app import outcome_model, seed

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
