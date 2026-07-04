"""
PHASE 5 — Diagnosis Router

GET /networks/{id}/diagnosis
  → Run full leak detection algorithm
  → Returns top candidate edge + confidence + all evidence

GET /networks/{id}/diagnosis/explain
  → Step-by-step explanation of how the algorithm reached its conclusion
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.db import Network, get_db
from app.engine.graph_builder import build_graph
from app.engine.pressure_solver import compute_pressures
from app.engine.leak_detector import detect_leaks, format_diagnosis
from app.routers.simulation import _live_graphs

router = APIRouter()


async def _load_network(nid: int, db: AsyncSession) -> Network:
    r = await db.execute(
        select(Network).where(Network.id == nid)
        .options(selectinload(Network.nodes), selectinload(Network.edges))
    )
    n = r.scalar_one_or_none()
    if not n: raise HTTPException(404, "Network not found")
    return n


@router.get("/{network_id}/diagnosis")
async def diagnose(network_id: int, db: AsyncSession = Depends(get_db)):
    """
    Full leak diagnosis. Works best after injecting a leak via /simulate/leak.

    Flow:
      1. Load baseline graph → compute baseline pressures
      2. Load live graph (may have leaks) → compute live pressures
      3. Run detection algorithm → rank candidate edges
      4. Return top candidate + confidence + all supporting evidence
    """
    network    = await _load_network(network_id, db)
    G_baseline = build_graph(network)
    G_live     = _live_graphs.get(network_id, G_baseline)

    baseline_p = compute_pressures(G_baseline)
    live_p     = compute_pressures(G_live)

    candidates = detect_leaks(G_baseline, baseline_p, live_p)
    return format_diagnosis(candidates, baseline_p, live_p)


@router.get("/{network_id}/diagnosis/explain")
async def explain_diagnosis(network_id: int, db: AsyncSession = Depends(get_db)):
    """
    Step-by-step walkthrough of the detection algorithm.
    Great for debugging and for understanding how it works.
    """
    network    = await _load_network(network_id, db)
    G_baseline = build_graph(network)
    G_live     = _live_graphs.get(network_id, G_baseline)

    baseline_p = compute_pressures(G_baseline)
    live_p     = compute_pressures(G_live)

    # Step by step explanation
    steps = []

    steps.append({
        "step": 1,
        "title": "Compute baseline pressures",
        "result": baseline_p,
    })

    steps.append({
        "step": 2,
        "title": "Compute live pressures",
        "result": live_p,
    })

    deltas = {
        node: round(baseline_p.get(node, 0) - live_p.get(node, 0), 2)
        for node in baseline_p
    }
    affected = [n for n, d in deltas.items() if d >= 5.0]

    steps.append({
        "step": 3,
        "title": "Find affected nodes (drop ≥ 5 PSI)",
        "deltas": deltas,
        "affected_nodes": affected,
    })

    edge_scores = []
    for u, v, _ in G_baseline.edges(data=True):
        if v in affected:
            up_delta   = deltas.get(u, 0)
            down_delta = deltas.get(v, 0)
            edge_scores.append({
                "edge":            f"{u} → {v}",
                "upstream_drop":   up_delta,
                "downstream_drop": down_delta,
                "boundary_signal": round(down_delta - up_delta, 2),
                "reasoning": f"'{v}' dropped {down_delta} PSI but upstream '{u}' only dropped {up_delta} PSI → boundary here",
            })

    steps.append({
        "step":  4,
        "title": "Score candidate edges (look for upstream-normal, downstream-affected boundaries)",
        "candidates": sorted(edge_scores, key=lambda x: x["boundary_signal"], reverse=True),
    })

    candidates = detect_leaks(G_baseline, baseline_p, live_p)
    steps.append({
        "step":       5,
        "title":      "Final ranked candidates",
        "conclusion": f"Most likely leak: {candidates[0].node_from} → {candidates[0].node_to} (confidence: {candidates[0].confidence})" if candidates else "No leak detected",
    })

    return {"network_id": network_id, "steps": steps}
