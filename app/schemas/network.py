"""
PHASE 1 — Schemas

Pydantic models for request/response.
Separate from DB models — never expose DB models directly in API responses.
"""

from pydantic import BaseModel, Field
from typing import Optional


# ── Node schemas ─────────────────────────────────────────────────────────────

class NodeIn(BaseModel):
    name:          str
    pressure_base: float = Field(default=100.0, description="Normal pressure in PSI")
    is_source:     bool  = False
    x:             float = 0.0
    y:             float = 0.0


class NodeOut(NodeIn):
    id:         int
    network_id: int


# ── Edge schemas ─────────────────────────────────────────────────────────────

class EdgeIn(BaseModel):
    node_from:   str
    node_to:     str
    flow_rate:   float = Field(default=5.0,   description="Flow in liters/second")
    length_m:    float = Field(default=100.0, description="Pipe length in meters")
    roughness_c: float = Field(default=120.0, description="Hazen-Williams roughness (100-140)")
    diameter_mm: float = Field(default=150.0, description="Pipe diameter in mm")


class EdgeOut(EdgeIn):
    id:         int
    network_id: int


# ── Network schemas ───────────────────────────────────────────────────────────

class NetworkCreate(BaseModel):
    """
    Create a network in one shot — send nodes and edges together.
    Example:
      {
        "name": "downtown",
        "nodes": [
          {"name": "pump_1", "pressure_base": 120, "is_source": true},
          {"name": "junction_A", "pressure_base": 95},
          {"name": "junction_B", "pressure_base": 90}
        ],
        "edges": [
          {"node_from": "pump_1", "node_to": "junction_A", "flow_rate": 8},
          {"node_from": "junction_A", "node_to": "junction_B", "flow_rate": 5}
        ]
      }
    """
    name:        str
    description: str = ""
    nodes:       list[NodeIn]
    edges:       list[EdgeIn]


class NetworkOut(BaseModel):
    id:          int
    name:        str
    description: str
    nodes:       list[NodeOut]
    edges:       list[EdgeOut]


# ── Pressure map schema (Phase 2 preview) ───────────────────────────────────

class PressureMap(BaseModel):
    """One pressure reading per node."""
    network_id: int
    pressures:  dict[str, float]   # node_name → pressure PSI
    note:       str = ""
