"""
PHASE 4 — Celery Background Monitor

A Celery beat task that runs every 2 seconds:
  1. For each active network, compute current pressures
  2. Compare against baseline
  3. Broadcast via WebSocket to connected clients
  4. If anomaly detected → trigger alert

Interview explanation:
  'Celery beat is a scheduler built into Celery. We use it like a cron
   job that fires every 2 seconds. Each tick computes pressures and
   broadcasts to WebSocket clients. This separates the monitoring loop
   from the HTTP request-response cycle — the API stays fast even when
   the monitor is doing heavy computation.'
"""

from celery import Celery
from celery.schedules import crontab
import redis
import json
import os

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

celery_app = Celery("pipe_monitor", broker=REDIS_URL, backend=REDIS_URL)

celery_app.conf.beat_schedule = {
    "monitor-all-networks": {
        "task":     "app.workers.monitor_task.monitor_all_networks",
        "schedule": 2.0,   # every 2 seconds
    }
}


ALERT_THRESHOLD_PSI = 10.0   # flag if pressure drops more than 10 PSI


@celery_app.task(name="app.workers.monitor_task.monitor_all_networks")
def monitor_all_networks():
    """
    Celery task: check all active networks for pressure anomalies.
    Writes alerts to Redis pub/sub — WebSocket router subscribes and broadcasts.

    Flow:
      Celery tick → detect anomaly → publish to Redis channel
      WebSocket route → subscribe to Redis → push to browser clients
    """
    r = redis.from_url(REDIS_URL)

    # Get list of active network IDs from Redis
    active_ids = r.smembers("active_networks")
    if not active_ids:
        return

    for network_id_bytes in active_ids:
        network_id = int(network_id_bytes)
        _check_network(r, network_id)


def _check_network(r: redis.Redis, network_id: int):
    """Read current state from Redis and check for anomalies."""
    raw = r.get(f"network_state:{network_id}")
    if not raw:
        return

    state = json.loads(raw)
    pressures = state.get("pressures", {})
    baselines = state.get("baselines", {})

    alerts = []
    for node, pressure in pressures.items():
        baseline = baselines.get(node, pressure)
        drop = baseline - pressure
        if drop > ALERT_THRESHOLD_PSI:
            alerts.append({
                "node":         node,
                "pressure_psi": pressure,
                "baseline_psi": baseline,
                "drop_psi":     round(drop, 2),
                "severity":     "critical" if drop > 25 else "warning",
            })

    if alerts:
        alert_msg = json.dumps({
            "type":       "pressure_alert",
            "network_id": network_id,
            "alerts":     alerts,
        })
        # Publish to Redis channel — WebSocket handler subscribes to this
        r.publish(f"alerts:{network_id}", alert_msg)

    # Publish regular tick to all subscribers (for live graph updates)
    tick_msg = json.dumps({
        "type":       "pressure_tick",
        "network_id": network_id,
        "pressures":  pressures,
    })
    r.publish(f"ticks:{network_id}", tick_msg)
