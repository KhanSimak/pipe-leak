"""
PHASE 1 — Graph Builder

Loads a Network from the database into a NetworkX DiGraph.

Why NetworkX?
  - A pipe network IS a graph: nodes = junctions, edges = pipes
  - NetworkX gives us graph algorithms for free: shortest path,
    connected components, neighbors — all useful for leak detection later
  - Each edge stores pipe metadata as attributes

This is the bridge between your DB and your physics engine.
In Phase 2, we'll run pressure calculations on this graph.
In Phase 5, we'll walk it to find leak locations.

Interview explanation:
  'We model the pipe network as a directed graph. Water flows from
   source nodes (pumping stations) through edges (pipes) to junction
   nodes. Each edge carries metadata like diameter and roughness
   that the physics equations need.'
"""

import networkx as nx
from app.models.db import Network


def build_graph(network: Network) -> nx.DiGraph:
    """
    Convert a Network DB object into a NetworkX DiGraph.

    Returns a DiGraph where:
      - Each node has attribute: pressure_base, is_source, x, y
      - Each edge has attribute: flow_rate, length_m, roughness_c, diameter_mm, edge_id
    """
    G = nx.DiGraph()

    # Add nodes with all their attributes
    for node in network.nodes:
        G.add_node(
            node.name,
            pressure_base = node.pressure_base,
            is_source     = node.is_source,
            x             = node.x,
            y             = node.y,
            node_id       = node.id,
        )

    # Add edges with pipe metadata
    for edge in network.edges:
        G.add_edge(
            edge.node_from,
            edge.node_to,
            flow_rate   = edge.flow_rate,
            length_m    = edge.length_m,
            roughness_c = edge.roughness_c,
            diameter_mm = edge.diameter_mm,
            edge_id     = edge.id,
        )

    return G


def graph_summary(G: nx.DiGraph) -> dict:
    """Human-readable summary of the graph — useful for debugging."""
    source_nodes = [n for n, d in G.nodes(data=True) if d.get("is_source")]
    return {
        "node_count":   G.number_of_nodes(),
        "edge_count":   G.number_of_edges(),
        "source_nodes": source_nodes,
        "is_connected": nx.is_weakly_connected(G),
        "nodes":        list(G.nodes()),
        "edges":        [(u, v) for u, v in G.edges()],
    }
