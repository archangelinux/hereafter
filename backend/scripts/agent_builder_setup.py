"""Register Hereafter's retrieval tools and agent on Elastic Agent Builder (idempotent).

    .venv/bin/python -m scripts.agent_builder_setup            # create or update
    .venv/bin/python -m scripts.agent_builder_setup --remove   # delete them again

The tools are ordinary Agent Builder tools once created: visible in Kibana, usable by the
Elastic AI Agent, and reachable over Agent Builder's MCP endpoint.
"""

import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from app import agent_builder, config  # noqa: E402

if not config.ES_URL:
    sys.exit("ELASTICSEARCH_URL is not set; there is no cluster to register anything on.")

for line in (agent_builder.teardown() if "--remove" in sys.argv else agent_builder.setup()):
    print(" ", line)
