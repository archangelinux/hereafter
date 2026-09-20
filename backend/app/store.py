"""The life-event store. Elasticsearch when configured, a SQLite stand-in otherwise.

Both expose the same small surface: `append` (create-only — there is deliberately no update
or delete, which is what makes the past immutable) plus the query tools the retrieval agent
chooses between when it builds a state vector.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Protocol

from . import config, db
from .models import Evidence, LifeEvent

log = logging.getLogger("hereafter.store")


class EventStore(Protocol):
    kind: str

    def append(self, events: list[LifeEvent]) -> list[LifeEvent]: ...
    def events(self, person_id: str, branch_id: str = "main") -> list[LifeEvent]: ...
    def latest_in_domain(self, person_id: str, domain: str, size: int = 5) -> list[LifeEvent]: ...
    def domain_histogram(self, person_id: str, domain: str) -> dict[str, Any]: ...
    def hybrid_search(self, person_id: str, text: str, size: int = 5) -> list[LifeEvent]: ...
    def add_evidence(self, items: list[Evidence]) -> None: ...
    def evidence(self, person_id: str, branch_id: str | None = None, ids: list[str] | None = None) -> list[Evidence]: ...
    def search_evidence(self, person_id: str, branch_id: str, text: str, size: int = 8) -> list[Evidence]: ...
    def counts_by_source(self, person_id: str) -> dict[str, int]: ...
    def erase(self, person_id: str) -> dict[str, int]: ...
    def delete_branches(self, person_id: str, branch_ids: list[str]) -> dict[str, int]: ...
    def origins(self, person_id: str) -> list[dict]: ...
    def forget(self, person_id: str, origin: str) -> int: ...
    def index_runs(self, branch, outcome, dates: list[str]) -> None: ...
    def distinctive(self, branch, siblings: list) -> list[dict] | None: ...
    def rarest_keys(self, branch) -> list[str] | None: ...
    def remembered(self, question: str, size: int = 3) -> list[Evidence]: ...
    def question_match(self, question: str, candidates: list[str]) -> list[float]: ...
    def track_record(self, person_id: str) -> tuple[int, int]: ...


class ElasticStore:
    kind = "elastic"

    MAPPINGS = {
        "properties": {
            "id": {"type": "keyword"},
            "person_id": {"type": "keyword"},
            "source": {"type": "keyword"},
            "branch_id": {"type": "keyword"},
            "date": {"type": "date"},
            "domain": {"type": "keyword"},
            "event_type": {"type": "keyword"},
            "payload": {"type": "object", "enabled": False},
            "confidence": {"type": "float"},
            "origin": {"type": "keyword"},
            "text": {"type": "text", "copy_to": "text_semantic"},
            "text_semantic": {"type": "semantic_text", "inference_id": config.ES_INFERENCE_ID},
        }
    }

    EVIDENCE_MAPPINGS = {
        "properties": {
            "id": {"type": "keyword"}, "person_id": {"type": "keyword"}, "branch_id": {"type": "keyword"},
            "kind": {"type": "keyword"}, "retrieved_at": {"type": "date"},
            "claim": {"type": "text", "copy_to": "claim_semantic"},
            "snippet": {"type": "text", "copy_to": "claim_semantic"},
            "claim_semantic": {"type": "semantic_text", "inference_id": config.ES_INFERENCE_ID},
            "value": {"type": "keyword", "index": False}, "unit": {"type": "keyword", "index": False},
            "source_title": {"type": "text"}, "source_url": {"type": "keyword"},
            "used_for": {"type": "text"}, "question": {"type": "text", "copy_to": "claim_semantic"},
            "figure": {"type": "keyword", "index": False}, "span_days": {"type": "integer", "index": False},
            # written by the evidence audit workflow (backend/app/workflows.py), not by the app
            "stale": {"type": "boolean"}, "checked_at": {"type": "date"},
        }
    }

    def __init__(self) -> None:
        from elasticsearch import Elasticsearch

        self.es = Elasticsearch(config.ES_URL, api_key=config.ES_API_KEY or None,
                                request_timeout=60, retry_on_timeout=True, max_retries=2)
        self.index = config.ES_INDEX
        self.semantic = True
        if not self.es.indices.exists(index=self.index):
            try:
                self.es.indices.create(index=self.index, mappings=self.MAPPINGS)
            except Exception as exc:  # no inference endpoint on this cluster: BM25 only
                log.warning("semantic_text unavailable (%s); creating a lexical-only index", exc)
                lexical = {k: v for k, v in self.MAPPINGS["properties"].items() if k != "text_semantic"}
                lexical["text"] = {"type": "text"}
                self.es.indices.create(index=self.index, mappings={"properties": lexical})
                self.semantic = False
        else:
            props = self.es.indices.get_mapping(index=self.index)[self.index]["mappings"]["properties"]
            self.semantic = "text_semantic" in props
            if "origin" not in props:  # older index: add the field that lets one upload be forgotten
                self.es.indices.put_mapping(index=self.index, properties={"origin": {"type": "keyword"}})
        self.runs_index = config.ES_RUNS_INDEX
        if not self.es.indices.exists(index=self.runs_index):
            keyword = {"type": "keyword"}
            self.es.indices.create(index=self.runs_index, mappings={"properties": {
                "person_id": keyword, "scenario_id": keyword, "branch_id": keyword, "revision": {"type": "integer"},
                "run": {"type": "integer"}, "step": {"type": "integer"}, "at": {"type": "date"},
                "event_key": keyword, "domain": keyword, "basis": keyword,
            }})
        self.evidence_index = config.ES_EVIDENCE_INDEX
        if not self.es.indices.exists(index=self.evidence_index):
            try:
                self.es.indices.create(index=self.evidence_index, mappings=self.EVIDENCE_MAPPINGS)
            except Exception as exc:
                log.warning("semantic_text unavailable for evidence (%s); lexical only", exc)
                lexical = {k: v for k, v in self.EVIDENCE_MAPPINGS["properties"].items() if k != "claim_semantic"}
                lexical["claim"], lexical["snippet"] = {"type": "text"}, {"type": "text"}
                self.es.indices.create(index=self.evidence_index, mappings={"properties": lexical})

    def append(self, events: list[LifeEvent]) -> list[LifeEvent]:
        from elasticsearch import helpers

        actions = [
            {"_op_type": "create", "_index": self.index, "_id": e.id, "_source": e.model_dump()}
            for e in events
        ]
        # `create` refuses to overwrite: an id that already exists stays exactly as it was.
        # Generous timeout: the first write after a quiet spell waits for the embedding model
        # behind the semantic_text field to wake up.
        _, errors = helpers.bulk(self.es.options(request_timeout=300), actions, raise_on_error=False,
                                 refresh="wait_for")
        rejected = {err["create"]["_id"] for err in errors if "create" in err}
        return [e for e in events if e.id not in rejected]

    def _filter(self, person_id: str, branch_id: str = "main", **terms: str) -> list[dict]:
        clauses = {"person_id": person_id, "branch_id": branch_id, **terms}
        return [{"term": {k: v}} for k, v in clauses.items()]

    def _hits(self, resp) -> list[LifeEvent]:
        return [LifeEvent(**_strip(h["_source"])) for h in resp["hits"]["hits"]]

    def events(self, person_id: str, branch_id: str = "main") -> list[LifeEvent]:
        resp = self.es.search(
            index=self.index, size=2000, sort=[{"date": "asc"}],
            query={"bool": {"filter": self._filter(person_id, branch_id)}},
        )
        return self._hits(resp)

    def latest_in_domain(self, person_id: str, domain: str, size: int = 5) -> list[LifeEvent]:
        resp = self.es.search(
            index=self.index, size=size, sort=[{"date": "desc"}],
            query={"bool": {"filter": self._filter(person_id, domain=domain)}},
        )
        return self._hits(resp)

    def domain_histogram(self, person_id: str, domain: str) -> dict[str, Any]:
        resp = self.es.search(
            index=self.index, size=0,
            query={"bool": {"filter": self._filter(person_id, domain=domain)}},
            aggs={
                "per_year": {
                    "date_histogram": {"field": "date", "calendar_interval": "year", "min_doc_count": 1},
                    "aggs": {"types": {"terms": {"field": "event_type", "size": 10}}},
                },
                "types": {"terms": {"field": "event_type", "size": 20}},
            },
        )
        aggs = resp["aggregations"]
        return {
            "per_year": {
                b["key_as_string"][:4]: {t["key"]: t["doc_count"] for t in b["types"]["buckets"]}
                for b in aggs["per_year"]["buckets"]
            },
            "types": {t["key"]: t["doc_count"] for t in aggs["types"]["buckets"]},
        }

    def _fuse(self, index: str, size: int, lexical: dict, dense: dict, text: str, field: str, what: str):
        """Three stages, plainest last: BM25 and dense fused by RRF, then that window read by a
        Jina cross-encoder, which scores the query against each candidate's actual words rather
        than against a single vector. Each stage falls back to the one before it, so a sleeping
        model or a missing endpoint degrades retrieval instead of failing it."""
        rrf = {"rrf": {"retrievers": [lexical, dense], "rank_window_size": 50}}
        attempts = [rrf]
        if config.ES_RERANK_ID:
            attempts.insert(0, {"text_similarity_reranker": {
                "retriever": rrf, "field": field, "inference_id": config.ES_RERANK_ID,
                "inference_text": text, "rank_window_size": max(4 * size, 20),
            }})
        for retriever in attempts:
            try:
                return self.es.search(index=index, size=size, retriever=retriever)
            except Exception as exc:
                log.warning("%s: %s unavailable (%s); falling back", what, next(iter(retriever)),
                            type(exc).__name__)
        return self.es.search(index=index, size=size, retriever=lexical)

    def hybrid_search(self, person_id: str, text: str, size: int = 5) -> list[LifeEvent]:
        filt = self._filter(person_id)
        lexical = {"standard": {"query": {"bool": {"must": {"match": {"text": text}}, "filter": filt}}}}
        if not self.semantic:
            return self._hits(self.es.search(index=self.index, size=size, retriever=lexical))
        dense = {
            "standard": {
                "query": {
                    "bool": {
                        "must": {"semantic": {"field": "text_semantic", "query": text}},
                        "filter": filt,
                    }
                }
            }
        }
        return self._hits(self._fuse(self.index, size, lexical, dense, text, "text", "life events"))


    # --- evidence: public facts and statistics, not the immutable past, so plain upserts ---

    def add_evidence(self, items: list[Evidence]) -> None:
        from elasticsearch import helpers

        if not items:
            return
        actions = [{"_op_type": "index", "_index": self.evidence_index, "_id": e.id, "_source": e.model_dump()}
                   for e in items]
        helpers.bulk(self.es.options(request_timeout=300), actions, raise_on_error=False, refresh="wait_for")

    def _evidence_hits(self, resp) -> list[Evidence]:
        out = []
        for h in resp["hits"]["hits"]:
            src = dict(h["_source"])
            src.pop("claim_semantic", None)
            out.append(Evidence(**src))
        return out

    def evidence(self, person_id: str, branch_id: str | None = None, ids: list[str] | None = None) -> list[Evidence]:
        filt: list[dict] = [{"term": {"person_id": person_id}}]
        if branch_id:
            filt.append({"term": {"branch_id": branch_id}})
        if ids:
            filt.append({"terms": {"id": ids}})
        resp = self.es.search(index=self.evidence_index, size=500, query={"bool": {"filter": filt}},
                              sort=[{"kind": "asc"}, {"retrieved_at": "desc"}])
        return self._evidence_hits(resp)

    def search_evidence(self, person_id: str, branch_id: str, text: str, size: int = 8) -> list[Evidence]:
        filt = [{"term": {"person_id": person_id}}, {"term": {"branch_id": branch_id}}]
        lexical = {"standard": {"query": {"bool": {"must": {"multi_match": {"query": text, "fields": ["claim", "snippet"]}}, "filter": filt}}}}
        dense = {"standard": {"query": {"bool": {"must": {"semantic": {"field": "claim_semantic", "query": text}}, "filter": filt}}}}
        return self._evidence_hits(
            self._fuse(self.evidence_index, size, lexical, dense, text, "claim", "evidence"))

    def remembered(self, question: str, size: int = 3) -> list[Evidence]:
        """Researched evidence from anyone's earlier research that may answer the same question.
        It is public fact, not personal data, so it is searched across people."""
        # `stale: true` is set by the scheduled evidence audit once a figure is older than
        # HEREAFTER_EVIDENCE_MAX_AGE_DAYS. Excluding it here is what turns that flag into
        # behaviour: the question falls through to a fresh crawl instead of being answered
        # from memory. Documents written before the first audit have no `stale` field at all,
        # so the clause is must_not rather than a term filter on false.
        filt = [{"term": {"kind": "researched"}}, {"exists": {"field": "question"}}]
        stale_filter = {"bool": {"must_not": [{"term": {"stale": True}}]}}
        filt = [*filt, stale_filter]
        lexical = {"standard": {"query": {"bool": {"must": {"match": {"question": question}}, "filter": filt}}}}
        dense = {"standard": {"query": {"bool": {"must": {"semantic": {"field": "claim_semantic", "query": question}}, "filter": filt}}}}
        # Reranked on `question`: whether to reuse a figure turns on the two questions asking the
        # same thing, which a cross-encoder judges and a single vector only approximates.
        return self._evidence_hits(
            self._fuse(self.evidence_index, size, lexical, dense, question, "question", "memory"))

    def question_match(self, question: str, candidates: list[str]) -> list[float]:
        """How well each already-researched question answers this one, scored by the Jina
        cross-encoder. Positive means the same question asked in other words; negative means a
        different question that merely shares vocabulary. Returns [] when no reranker is
        configured, which tells the caller to fall back to comparing the wording."""
        if not (config.ES_RERANK_ID and candidates):
            return []
        try:
            resp = self.es.inference.rerank(inference_id=config.ES_RERANK_ID, query=question,
                                            input=candidates)
        except Exception as exc:
            log.warning("question rerank unavailable (%s); comparing wording instead", type(exc).__name__)
            return []
        scores = [0.0] * len(candidates)
        for r in resp["rerank"]:
            scores[r["index"]] = float(r["relevance_score"])
        return scores

    def track_record(self, person_id: str) -> tuple[int, int]:
        """(kept, total) commitments in the person's own log: one filters aggregation over main."""
        resp = self.es.search(
            index=self.index, size=0, query={"bool": {"filter": self._filter(person_id)}},
            aggs={"record": {"filters": {"filters": {
                "kept": {"term": {"event_type": "goal_kept"}},
                "ended": {"terms": {"event_type": ["goal_kept", "goal_dropped"]}},
            }}}},
        )
        buckets = resp["aggregations"]["record"]["buckets"]
        return buckets["kept"]["doc_count"], buckets["ended"]["doc_count"]

    def counts_by_source(self, person_id: str) -> dict[str, int]:
        resp = self.es.search(index=self.index, size=0,
                              query={"bool": {"filter": [{"term": {"person_id": person_id}}]}},
                              aggs={"by": {"terms": {"field": "source", "size": 10}}})
        return {b["key"]: b["doc_count"] for b in resp["aggregations"]["by"]["buckets"]}

    # --- the multiverse: every simulated life's events, so that "what is distinctive about this
    #     branch" and "what is rare" are aggregations rather than code ---

    MAX_RUN_DOCS = 40_000

    def index_runs(self, branch, outcome, dates: list[str]) -> None:
        import numpy as np
        from elasticsearch import helpers

        by_key = {e["key"]: e for e in branch.model.get("events", [])}
        events = [by_key[k] for k in outcome.keys]  # the sampler's own (canonical) order
        if not events:
            return
        hits = np.argwhere(outcome.fired)[: self.MAX_RUN_DOCS]
        actions = ({
            "_op_type": "index", "_index": self.runs_index,
            "_id": f"{branch.id}-{branch.revision}-{run}-{step}-{events[e]['key']}",
            "_source": {"person_id": branch.person_id, "scenario_id": branch.scenario_id, "branch_id": branch.id,
                        "revision": branch.revision, "run": int(run), "step": int(step), "at": dates[step],
                        "event_key": events[e]["key"], "domain": events[e]["domain"], "basis": events[e]["basis"]},
        } for step, run, e in hits)
        helpers.bulk(self.es.options(request_timeout=300), actions, raise_on_error=False, chunk_size=5000)
        self.es.indices.refresh(index=self.runs_index)

    @staticmethod
    def _current(branch) -> dict:
        return {"bool": {"filter": [{"term": {"branch_id": branch.id}}, {"term": {"revision": branch.revision}}]}}

    def distinctive(self, branch, siblings: list) -> list[dict] | None:
        """significant_terms: events unusually common in this branch against its scenario."""
        try:
            resp = self.es.search(
                index=self.runs_index, size=0, query=self._current(branch),
                aggs={"distinct": {"significant_terms": {
                    "field": "event_key", "size": 5, "min_doc_count": 20,
                    "background_filter": {"bool": {"should": [self._current(b) for b in [branch, *siblings]],
                                                   "minimum_should_match": 1}},
                }}},
            )
        except Exception as exc:
            log.warning("significant_terms unavailable (%s)", type(exc).__name__)
            return None
        if not resp["hits"]["total"]["value"]:
            return None  # the background bulk has not landed yet
        return [{"key": b["key"], "runs": b["doc_count"], "score": b["score"]}
                for b in resp["aggregations"]["distinct"]["buckets"]]

    def rarest_keys(self, branch) -> list[str] | None:
        """rare_terms: events that happen in very few of this branch's thousand lives."""
        try:
            resp = self.es.search(index=self.runs_index, size=0, query=self._current(branch),
                                  aggs={"rare": {"rare_terms": {"field": "event_key", "max_doc_count": 100}}})
        except Exception as exc:
            log.warning("rare_terms unavailable (%s)", type(exc).__name__)
            return None
        if not resp["hits"]["total"]["value"]:
            return None
        return [b["key"] for b in sorted(resp["aggregations"]["rare"]["buckets"], key=lambda b: b["doc_count"])]

    def origins(self, person_id: str) -> list[dict]:
        """What the person has offered, by origin, with how much each contributed to main."""
        resp = self.es.search(
            index=self.index, size=0,
            query={"bool": {"filter": self._filter(person_id), "must": {"exists": {"field": "origin"}}}},
            aggs={"o": {"terms": {"field": "origin", "size": 200},
                        "aggs": {"newest": {"max": {"field": "date"}}, "source": {"terms": {"field": "source", "size": 1}}}}},
        )
        return [{"origin": b["key"], "count": b["doc_count"], "newest": (b["newest"].get("value_as_string") or "")[:10],
                 "source": (b["source"]["buckets"] or [{"key": ""}])[0]["key"]} for b in resp["aggregations"]["o"]["buckets"]]

    def forget(self, person_id: str, origin: str) -> int:
        """Remove everything on main that came from one offering. Owner-only, like erase."""
        resp = self.es.delete_by_query(
            index=self.index, refresh=True, conflicts="proceed",
            query={"bool": {"filter": [*self._filter(person_id), {"term": {"origin": origin}}]}},
        )
        return resp["deleted"]

    def erase(self, person_id: str) -> dict[str, int]:
        """The one deletion the system allows: the owner burning their own book."""
        query = {"term": {"person_id": person_id}}
        gone = {}
        for name, index in (("events", self.index), ("evidence", self.evidence_index), ("runs", self.runs_index)):
            resp = self.es.delete_by_query(index=index, query=query, refresh=True, conflicts="proceed")
            gone[name] = resp["deleted"]
        return gone

    def delete_branches(self, person_id: str, branch_ids: list[str]) -> dict[str, int]:
        """Remove what was simulated and researched for these paths (their events, evidence and runs).
        Never anything on main: the past is not rewritten."""
        ids = [b for b in branch_ids if b and b != "main"]
        gone = {"events": 0, "evidence": 0, "runs": 0}
        if not ids:
            return gone
        query = {"bool": {"filter": [{"term": {"person_id": person_id}}, {"terms": {"branch_id": ids}}]}}
        for name, index in (("events", self.index), ("evidence", self.evidence_index), ("runs", self.runs_index)):
            resp = self.es.options(request_timeout=300).delete_by_query(index=index, query=query, refresh=True, conflicts="proceed")
            gone[name] = resp["deleted"]
        return gone


class LocalStore:
    """Same surface over SQLite so the whole app runs with no cloud credentials."""

    kind = "local"

    def __init__(self) -> None:
        db.conn().execute(
            "CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, person_id TEXT, branch_id TEXT,"
            " date TEXT, domain TEXT, doc TEXT)"
        )

    def append(self, events: list[LifeEvent]) -> list[LifeEvent]:
        added = []
        with db._lock:
            c = db.conn()
            for e in events:
                cur = c.execute(
                    "INSERT OR IGNORE INTO events VALUES (?,?,?,?,?,?)",
                    (e.id, e.person_id, e.branch_id, e.date, e.domain, e.model_dump_json()),
                )
                if cur.rowcount:
                    added.append(e)
            c.commit()
        return added

    def _select(self, where: str, args: tuple, order: str = "date ASC") -> list[LifeEvent]:
        rows = db.conn().execute(f"SELECT doc FROM events WHERE {where} ORDER BY {order}", args)
        return [LifeEvent(**json.loads(r["doc"])) for r in rows.fetchall()]

    def events(self, person_id: str, branch_id: str = "main") -> list[LifeEvent]:
        return self._select("person_id=? AND branch_id=?", (person_id, branch_id))

    def latest_in_domain(self, person_id: str, domain: str, size: int = 5) -> list[LifeEvent]:
        return self._select(
            "person_id=? AND branch_id='main' AND domain=?", (person_id, domain), "date DESC"
        )[:size]

    def domain_histogram(self, person_id: str, domain: str) -> dict[str, Any]:
        per_year: dict[str, dict[str, int]] = {}
        types: dict[str, int] = {}
        for e in self._select("person_id=? AND branch_id='main' AND domain=?", (person_id, domain)):
            bucket = per_year.setdefault(e.date[:4], {})
            bucket[e.event_type] = bucket.get(e.event_type, 0) + 1
            types[e.event_type] = types.get(e.event_type, 0) + 1
        return {"per_year": per_year, "types": types}

    def hybrid_search(self, person_id: str, text: str, size: int = 5) -> list[LifeEvent]:
        want = set(re.findall(r"\w+", text.lower()))
        scored = []
        for e in self.events(person_id):
            overlap = len(want & set(re.findall(r"\w+", f"{e.text} {e.event_type}".lower())))
            if overlap:
                scored.append((overlap, e.date, e))
        scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
        return [e for _, _, e in scored[:size]]


    def add_evidence(self, items: list[Evidence]) -> None:
        with db._lock:
            c = db.conn()
            for e in items:
                c.execute("INSERT OR REPLACE INTO evidence VALUES (?,?,?,?)",
                          (e.id, e.person_id, e.branch_id, e.model_dump_json()))
            c.commit()

    def evidence(self, person_id: str, branch_id: str | None = None, ids: list[str] | None = None) -> list[Evidence]:
        rows = db.conn().execute("SELECT doc FROM evidence WHERE person_id=?", (person_id,)).fetchall()
        found = [Evidence(**json.loads(r["doc"])) for r in rows]
        return [e for e in found if (not branch_id or e.branch_id == branch_id) and (not ids or e.id in ids)]

    def search_evidence(self, person_id: str, branch_id: str, text: str, size: int = 8) -> list[Evidence]:
        want = set(re.findall(r"\w+", text.lower()))
        scored = [(len(want & set(re.findall(r"\w+", f"{e.claim} {e.snippet or ''}".lower()))), e)
                  for e in self.evidence(person_id, branch_id)]
        return [e for n, e in sorted(scored, key=lambda t: t[0], reverse=True)[:size] if n]

    def track_record(self, person_id: str) -> tuple[int, int]:
        kinds = [e.event_type for e in self.events(person_id)]
        return kinds.count("goal_kept"), kinds.count("goal_kept") + kinds.count("goal_dropped")

    def counts_by_source(self, person_id: str) -> dict[str, int]:
        rows = db.conn().execute("SELECT doc FROM events WHERE person_id=?", (person_id,)).fetchall()
        counts: dict[str, int] = {}
        for r in rows:
            source = json.loads(r["doc"])["source"]
            counts[source] = counts.get(source, 0) + 1
        return counts

    def remembered(self, question: str, size: int = 3) -> list[Evidence]:
        rows = db.conn().execute("SELECT doc FROM evidence").fetchall()
        found = [Evidence(**json.loads(r["doc"])) for r in rows]
        return [e for e in found if e.kind == "researched" and e.question][:50]

    def question_match(self, question: str, candidates: list[str]) -> list[float]:
        return []  # no inference here; the caller compares wording instead

    def index_runs(self, branch, outcome, dates: list[str]) -> None:
        return None  # the local stand-in keeps no multiverse; callers fall back to numpy

    def distinctive(self, branch, siblings: list) -> list[dict] | None:
        return None

    def rarest_keys(self, branch) -> list[str] | None:
        return None

    def origins(self, person_id: str) -> list[dict]:
        found: dict[str, dict] = {}
        for e in self.events(person_id):
            if e.origin:
                row = found.setdefault(e.origin, {"origin": e.origin, "count": 0, "newest": "", "source": e.source})
                row["count"] += 1
                row["newest"] = max(row["newest"], e.date)
        return list(found.values())

    def forget(self, person_id: str, origin: str) -> int:
        ids = [e.id for e in self.events(person_id) if e.origin == origin]
        with db._lock:
            c = db.conn()
            c.executemany("DELETE FROM events WHERE id=? AND person_id=? AND branch_id='main'", [(i, person_id) for i in ids])
            c.commit()
        return len(ids)

    def erase(self, person_id: str) -> dict[str, int]:
        c = db.conn()
        gone = {"events": c.execute("SELECT COUNT(*) FROM events WHERE person_id=?", (person_id,)).fetchone()[0],
                "evidence": c.execute("SELECT COUNT(*) FROM evidence WHERE person_id=?", (person_id,)).fetchone()[0]}
        return gone  # the rows themselves go in db.erase_person, inside one transaction

    def delete_branches(self, person_id: str, branch_ids: list[str]) -> dict[str, int]:
        ids = [b for b in branch_ids if b and b != "main"]  # never anything on main
        gone = {"events": 0, "evidence": 0, "runs": 0}
        if not ids:
            return gone
        marks = ",".join("?" * len(ids))
        c = db.conn()
        for table in ("events", "evidence"):
            gone[table] = c.execute(f"SELECT COUNT(*) FROM {table} WHERE person_id=? AND branch_id IN ({marks})", (person_id, *ids)).fetchone()[0]
            db._exec(f"DELETE FROM {table} WHERE person_id=? AND branch_id IN ({marks})", (person_id, *ids))
        return gone


def _strip(source: dict) -> dict:
    source.pop("text_semantic", None)
    return source


_store: EventStore | None = None


def get_store() -> EventStore:
    global _store
    if _store is None:
        if config.ES_URL:
            _store = ElasticStore()
        else:
            log.warning("ELASTICSEARCH_URL not set; using the local SQLite event store")
            _store = LocalStore()
    return _store


def reset() -> None:
    global _store
    _store = None
