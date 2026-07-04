"""
PHASE 4 — Streaming Router

WebSocket endpoints:
  WS /networks/{id}/stream  → live pressure tick every 500ms
  WS /networks/{id}/alerts  → push alerts when anomaly detected
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
import asyncio
import json
import redis.asyncio as aioredis
import os

from app.models.db import Network, get_db
from app.engine.graph_builder import build_graph
from app.engine.pressure_solver import compute_pressures
from app.streaming.ws_manager import manager
from app.routers.simulation import _live_graphs

router = APIRouter()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")


async def _load_network(network_id: int, db: AsyncSession) -> Network:
    r = await db.execute(
        select(Network).where(Network.id == network_id)
        .options(selectinload(Network.nodes), selectinload(Network.edges))
    )
    return r.scalar_one_or_none()


@router.websocket("/{network_id}/stream")
async def pressure_stream(network_id: int, websocket: WebSocket,
                          db: AsyncSession = Depends(get_db)):
    """
    Live pressure stream — sends a tick every 500ms.
    Each tick contains current pressure at every node.

    Client receives:
    {
      "type": "pressure_tick",
      "network_id": 1,
      "pressures": {"pump_1": 120.0, "junction_A": 95.3, ...},
      "has_leaks": false
    }
    """
    network = await _load_network(network_id, db)
    if not network:
        await websocket.close(code=4004)
        return

    await manager.connect(network_id, websocket)
    G_baseline = build_graph(network)

    try:
        while True:
            # Use live graph (may have leaks injected)
            G_live = _live_graphs.get(network_id, G_baseline)
            pressures = compute_pressures(G_live)

            from app.engine.leak_injector import list_leaks
            leaks = list_leaks(G_live)

            await websocket.send_json({
                "type":       "pressure_tick",
                "network_id": network_id,
                "pressures":  pressures,
                "has_leaks":  len(leaks) > 0,
                "leak_count": len(leaks),
            })

            await asyncio.sleep(0.5)   # tick every 500ms

    except WebSocketDisconnect:
        manager.disconnect(network_id, websocket)


@router.websocket("/{network_id}/alerts")
async def alert_stream(network_id: int, websocket: WebSocket,
                       db: AsyncSession = Depends(get_db)):
    """
    Alert stream — only sends messages when an anomaly is detected.
    Uses Redis pub/sub so Celery worker can push alerts.

    Client receives:
    {
      "type": "pressure_alert",
      "alerts": [{"node": "junction_B", "drop_psi": 18.5, "severity": "warning"}]
    }
    """
    network = await _load_network(network_id, db)
    if not network:
        await websocket.close(code=4004)
        return

    await websocket.accept()

    r = aioredis.from_url(REDIS_URL)
    pubsub = r.pubsub()
    await pubsub.subscribe(f"alerts:{network_id}")

    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                data = json.loads(message["data"])
                await websocket.send_json(data)
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe(f"alerts:{network_id}")
        await r.aclose()
