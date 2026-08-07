"""Render docs/lineage.png from dbt's manifest.json, for the README.

Run after any change to the model DAG: `dbt docs generate` first (this script reads its
output), then `.venv/bin/python scripts/generate_lineage_graph.py`.

Requires the `dot` binary (Homebrew: `brew install graphviz`) plus the `graphviz` Python
package (requirements-dev.txt) -- a real dependency, not vendored, since this is a one-shot
doc-generation utility, not something the pipeline or dbt project needs at runtime.
"""

from __future__ import annotations

import json
from pathlib import Path

import graphviz

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "dbt" / "target" / "manifest.json"
OUT = ROOT / "docs" / "lineage"

KEEP_PACKAGE = "bridge_pipeline"
# Generic schema tests (not_null/unique/relationships/dbt_expectations/dbt_utils) would
# clutter a recruiter-facing diagram without adding signal; singular business-logic tests stay.
GENERIC_TEST_PREFIXES = (
    "not_null_",
    "unique_",
    "relationships_",
    "accepted_values_",
    "dbt_utils_",
    "dbt_expectations_",
)
# DuckDB-only fixture seeds that share a display name with a raw_fred source (see
# DECISIONS.md) -- they have no downstream edges (seeds aren't ref()'d by staging models),
# so they'd render as disconnected-looking duplicates of the source nodes that tell the real
# architecture story. dim_series_category has no such collision and is kept.
DUPLICATE_SEED_NAMES = {"observations", "series_metadata"}

COLORS = {
    "source": "#8ecae6",
    "seed": "#8ecae6",
    "model_staging": "#ffb703",
    "model_marts_dim": "#219ebc",
    "model_marts_fct": "#023047",
    "model_marts_mart": "#fb8500",
    "test": "#adb5bd",
}


def classify(node: dict) -> str:
    rt = node["resource_type"]
    if rt in ("source", "seed"):
        return rt
    if rt == "test":
        return "test"
    if "staging" in node.get("path", ""):
        return "model_staging"
    if node["name"].startswith("dim_"):
        return "model_marts_dim"
    if node["name"].startswith("fct_"):
        return "model_marts_fct"
    return "model_marts_mart"


def main() -> None:
    manifest = json.loads(MANIFEST.read_text())

    nodes = {}
    for key, node in {**manifest["nodes"], **manifest["sources"]}.items():
        if node.get("package_name") != KEEP_PACKAGE:
            continue
        name = node["name"]
        if node["resource_type"] == "test" and name.startswith(GENERIC_TEST_PREFIXES):
            continue
        if node["resource_type"] == "seed" and name in DUPLICATE_SEED_NAMES:
            continue
        nodes[key] = node

    dot = graphviz.Digraph("lineage", format="png")
    dot.attr(rankdir="LR", bgcolor="#ffffff", fontname="Helvetica", nodesep="0.35", ranksep="0.9")
    dot.attr("node", fontname="Helvetica", fontsize="11", style="filled", shape="box")
    dot.attr("edge", color="#9aa5b1", arrowsize="0.7")

    for key, node in nodes.items():
        kind = classify(node)
        font_color = "#ffffff" if kind == "model_marts_fct" else "#1b1b1b"
        dot.node(
            key,
            label=node["name"],
            fillcolor=COLORS[kind],
            fontcolor=font_color,
            color=COLORS[kind],
        )

    edges_added = set()
    for key, node in nodes.items():
        for dep in node.get("depends_on", {}).get("nodes", []):
            if dep in nodes and (dep, key) not in edges_added:
                dot.edge(dep, key)
                edges_added.add((dep, key))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    rendered_path = dot.render(filename=str(OUT), cleanup=True)
    print(f"wrote {rendered_path}")


if __name__ == "__main__":
    main()
