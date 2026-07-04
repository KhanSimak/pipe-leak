"""
PHASE 5 — Leak Detector

The core algorithm. Compares live pressures against baseline,
walks the graph to isolate which edge most likely has the leak.

Algorithm:
  1. Compute pressure delta at every node (live - baseline)
  2. Flag nodes with delta below threshold as "affected"
  3. For each affected node, look at incoming edges
  4. The edge whose upstream node is NOT affected but downstream IS
     = the leak is on that edge
  5. Score each candidate edge by how much it explains the pattern
  6. Return ranked candidates with confidence scores

Interview explanation:
  'Think of it like tracing a water pressure drop upstream.
   If junction_B is low but junction_A is normal, and there is a
   pipe from A to B — that pipe is the suspect. We walk every
   affected node and score all candidate edges using a combination
   of pressure drop magnitude and graph position. The highest-scoring
   edge is returned as the most likely leak location.'
"""

import networkx as nx
from dataclasses import dataclass


AFFECTED_THRESHOLD_PSI = 5.0    # pressure drop this big = node is affected
MIN_CONFIDENCE = 0.1             # don't return candidates below 10% confidence


@dataclass
class LeakCandidate:
    node_from:   str
    node_to:     str
    confidence:  float      # 0.0 – 1.0
    evidence:    str        # human-readable explanation
    drop_at_downstream: float


def detect_leaks(
    G: nx.DiGraph,
    baseline_pressures: dict[str, float],
    live_pressures:     dict[str, float],
) -> list[LeakCandidate]:
    """
    Returns a ranked list of leak candidates.
    Index 0 = most likely leak location.
    """
    if not baseline_pressures or not live_pressures:
        return []

    # ── Step 1: Find affected nodes ─────────────────────────────────
    affected = set()
    deltas: dict[str, float] = {}

    for node in baseline_pressures:
        base  = baseline_pressures[node]
        live  = live_pressures.get(node, base)
        delta = base - live              # positive = pressure dropped
        deltas[node] = delta
        if delta >= AFFECTED_THRESHOLD_PSI:
            affected.add(node)

    if not affected:
        return []   # no anomaly detected

    # ── Step 2: Score candidate edges ───────────────────────────────
    # An edge is a candidate if:
    #   - its downstream node is affected
    #   - its upstream node is NOT affected (or is less affected)
    candidates: list[LeakCandidate] = []
    max_drop = max(deltas.values()) or 1.0

    for u, v, edge_data in G.edges(data=True):
        if v not in affected:
            continue   # downstream node not affected — skip

        upstream_delta   = deltas.get(u, 0.0)
        downstream_delta = deltas.get(v, 0.0)

        # Score: higher if upstream is ok but downstream is affected
        boundary_score = max(0.0, downstream_delta - upstream_delta) / max_drop

        # Leak boundary:
# upstream should be mostly normal
# downstream should have a significant pressure drop

        if upstream_delta >= AFFECTED_THRESHOLD_PSI:
         continue

        confidence = (
            downstream_delta /
            max(max_drop, 1)
        )
        if confidence >= MIN_CONFIDENCE:
            evidence = (
                f"Node '{v}' dropped {downstream_delta:.1f} PSI. "
                f"Upstream '{u}' remained normal ({upstream_delta:.1f} PSI drop). "
                "This pressure boundary strongly indicates the leak is on this pipe."
            )
            candidates.append(LeakCandidate(
                node_from          = u,
                node_to            = v,
                confidence         = round(confidence, 3),
                evidence           = evidence,
                drop_at_downstream = round(downstream_delta, 2),
            ))

    # Sort by confidence descending
    candidates.sort(key=lambda c: c.confidence, reverse=True)

    # Normalize confidences so top candidate = 1.0 (relative scoring)
    if candidates:
        top = candidates[0].confidence
        if top > 0:
            for c in candidates:
                c.confidence = round(c.confidence / top, 3)

    return candidates


def format_diagnosis(
    candidates:         list[LeakCandidate],
    baseline_pressures: dict[str, float],
    live_pressures:     dict[str, float],
) -> dict:
    """Format detection results as a clean API response."""
    deltas = {
        node: round(baseline_pressures.get(node, 0) - live_pressures.get(node, 0), 2)
        for node in baseline_pressures
    }
    affected_nodes = [n for n, d in deltas.items() if d >= AFFECTED_THRESHOLD_PSI]

    return {
        "anomaly_detected":   len(candidates) > 0,
        "affected_nodes":     affected_nodes,
        "affected_count":     len(affected_nodes),
        "top_candidate": {
            "edge":       f"{candidates[0].node_from} → {candidates[0].node_to}",
            "confidence": candidates[0].confidence,
            "evidence":   candidates[0].evidence,
        } if candidates else None,
        "all_candidates": [
            {
                "edge":                f"{c.node_from} → {c.node_to}",
                "node_from":           c.node_from,
                "node_to":             c.node_to,
                "confidence":          c.confidence,
                "drop_at_downstream":  c.drop_at_downstream,
                "evidence":            c.evidence,
            }
            for c in candidates
        ],
        "pressure_map": {
            node: {
                "baseline": baseline_pressures.get(node, 0),
                "live":     live_pressures.get(node, 0),
                "drop":     deltas.get(node, 0),
                "status":   "critical" if deltas.get(node,0) > 25
                            else "warning" if deltas.get(node,0) > AFFECTED_THRESHOLD_PSI
                            else "normal",
            }
            for node in baseline_pressures
        },
    }
