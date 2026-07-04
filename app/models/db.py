"""
PHASE 1 — Database

Simple SQLAlchemy models for:
  - Network (a named pipe network)
  - Node   (a junction in the network, has a pressure value)
  - Edge   (a pipe connecting two nodes, has flow rate and length)

This is the raw data store. In Phase 2 we load these into a NetworkX graph.
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, Float, ForeignKey, JSON
from typing import AsyncGenerator
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://pipe:pipe@localhost:5432/pipe_db")
print("=" * 50)
print(DATABASE_URL)
print("=" * 50)
engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Network(Base):
    """A named pipe network — container for nodes and edges."""
    __tablename__ = "networks"

    id:          Mapped[int]    = mapped_column(primary_key=True)
    name:        Mapped[str]    = mapped_column(String(100), unique=True)
    description: Mapped[str]    = mapped_column(String(500), default="")

    nodes: Mapped[list["Node"]] = relationship("Node", back_populates="network", cascade="all, delete")
    edges: Mapped[list["Edge"]] = relationship("Edge", back_populates="network", cascade="all, delete")


class Node(Base):
    """
    A junction in the pipe network.
    pressure_base = normal operating pressure (PSI)
    is_source     = True if this is a water supply node (pumping station)
    """
    __tablename__ = "nodes"

    id:            Mapped[int]   = mapped_column(primary_key=True)
    network_id:    Mapped[int]   = mapped_column(ForeignKey("networks.id"))
    name:          Mapped[str]   = mapped_column(String(50))
    pressure_base: Mapped[float] = mapped_column(Float, default=100.0)  # PSI
    is_source:     Mapped[bool]  = mapped_column(default=False)
    x:             Mapped[float] = mapped_column(Float, default=0.0)    # for visualization
    y:             Mapped[float] = mapped_column(Float, default=0.0)

    network: Mapped["Network"] = relationship("Network", back_populates="nodes")


class Edge(Base):
    """
    A pipe connecting two nodes.
    flow_rate   = liters/second through this pipe
    length_m    = pipe length in meters
    roughness_c = Hazen-Williams roughness coefficient (140 = new pipe, 100 = older pipe)
    diameter_mm = pipe diameter in millimeters
    """
    __tablename__ = "edges"

    id:          Mapped[int]   = mapped_column(primary_key=True)
    network_id:  Mapped[int]   = mapped_column(ForeignKey("networks.id"))
    node_from:   Mapped[str]   = mapped_column(String(50))   # node name
    node_to:     Mapped[str]   = mapped_column(String(50))   # node name
    flow_rate:   Mapped[float] = mapped_column(Float, default=5.0)    # L/s
    length_m:    Mapped[float] = mapped_column(Float, default=100.0)  # meters
    roughness_c: Mapped[float] = mapped_column(Float, default=120.0)  # HW coefficient
    diameter_mm: Mapped[float] = mapped_column(Float, default=150.0)  # mm

    network: Mapped["Network"] = relationship("Network", back_populates="edges")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
