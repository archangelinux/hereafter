"""Register the evidence audit workflow on the cluster (idempotent).

    .venv/bin/python -m scripts.workflow_setup            # create or replace
    .venv/bin/python -m scripts.workflow_setup --run      # ... and run it once now
    .venv/bin/python -m scripts.workflow_setup --remove   # delete it
"""

import json
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from app import config, workflows  # noqa: E402

if not config.ES_URL:
    sys.exit("ELASTICSEARCH_URL is not set; there is no cluster to register a workflow on.")

if "--remove" in sys.argv:
    print(" ", workflows.teardown())
    sys.exit()

print(" ", workflows.WORKFLOW_ID + ":", workflows.setup(),
      f"(stale after {config.EVIDENCE_MAX_AGE_DAYS} days, scheduled every 24h)")

if "--run" in sys.argv:
    execution = workflows.run()
    print("  run:", execution.get("status"), execution.get("error_message") or "")
    print("  health:", json.dumps(workflows.health(), default=str)[:400])
