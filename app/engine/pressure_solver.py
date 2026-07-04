"""
PHASE 2 — Pressure Solver (Hazen-Williams)

The physics engine. Computes pressure at every node in the network
based on flow rates, pipe geometry, and source pressures.

Hazen-Williams head loss formula:
  hL = (10.67 × L × Q^1.852) / (C^1.852 × D^4.87)

  hL = head loss in meters
  L  = pipe length (meters)
  Q  = flow rate (m³/s)
  C  = roughness coefficient (100–140, higher = smoother)
  D  = pipe diameter (meters)

Pressure drop = hL × ρ × g  (Pa), then convert to PSI

Interview explanation:
  'Hazen-Williams is the standard equation used by civil engineers
   to calculate pressure drop in water pipes. We implement it as a
   pure Python function that takes pipe parameters and returns head loss.
   Then we walk the graph from source nodes, computing cumulative
   pressure at each downstream junction.'
"""

import numpy as np
import networkx as nx

RHO_WATER = 1000.0   # kg/m³
GRAVITY   = 9.81     # m/s²
PA_TO_PSI = 0.000145038  # conversion factor


def hazen_williams_head_loss(
    flow_lps: float,        # liters per second
    length_m: float,        # pipe length in meters
    roughness_c: float,     # HW coefficient (100-140)
    diameter_mm: float,     # pipe diameter in mm
) -> float:
    """
    Returns head loss in meters for a single pipe.

    Head loss = how much pressure energy is lost to friction
    as water flows through the pipe.

    More flow   → more loss (exponential, not linear)
    Longer pipe → more loss (linear)
    Wider pipe  → less loss
    Rougher pipe → more loss
    """
    if flow_lps <= 0:
        return 0.0

    Q = flow_lps / 1000.0       # L/s → m³/s
    D = diameter_mm / 1000.0    # mm → meters

    # Hazen-Williams formula
    # Using the SI version of the constant (10.67)
    head_loss = (10.67 * length_m * (Q ** 1.852)) / (
        (roughness_c ** 1.852) * (D ** 4.871)
    )
    return round(head_loss, 4)


def head_to_psi(head_m: float) -> float:
    """Convert head loss in meters to PSI (pounds per square inch)."""
    pressure_pa = head_m * RHO_WATER * GRAVITY
    return round(pressure_pa * PA_TO_PSI, 4)


def compute_pressures(G: nx.DiGraph) -> dict[str, float]:
    """
    Compute pressure at every node using BFS.

    Pressure decreases because of:
      1. Pipe friction (Hazen-Williams)
      2. Extra pressure loss caused by leaks
    """

    pressures = {}
    visit_count = {}

    # Initialize source nodes
    for node, data in G.nodes(data=True):
        if data.get("is_source"):
            pressures[node] = data["pressure_base"]
            visit_count[node] = 1

    queue = list(pressures.keys())

    while queue:
        current = queue.pop(0)
        current_pressure = pressures[current]

        for _, neighbor, edge_data in G.out_edges(current, data=True):

            # -----------------------------
            # Normal friction loss
            # -----------------------------
            head_loss = hazen_williams_head_loss(
                flow_lps=edge_data["flow_rate"],
                length_m=edge_data["length_m"],
                roughness_c=edge_data["roughness_c"],
                diameter_mm=edge_data["diameter_mm"],
            )

            pressure_loss = head_to_psi(head_loss)

            pressure_at_neighbor = current_pressure - pressure_loss

            # -----------------------------
            # Extra pressure loss due to leak
            # -----------------------------
            if edge_data.get("has_leak", False):

                severity = edge_data["leak_severity"]

                # 0 -> 0 PSI
                # 0.5 -> 7.5 PSI
                # 1.0 -> 15 PSI
                leak_loss = severity * 15

                pressure_at_neighbor -= leak_loss

            pressure_at_neighbor = max(0.0, pressure_at_neighbor)

            if neighbor not in pressures:
                pressures[neighbor] = pressure_at_neighbor
                visit_count[neighbor] = 1
                queue.append(neighbor)

            else:
                pressures[neighbor] = (
                    pressures[neighbor] * visit_count[neighbor]
                    + pressure_at_neighbor
                ) / (visit_count[neighbor] + 1)

                visit_count[neighbor] += 1

    return {node: round(value, 2) for node, value in pressures.items()}

def pressure_report(G: nx.DiGraph, pressures: dict[str, float]) -> dict:
    """
    Generate a human-readable pressure report.
    Shows each node's expected vs computed pressure.
    """
    report = []
    for node, data in G.nodes(data=True):
        computed = pressures.get(node, 0.0)
        expected = data.get("pressure_base", 0.0)
        delta    = round(computed - expected, 2)
        report.append({
            "node":          node,
            "pressure_psi":  computed,
            "baseline_psi":  expected,
            "delta_psi":     delta,
            "is_source":     data.get("is_source", False),
            "status":        "ok" if abs(delta) < 10 else "warning" if abs(delta) < 25 else "critical",
        })
    return {"nodes": report, "total_nodes": len(report)}
