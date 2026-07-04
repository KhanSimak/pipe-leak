"""
PHASE 3 — Leak Injector

Injects a simulated leak into the live graph.

A leak on a pipe edge means some flow is "lost" before reaching the
downstream node. We model this as:
  - Reducing the edge's flow_rate by (severity × original_flow)
  - Adding a "leak" flag to the edge attributes

The pressure solver then recomputes pressures with the reduced flow.
Downstream nodes will show lower pressure — that's the signal we detect.

Interview explanation:
  'A leak reduces the flow rate on an edge. Since Hazen-Williams
   pressure drop depends on flow rate, downstream pressures fall.
   We inject leaks by modifying edge attributes on the in-memory
   graph — no DB write needed. The detection algorithm then compares
   live pressures against the stored baseline.'
"""

import networkx as nx
from copy import deepcopy


def inject_leak(
    G: nx.DiGraph,
    node_from: str,
    node_to: str,
    severity: float = 0.5,
) -> nx.DiGraph:

    if not G.has_edge(node_from, node_to):
        raise ValueError(f"Edge {node_from} -> {node_to} does not exist")

    severity = max(0.0, min(1.0, severity))

    G_leaked = deepcopy(G)

    edge = G_leaked[node_from][node_to]

    edge["original_flow"] = edge["flow_rate"]

# Don't reduce the flow.
# Just mark this pipe as leaking.
    edge["has_leak"] = True
    edge["leak_severity"] = severity


    print("=" * 60)
    print("LEAK INJECTED")
    print(f"Edge          : {node_from} -> {node_to}")
    print(f"Original Flow : {edge['original_flow']}")
    print(f"Leak Severity : {severity}")
    print(f"Severity      : {severity}")
    print("=" * 60)

    return G_leaked

def list_leaks(G: nx.DiGraph) -> list[dict]:
    """List all edges that currently have an injected leak."""
    leaks = []
    for u, v, data in G.edges(data=True):
        if data.get("has_leak"):
            leaks.append({
                "edge":            f"{u} → {v}",
                "node_from":       u,
                "node_to":         v,
                "severity":        data["leak_severity"],
                "original_flow":   data["original_flow"],
                "current_flow":    data["flow_rate"],
                "flow_lost_lps":   round(data["original_flow"] - data["flow_rate"], 2),
            })
    return leaks
