"""
PHASE 3 — Simulation Router

Endpoints:
  POST /networks/{id}/simulate/leak    → inject a leak
  POST /networks/{id}/simulate/clear   → clear all injected leaks
  GET  /networks/{id}/simulate/compare → compare baseline vs leaked pressures
  GET  /networks/{id}/history          → time-series pressure readings

The in-memory graph state is stored per-network in a simple dict.
In Phase 4 this moves to Redis for multi-process access.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload
from pydantic import BaseModel, Field
from datetime import datetime, timezone, timedelta
import asyncio

from app.models.db import Network, get_db
from app.models.readings import PressureReading
from app.engine.graph_builder import build_graph
from app.engine.pressure_solver import compute_pressures
from app.engine.leak_injector import inject_leak, list_leaks

router = APIRouter()

# ── In-memory graph store (per network_id) ───────────────────────────────────
# Phase 4 will move this to Redis
_live_graphs: dict = {}


class LeakRequest(BaseModel):
    node_from: str
    node_to:   str
    severity:  float = Field(default=0.5, ge=0.0, le=1.0,
                              description="0=no leak, 1=full blockage")


async def _get_or_build_graph(network_id: int, db: AsyncSession):
    """Get live graph from memory, or build fresh from DB."""
    if network_id not in _live_graphs:
        result = await db.execute(
            select(Network).where(Network.id == network_id)
            .options(selectinload(Network.nodes), selectinload(Network.edges))
        )
        network = result.scalar_one_or_none()
        if not network:
            raise HTTPException(404, "Network not found")
        _live_graphs[network_id] = build_graph(network)
    return _live_graphs[network_id]


async def _save_reading(db: AsyncSession, network_id: int, pressures: dict,
                         baseline: dict, has_leak: bool):
    """Persist a pressure snapshot to the readings table."""
    now = datetime.now(timezone.utc)
    for node_name, pressure in pressures.items():
        base = baseline.get(node_name, pressure)
        reading = PressureReading(
            network_id   = network_id,
            node_name    = node_name,
            pressure_psi = pressure,
            baseline_psi = base,
            delta_psi    = round(pressure - base, 3),
            has_leak     = has_leak,
            recorded_at  = now,
        )
        db.add(reading)
    await db.commit()


@router.post("/{network_id}/simulate/leak")
async def inject_leak_endpoint(
    network_id: int,
    body: LeakRequest,
    db: AsyncSession = Depends(get_db),
):
    print(">>> ENTERED inject_leak_endpoint", flush=True)
    """
    Inject a leak into the live graph.
    Immediately recomputes pressures and saves a snapshot.

    After calling this, hit GET /pressures to see the pressure drop.
    """
    G_baseline = await _get_or_build_graph(network_id, db)

    # Inject leak → new graph (baseline unchanged)
    G_leaked = inject_leak(G_baseline, body.node_from, body.node_to, body.severity)

    # Store the leaked graph as the live state
    _live_graphs[network_id] = G_leaked

    # Compute both pressure states
    baseline_pressures = compute_pressures(G_baseline)
    leaked_pressures   = compute_pressures(G_leaked)

    # Save snapshot to DB
    await _save_reading(db, network_id, leaked_pressures, baseline_pressures, has_leak=True)

    # Show the impact
    impact = {}
    for node in leaked_pressures:
        base   = baseline_pressures.get(node, 0)
        leaked = leaked_pressures[node]
        impact[node] = {
            "baseline":  base,
            "with_leak": leaked,
            "drop":      round(base - leaked, 2),
            "affected":  abs(base - leaked) > 2.0,
        }

    return {
        "leak_injected": True,
        "edge":          f"{body.node_from} → {body.node_to}",
        "severity":      body.severity,
        "pressure_impact": impact,
    }


@router.post("/{network_id}/simulate/clear")
async def clear_leaks(network_id: int, db: AsyncSession = Depends(get_db)):
    """Remove all injected leaks, restore to baseline graph."""
    result = await db.execute(
        select(Network).where(Network.id == network_id)
        .options(selectinload(Network.nodes), selectinload(Network.edges))
    )
    network = result.scalar_one_or_none()
    if not network:
        raise HTTPException(404, "Network not found")

    _live_graphs[network_id] = build_graph(network)
    return {"cleared": True, "message": "Graph restored to baseline"}


@router.get("/{network_id}/simulate/compare")
async def compare_pressures(network_id: int, db: AsyncSession = Depends(get_db)):
    """
    Compare baseline vs live (potentially leaked) pressures side by side.
    This is your main diagnostic view.
    """
    result = await db.execute(
        select(Network).where(Network.id == network_id)
        .options(selectinload(Network.nodes), selectinload(Network.edges))
    )
    network = result.scalar_one_or_none()
    if not network:
        raise HTTPException(404, "Network not found")

    G_baseline = build_graph(network)
    G_live     = _live_graphs.get(network_id, G_baseline)

    baseline_p = compute_pressures(G_baseline)
    live_p     = compute_pressures(G_live)
    leaks      = list_leaks(G_live)

    comparison = [
        {
            "node":         node,
            "baseline_psi": baseline_p.get(node, 0),
            "live_psi":     live_p.get(node, 0),
            "drop_psi":     round(baseline_p.get(node, 0) - live_p.get(node, 0), 2),
            "status":       "affected" if abs(baseline_p.get(node,0) - live_p.get(node,0)) > 2 else "normal",
        }
        for node in baseline_p
    ]

    return {
        "has_active_leaks": len(leaks) > 0,
        "active_leaks":     leaks,
        "comparison":       comparison,
    }


@router.get("/{network_id}/history")
async def get_history(
    network_id: int,
    db:         AsyncSession = Depends(get_db),
    node:       str | None   = Query(default=None, description="Filter by node name"),
    minutes:    int          = Query(default=10, ge=1, le=1440),
):
    """
    Fetch pressure readings from the last N minutes.
    This queries the TimescaleDB hypertable.
    Add ?node=junction_A to filter by specific node.
    """
    since = datetime.now(timezone.utc) - timedelta(minutes=minutes)

    query = select(PressureReading).where(
        PressureReading.network_id  == network_id,
        PressureReading.recorded_at >= since,
    ).order_by(PressureReading.recorded_at.desc()).limit(500)

    if node:
        query = query.where(PressureReading.node_name == node)

    result = await db.execute(query)
    readings = result.scalars().all()

    return {
        "network_id": network_id,
        "node_filter": node,
        "minutes": minutes,
        "count": len(readings),
        "readings": [
            {
                "node":         r.node_name,
                "pressure_psi": r.pressure_psi,
                "baseline_psi": r.baseline_psi,
                "delta_psi":    r.delta_psi,
                "has_leak":     r.has_leak,
                "recorded_at":  r.recorded_at.isoformat(),
            }
            for r in readings
        ],
    }
