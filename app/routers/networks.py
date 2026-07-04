"""
PHASE 2 — Networks Router (upgraded)
Added: GET /pressures and GET /report
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.models.db import Network, Node, Edge, get_db
from app.schemas.network import NetworkCreate, NetworkOut, NodeOut, EdgeOut, PressureMap
from app.engine.graph_builder import build_graph, graph_summary
from app.engine.pressure_solver import compute_pressures, pressure_report

router = APIRouter()

def _to_out(network):
    return NetworkOut(
        id=network.id, name=network.name, description=network.description,
        nodes=[NodeOut(id=n.id, network_id=n.network_id, name=n.name,
                       pressure_base=n.pressure_base, is_source=n.is_source,
                       x=n.x, y=n.y) for n in network.nodes],
        edges=[EdgeOut(id=e.id, network_id=e.network_id, node_from=e.node_from,
                       node_to=e.node_to, flow_rate=e.flow_rate, length_m=e.length_m,
                       roughness_c=e.roughness_c, diameter_mm=e.diameter_mm) for e in network.edges],
    )

async def _load(nid, db):
    r = await db.execute(select(Network).where(Network.id == nid)
                         .options(selectinload(Network.nodes), selectinload(Network.edges)))
    n = r.scalar_one_or_none()
    if not n: raise HTTPException(404, "Network not found")
    return n

@router.post("/", response_model=NetworkOut, status_code=201)
async def create_network(body: NetworkCreate, db: AsyncSession = Depends(get_db)):
    ex = await db.execute(select(Network).where(Network.name == body.name))
    if ex.scalar_one_or_none(): raise HTTPException(400, "Name exists")
    node_names = {n.name for n in body.nodes}
    for e in body.edges:
        if e.node_from not in node_names or e.node_to not in node_names:
            raise HTTPException(400, f"Unknown node in edge")
    net = Network(name=body.name, description=body.description)
    db.add(net); await db.flush()
    for n in body.nodes: db.add(Node(network_id=net.id, **n.model_dump()))
    for e in body.edges: db.add(Edge(network_id=net.id, **e.model_dump()))
    await db.commit()
    return _to_out(await _load(net.id, db))

@router.get("/{network_id}", response_model=NetworkOut)
async def get_network(network_id: int, db: AsyncSession = Depends(get_db)):
    return _to_out(await _load(network_id, db))

@router.delete("/{network_id}", status_code=204)
async def delete_network(network_id: int, db: AsyncSession = Depends(get_db)):
    net = await _load(network_id, db)
    await db.delete(net); await db.commit()

@router.get("/{network_id}/graph-summary")
async def graph_sum(network_id: int, db: AsyncSession = Depends(get_db)):
    return graph_summary(build_graph(await _load(network_id, db)))

@router.get("/{network_id}/pressures", response_model=PressureMap)
async def get_pressures(network_id: int, db: AsyncSession = Depends(get_db)):
    """Compute Hazen-Williams pressure at every node."""
    G = build_graph(await _load(network_id, db))
    return PressureMap(network_id=network_id, pressures=compute_pressures(G),
                       note="Hazen-Williams formula")

@router.get("/{network_id}/report")
async def get_report(network_id: int, db: AsyncSession = Depends(get_db)):
    """Full report: expected vs actual pressure + status flags."""
    G = build_graph(await _load(network_id, db))
    return pressure_report(G, compute_pressures(G))
