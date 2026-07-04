"""
PHASE 4 — WebSocket Manager

Manages all active WebSocket connections across all networks.
Allows broadcasting pressure updates to all connected clients at once.

Interview explanation:
  'We maintain a dict of connection pools per network_id.
   When a pressure tick fires, we broadcast to all connections
   in that network's pool. Disconnected clients are cleaned up
   automatically — we catch the exception and remove them.'
"""

from fastapi import WebSocket
import asyncio
import logging

logger = logging.getLogger(__name__)


class WebSocketManager:
    def __init__(self):
        # network_id → set of active WebSocket connections
        self._connections: dict[int, set[WebSocket]] = {}

    async def connect(self, network_id: int, ws: WebSocket):
        await ws.accept()
        if network_id not in self._connections:
            self._connections[network_id] = set()
        self._connections[network_id].add(ws)
        logger.info(f"WS connected: network {network_id} | total: {self.count(network_id)}")

    def disconnect(self, network_id: int, ws: WebSocket):
        if network_id in self._connections:
            self._connections[network_id].discard(ws)
        logger.info(f"WS disconnected: network {network_id} | remaining: {self.count(network_id)}")

    def count(self, network_id: int) -> int:
        return len(self._connections.get(network_id, set()))

    async def broadcast(self, network_id: int, data: dict):
        """
        Send data to all connected clients for this network.
        Remove dead connections silently.
        """
        connections = self._connections.get(network_id, set()).copy()
        dead = set()

        for ws in connections:
            try:
                await ws.send_json(data)
            except Exception:
                dead.add(ws)

        # Clean up dead connections
        for ws in dead:
            self._connections[network_id].discard(ws)

    async def send_alert(self, network_id: int, alert: dict):
        """Broadcast an alert to all clients."""
        await self.broadcast(network_id, {"type": "alert", **alert})


# Single global instance — shared across all routes
manager = WebSocketManager()
