"""Move the two semantic indices onto a different embedding model.

`semantic_text` bakes its `inference_id` into the mapping, so switching models means a new
index and a reindex — the embeddings are regenerated from `text` / `claim` / `snippet` /
`question` by the same `copy_to` rules, not copied. The life log's immutability is untouched:
this reads the old index and writes new documents with the same ids, and deletes nothing.

    .venv/bin/python -m scripts.reindex_semantic            # dry run: what it would do
    .venv/bin/python -m scripts.reindex_semantic --go       # do it
    .venv/bin/python -m scripts.reindex_semantic --go --force   # overwrite existing targets

Afterwards it prints the two lines to put in `.env`; nothing is switched over until you do.
"""

from __future__ import annotations

import sys
import time

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from app import config  # noqa: E402
from app.store import ElasticStore  # noqa: E402

SUFFIX = "-v2"
# The semantic fields are populated by copy_to on write, so they must not be carried over.
DROP = "ctx._source.remove('text_semantic'); ctx._source.remove('claim_semantic');"


def target_for(source: str) -> str:
    return source + SUFFIX


def reindex(es, source: str, target: str, mappings: dict, force: bool) -> None:
    if not es.indices.exists(index=source):
        print(f"  {source}: does not exist, skipping")
        return
    n = es.count(index=source)["count"]
    if es.indices.exists(index=target):
        if not force:
            print(f"  {target}: already exists — pass --force to replace it")
            return
        print(f"  {target}: exists, deleting (--force)")
        es.indices.delete(index=target)
    es.indices.create(index=target, mappings=mappings)
    print(f"  {source} -> {target}: {n} documents, embedding with {config.ES_INFERENCE_ID}")

    task = es.reindex(
        source={"index": source}, dest={"index": target},
        script={"source": DROP, "lang": "painless"},
        wait_for_completion=False, refresh=True,
    )["task"]
    while True:
        status = es.tasks.get(task_id=task)
        if status.get("completed"):
            break
        s = status["task"]["status"]
        print(f"    {s['created']}/{s['total']} embedded", end="\r", flush=True)
        time.sleep(2)
    failures = status.get("response", {}).get("failures", [])
    if failures:
        print(f"\n    {len(failures)} failures; first: {str(failures[0])[:300]}")
    es.indices.refresh(index=target)
    print(f"    {es.count(index=target)['count']}/{n} documents in {target}")


def main() -> None:
    go, force = "--go" in sys.argv, "--force" in sys.argv
    if not config.ES_URL:
        sys.exit("ELASTICSEARCH_URL is not set; there is nothing to reindex.")
    store = ElasticStore()
    pairs = [(config.ES_INDEX, ElasticStore.MAPPINGS),
             (config.ES_EVIDENCE_INDEX, ElasticStore.EVIDENCE_MAPPINGS)]

    if not go:
        print("Dry run. Would reindex, regenerating every embedding with "
              f"{config.ES_INFERENCE_ID}:\n")
        for source, _ in pairs:
            exists = store.es.indices.exists(index=source)
            n = store.es.count(index=source)["count"] if exists else 0
            print(f"  {source} ({n} docs) -> {target_for(source)}")
        print("\nRe-run with --go to do it. `hereafter-runs` holds no embeddings and is untouched.")
        return

    for source, mappings in pairs:
        reindex(store.es, source, target_for(source), mappings, force)

    print("\nNothing is live yet. Put these in .env, then restart the backend:\n")
    print(f"HEREAFTER_ES_INDEX={target_for(config.ES_INDEX)}")
    print(f"HEREAFTER_ES_EVIDENCE_INDEX={target_for(config.ES_EVIDENCE_INDEX)}")
    print("\nThe old indices are left exactly as they are; delete them once you are happy.")


if __name__ == "__main__":
    main()
