# pyright: reportAttributeAccessIssue=false
"""DAG layout computation for property/risk/control visualisation.

Uses grandalf (Sugiyama layered layout) to compute node positions at build time.
The layout flows left-to-right: properties → risks/controls.
"""

from __future__ import annotations

from dataclasses import dataclass

from grandalf.graphs import Edge, Graph, Vertex
from grandalf.layouts import SugiyamaLayout, VertexViewer
from grandalf.routing import EdgeViewer, route_with_lines

from models import Control, Property, Risk

# Node dimensions in SVG units
NODE_W = 160
NODE_H = 40
X_SPACE = 30
Y_SPACE = 20
PADDING = 20


@dataclass(frozen=True)
class GraphNode:
    """A positioned node in the DAG visualisation."""

    id: str
    label: str
    description: str
    kind: str  # "property" | "risk" | "control"
    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class GraphEdge:
    """A routed edge in the DAG visualisation."""

    source_id: str
    target_id: str
    kind: str  # "parent" | "condition" | "control_in" | "control_out"
    path: str  # SVG path d attribute


@dataclass(frozen=True)
class GraphLayout:
    """Complete positioned graph ready for SVG rendering."""

    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    viewbox: str
    width: float
    height: float


def _make_label(id_str: str) -> str:
    """Convert an underscore ID to a human-readable label."""
    return id_str.replace("_", " ").title()


def _polyline_path(pts: list[tuple[float, float]]) -> str:
    """Convert waypoints to an SVG polyline path (M then L segments)."""
    if len(pts) < 2:
        return ""
    parts = [f"M {pts[0][0]:.1f} {pts[0][1]:.1f}"]
    parts.extend(f"L {x:.1f} {y:.1f}" for x, y in pts[1:])
    return " ".join(parts)


def compute_layout(
    properties: list[Property],
    risks: list[Risk],
    controls: list[Control],
) -> GraphLayout:
    """Build the DAG, run grandalf SugiyamaLayout, return positioned nodes and routed edges.

    Layout flows left-to-right by computing top-to-bottom then swapping x/y.
    """
    if not properties and not risks and not controls:
        return GraphLayout(nodes=(), edges=(), viewbox="0 0 0 0", width=0, height=0)

    # Create vertices keyed by ID
    vertices: dict[str, Vertex] = {}
    node_kinds: dict[str, str] = {}

    for p in properties:
        v = Vertex(p.id)
        v.view = VertexViewer(w=NODE_W, h=NODE_H)
        vertices[p.id] = v
        node_kinds[p.id] = "property"

    for r in risks:
        v = Vertex(r.id)
        v.view = VertexViewer(w=NODE_W, h=NODE_H)
        vertices[r.id] = v
        node_kinds[r.id] = "risk"

    for c in controls:
        v = Vertex(c.id)
        v.view = VertexViewer(w=NODE_W, h=NODE_H)
        vertices[c.id] = v
        node_kinds[c.id] = "control"

    # Build edges with kind metadata
    edges_list: list[Edge] = []
    edge_kinds: dict[tuple[str, str], str] = {}

    # Property → Property (parent edges: child depends on parent)
    for p in properties:
        for parent_id in p.parents:
            if parent_id in vertices:
                e = Edge(vertices[parent_id], vertices[p.id])
                edges_list.append(e)
                edge_kinds[(parent_id, p.id)] = "parent"

    # Property → Risk (condition references)
    for r in risks:
        seen_props: set[str] = set()
        for cond in r.conditions:
            for pid in cond.properties:
                if pid in vertices and pid not in seen_props:
                    e = Edge(vertices[pid], vertices[r.id])
                    edges_list.append(e)
                    edge_kinds[(pid, r.id)] = "condition"
                    seen_props.add(pid)

    # Property → Control (control_in) and Control → Risk (control_out)
    for c in controls:
        if c.property in vertices:
            e = Edge(vertices[c.property], vertices[c.id])
            edges_list.append(e)
            edge_kinds[(c.property, c.id)] = "control_in"

        for effect in c.effects:
            if effect.risk_id in vertices:
                e = Edge(vertices[c.id], vertices[effect.risk_id])
                edges_list.append(e)
                edge_kinds[(c.id, effect.risk_id)] = "control_out"

    # Assign edge views
    for e in edges_list:
        e.view = EdgeViewer()

    # Build graph
    all_verts = list(vertices.values())
    g = Graph(all_verts, edges_list)

    # Identify root properties (no parents, not derived)
    root_verts = [vertices[p.id] for p in properties if not p.parents]

    # Run layout on each connected component
    for component in g.C:
        roots = [v for v in root_verts if v in component.sV]
        sug = SugiyamaLayout(component)
        sug.route_edge = route_with_lines
        sug.xspace = Y_SPACE  # will become vertical after swap
        sug.yspace = X_SPACE  # will become horizontal after swap
        sug.init_all(roots=roots if roots else None)
        sug.draw(N=1.5)

    # Extract positions — swap x/y for left-to-right flow
    descriptions = {p.id: p.description for p in properties}
    descriptions.update({r.id: r.description for r in risks})
    descriptions.update({c.id: c.description for c in controls})

    graph_nodes: list[GraphNode] = []
    for nid, v in vertices.items():
        if v.view.xy is None:
            continue
        raw_x, raw_y = v.view.xy
        # Swap: grandalf's y (layer depth) becomes our x, grandalf's x becomes our y
        graph_nodes.append(
            GraphNode(
                id=nid,
                label=_make_label(nid),
                description=descriptions.get(nid, ""),
                kind=node_kinds[nid],
                x=raw_y,
                y=raw_x,
                width=NODE_W,
                height=NODE_H,
            )
        )

    # Build edge paths from routed waypoints, clipping to node borders
    node_by_id = {n.id: n for n in graph_nodes}
    graph_edges: list[GraphEdge] = []
    for e in edges_list:
        src_id = e.v[0].data
        tgt_id = e.v[1].data
        kind = edge_kinds.get((src_id, tgt_id), "parent")
        src_node = node_by_id[src_id]
        tgt_node = node_by_id[tgt_id]

        if hasattr(e.view, "_pts") and e.view._pts:
            swapped_pts = [(y, x) for x, y in e.view._pts]
        else:
            swapped_pts = [(src_node.x, src_node.y), (tgt_node.x, tgt_node.y)]

        # Clip start to right edge of source, end to left edge of target
        swapped_pts[0] = (src_node.x + NODE_W / 2, swapped_pts[0][1])
        swapped_pts[-1] = (tgt_node.x - NODE_W / 2, swapped_pts[-1][1])

        path = _polyline_path(swapped_pts)
        graph_edges.append(GraphEdge(source_id=src_id, target_id=tgt_id, kind=kind, path=path))

    # Compute viewbox
    if graph_nodes:
        min_x = min(n.x - n.width / 2 for n in graph_nodes) - PADDING
        min_y = min(n.y - n.height / 2 for n in graph_nodes) - PADDING
        max_x = max(n.x + n.width / 2 for n in graph_nodes) + PADDING
        max_y = max(n.y + n.height / 2 for n in graph_nodes) + PADDING
        vb_w = max_x - min_x
        vb_h = max_y - min_y
        viewbox = f"{min_x:.1f} {min_y:.1f} {vb_w:.1f} {vb_h:.1f}"
    else:
        min_x = min_y = 0.0
        vb_w = vb_h = 0.0
        viewbox = "0 0 0 0"

    return GraphLayout(
        nodes=tuple(graph_nodes),
        edges=tuple(graph_edges),
        viewbox=viewbox,
        width=vb_w,
        height=vb_h,
    )
