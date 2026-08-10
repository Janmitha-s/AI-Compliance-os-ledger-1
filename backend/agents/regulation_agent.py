"""
Regulatory Intelligence Agent
------------------------------
In production this agent runs scheduled crawlers/RSS/API pollers against
government sources (DGCA, MCA, GST, RBI, Labour Ministry, etc.), diffs new
content against the last known version, and embeds the result into a
vector database for retrieval. Here it simply loads the static regulation
knowledge base used for the demo.
"""
import json


def load_regulations(path: str) -> list[dict]:
    with open(path, "r") as f:
        return json.load(f)
