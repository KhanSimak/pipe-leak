"""
PHASE 3 — Pressure Readings Model (TimescaleDB hypertable)

TimescaleDB is PostgreSQL with a time-series extension.
We store every pressure snapshot here.

A hypertable automatically partitions data by time — queries like
"get all readings in the last 5 minutes" are O(1) instead of full table scan.

Interview explanation:
  'We use TimescaleDB's hypertable feature. It partitions the readings
   table by time automatically. A query for the last hour only scans
   that hour's partition, not the entire table. At 2 readings/second
   across 50 nodes, that's 360,000 rows/hour — partitioning is essential.'
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, func
from sqlalchemy.orm import DeclarativeBase
from app.models.db import Base
from datetime import datetime


class PressureReading(Base):
    """
    One row = one node's pressure at one moment in time.
    TimescaleDB partitions this by 'recorded_at' automatically.

    To convert to hypertable (run once after table creation):
      SELECT create_hypertable('pressure_readings', 'recorded_at');
    """
    __tablename__ = "pressure_readings"

    id:           int      = Column(Integer, primary_key=True, autoincrement=True)
    network_id:   int      = Column(Integer, index=True)
    node_name:    str      = Column(String(50), index=True)
    pressure_psi: float    = Column(Float)
    baseline_psi: float    = Column(Float)
    delta_psi:    float    = Column(Float)      # pressure - baseline
    has_leak:     bool     = Column(Boolean, default=False)
    recorded_at:  datetime = Column(DateTime(timezone=True),
                                    server_default=func.now(), index=True)
