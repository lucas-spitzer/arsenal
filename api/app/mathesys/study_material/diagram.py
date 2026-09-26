"""Deterministic diagram layout and SVG rendering.

The model only describes nodes and connections. Everything geometric (node
sizing, layering, ordering, routing, bounds) happens here so diagrams stay
legible and consistent with the theme.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from html import escape
from typing import Any

LAYOUTS = frozenset({"flow", "hierarchy", "cycle"})
DIRECTIONS = frozenset({"TB", "LR"})
MAX_NODES = 16
MAX_LABEL_CHARS = 60
MAX_DETAIL_CHARS = 90

LABEL_PX = 13.0
DETAIL_PX = 10.5
LINE_HEIGHT = 1.25
CHAR_WIDTH = 0.56
PAD_X = 12.0
PAD_Y = 9.0
MIN_NODE_WIDTH = 84.0
LAYER_GAP = 56.0
NODE_GAP = 26.0
MARGIN = 14.0

_ID_CLEAN = re.compile(r"[^a-zA-Z0-9_-]+")


class DiagramError(ValueError):
    """The model returned diagram data the renderer cannot use."""


@dataclass
class DiagramNode:
    id: str
    label: str
    detail: str = ""
    emphasis: bool = False
    label_lines: list[str] = field(default_factory=list)
    detail_lines: list[str] = field(default_factory=list)
    width: float = 0.0
    height: float = 0.0
    x: float = 0.0
    y: float = 0.0

    @property
    def cx(self) -> float:
        return self.x + self.width / 2

    @property
    def cy(self) -> float:
        return self.y + self.height / 2


@dataclass(frozen=True)
class DiagramEdge:
    source: str
    target: str
    label: str = ""


@dataclass
class DiagramSpec:
    layout: str
    direction: str
    nodes: list[DiagramNode]
    edges: list[DiagramEdge]
    caption: str = ""


@dataclass(frozen=True)
class RenderedDiagram:
    svg: str
    width: float
    height: float

    @property
    def aspect(self) -> float:
        return round(self.width / self.height, 4) if self.height else 1.0


def _text(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def parse_diagram_spec(payload: dict[str, Any]) -> DiagramSpec:
    layout = str(payload.get("layout") or "flow").strip().lower()
    if layout not in LAYOUTS:
        layout = "flow"
    direction = str(payload.get("direction") or "TB").strip().upper()
    if direction not in DIRECTIONS:
        direction = "TB"

    nodes: list[DiagramNode] = []
    seen: set[str] = set()
    raw_ids: dict[str, str] = {}
    for index, raw in enumerate(payload.get("nodes") or []):
        if not isinstance(raw, dict):
            continue
        label = _text(raw.get("label"), MAX_LABEL_CHARS)
        if not label:
            continue
        raw_id = str(raw.get("id") or f"n{index}")
        node_id = _ID_CLEAN.sub("-", raw_id).strip("-") or f"n{index}"
        if node_id in seen:
            node_id = f"{node_id}-{index}"
        seen.add(node_id)
        raw_ids.setdefault(raw_id, node_id)
        nodes.append(
            DiagramNode(
                id=node_id,
                label=label,
                detail=_text(raw.get("detail"), MAX_DETAIL_CHARS),
                emphasis=bool(raw.get("emphasis")),
            ),
        )
        if len(nodes) >= MAX_NODES:
            break

    if len(nodes) < 2:
        raise DiagramError("A diagram needs at least two labeled nodes.")

    # Keep at most one emphasized node so the accent stays a signal.
    emphasized = [node for node in nodes if node.emphasis]
    for node in emphasized[1:]:
        node.emphasis = False

    ids = {node.id for node in nodes}
    edges: list[DiagramEdge] = []
    pairs: set[tuple[str, str]] = set()
    for raw in payload.get("connections") or payload.get("edges") or []:
        if not isinstance(raw, dict):
            continue
        source = raw_ids.get(str(raw.get("from")), str(raw.get("from")))
        target = raw_ids.get(str(raw.get("to")), str(raw.get("to")))
        if source not in ids or target not in ids or source == target:
            continue
        if (source, target) in pairs:
            continue
        pairs.add((source, target))
        edges.append(DiagramEdge(source=source, target=target, label=_text(raw.get("label"), 28)))

    return DiagramSpec(
        layout=layout,
        direction=direction,
        nodes=nodes,
        edges=edges,
        caption=_text(payload.get("caption") or payload.get("title"), 140),
    )


def _wrap(text: str, max_chars: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if len(candidate) <= max_chars or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _measure(node: DiagramNode, *, max_chars: int) -> None:
    node.label_lines = _wrap(node.label, max_chars)
    node.detail_lines = _wrap(node.detail, max_chars + 6) if node.detail else []
    label_w = max(len(line) for line in node.label_lines) * LABEL_PX * CHAR_WIDTH
    detail_w = max((len(line) for line in node.detail_lines), default=0) * DETAIL_PX * CHAR_WIDTH
    node.width = max(MIN_NODE_WIDTH, max(label_w, detail_w) + 2 * PAD_X)
    node.height = (
        len(node.label_lines) * LABEL_PX * LINE_HEIGHT
        + len(node.detail_lines) * DETAIL_PX * LINE_HEIGHT
        + (4 if node.detail_lines else 0)
        + 2 * PAD_Y
    )


def _break_cycles(nodes: list[DiagramNode], edges: list[DiagramEdge]) -> set[tuple[str, str]]:
    """Return edges to treat as reversed so layering sees a DAG."""
    outgoing: dict[str, list[str]] = {node.id: [] for node in nodes}
    for edge in edges:
        outgoing[edge.source].append(edge.target)
    state: dict[str, int] = {}
    reversed_edges: set[tuple[str, str]] = set()

    def visit(node_id: str) -> None:
        state[node_id] = 1
        for target in outgoing[node_id]:
            if state.get(target) == 1:
                reversed_edges.add((node_id, target))
            elif target not in state:
                visit(target)
        state[node_id] = 2

    for node in nodes:
        if node.id not in state:
            visit(node.id)
    return reversed_edges


def _assign_layers(nodes: list[DiagramNode], edges: list[DiagramEdge]) -> list[list[DiagramNode]]:
    reversed_edges = _break_cycles(nodes, edges)
    parents: dict[str, list[str]] = {node.id: [] for node in nodes}
    for edge in edges:
        source, target = edge.source, edge.target
        if (source, target) in reversed_edges:
            source, target = target, source
        parents[target].append(source)

    layer_of: dict[str, int] = {}

    def depth(node_id: str, trail: frozenset[str]) -> int:
        if node_id in layer_of:
            return layer_of[node_id]
        if node_id in trail:
            return 0
        value = 0
        for parent in parents[node_id]:
            value = max(value, depth(parent, trail | {node_id}) + 1)
        layer_of[node_id] = value
        return value

    for node in nodes:
        depth(node.id, frozenset())

    count = max(layer_of.values(), default=0) + 1
    layers: list[list[DiagramNode]] = [[] for _ in range(count)]
    for node in nodes:
        layers[layer_of[node.id]].append(node)

    # Barycenter sweeps reduce crossings while keeping author order as the tiebreak.
    neighbors: dict[str, set[str]] = {node.id: set() for node in nodes}
    for edge in edges:
        neighbors[edge.source].add(edge.target)
        neighbors[edge.target].add(edge.source)
    for _ in range(4):
        for index in range(1, len(layers)):
            _order_by_barycenter(layers[index], layers[index - 1], neighbors)
        for index in range(len(layers) - 2, -1, -1):
            _order_by_barycenter(layers[index], layers[index + 1], neighbors)
    return [layer for layer in layers if layer]


def _order_by_barycenter(
    layer: list[DiagramNode],
    reference: list[DiagramNode],
    neighbors: dict[str, set[str]],
) -> None:
    position = {node.id: index for index, node in enumerate(reference)}
    original = {node.id: index for index, node in enumerate(layer)}

    def key(node: DiagramNode) -> tuple[float, int]:
        linked = [position[other] for other in neighbors[node.id] if other in position]
        center = sum(linked) / len(linked) if linked else float(original[node.id])
        return (center, original[node.id])

    layer.sort(key=key)


def _layout_layered(spec: DiagramSpec) -> None:
    horizontal = spec.direction == "LR"
    for node in spec.nodes:
        _measure(node, max_chars=16 if horizontal else 20)
    layers = _assign_layers(spec.nodes, spec.edges)

    if not horizontal:
        widths = [sum(node.width for node in layer) + NODE_GAP * (len(layer) - 1) for layer in layers]
        span = max(widths)
        y = 0.0
        for layer, width in zip(layers, widths):
            x = (span - width) / 2
            tallest = max(node.height for node in layer)
            for node in layer:
                node.x = x
                node.y = y + (tallest - node.height) / 2
                x += node.width + NODE_GAP
            y += tallest + LAYER_GAP
    else:
        heights = [sum(node.height for node in layer) + NODE_GAP * (len(layer) - 1) for layer in layers]
        span = max(heights)
        x = 0.0
        for layer, height in zip(layers, heights):
            y = (span - height) / 2
            widest = max(node.width for node in layer)
            for node in layer:
                node.x = x + (widest - node.width) / 2
                node.y = y
                y += node.height + NODE_GAP
            x += widest + LAYER_GAP * 1.2


def _layout_cycle(spec: DiagramSpec) -> None:
    for node in spec.nodes:
        _measure(node, max_chars=16)
    count = len(spec.nodes)
    perimeter = sum(max(node.width, node.height) for node in spec.nodes) + count * NODE_GAP * 1.6
    radius_x = max(110.0, perimeter / (2 * math.pi) * 1.15)
    radius_y = max(90.0, radius_x * 0.78)
    for index, node in enumerate(spec.nodes):
        angle = -math.pi / 2 + index * 2 * math.pi / count
        node.x = radius_x * math.cos(angle) - node.width / 2
        node.y = radius_y * math.sin(angle) - node.height / 2


def _clip_to_box(node: DiagramNode, toward_x: float, toward_y: float) -> tuple[float, float]:
    """Point where the line from the node center toward (x, y) leaves its box."""
    dx = toward_x - node.cx
    dy = toward_y - node.cy
    if dx == 0 and dy == 0:
        return node.cx, node.cy
    half_w = node.width / 2 + 2
    half_h = node.height / 2 + 2
    scale = min(
        half_w / abs(dx) if dx else math.inf,
        half_h / abs(dy) if dy else math.inf,
    )
    return node.cx + dx * scale, node.cy + dy * scale


BACK_EDGE_OFFSET = 26.0


def _is_back_edge(spec: DiagramSpec, source: DiagramNode, target: DiagramNode) -> bool:
    if spec.layout == "cycle":
        return False
    if spec.direction == "TB":
        return target.y + target.height < source.y
    return target.x + target.width < source.x


def _edge_path(
    spec: DiagramSpec,
    source: DiagramNode,
    target: DiagramNode,
    *,
    far_edge: float,
) -> tuple[str, float, float]:
    """Return the path plus a label anchor. Back edges loop around the outside."""
    if _is_back_edge(spec, source, target):
        out = far_edge + BACK_EDGE_OFFSET
        if spec.direction == "TB":
            sx, sy = source.x + source.width + 2, source.cy
            tx, ty = target.x + target.width + 2, target.cy
            path = f"M{sx:.1f},{sy:.1f} C{out:.1f},{sy:.1f} {out:.1f},{ty:.1f} {tx:.1f},{ty:.1f}"
            return path, (sx + tx + 6 * out) / 8, (sy + ty) / 2
        sx, sy = source.cx, source.y + source.height + 2
        tx, ty = target.cx, target.y + target.height + 2
        path = f"M{sx:.1f},{sy:.1f} C{sx:.1f},{out:.1f} {tx:.1f},{out:.1f} {tx:.1f},{ty:.1f}"
        return path, (sx + tx) / 2, (sy + ty + 6 * out) / 8

    if spec.layout == "cycle":
        mid_x = (source.cx + target.cx) / 2
        mid_y = (source.cy + target.cy) / 2
        ctrl_x = mid_x * 1.25
        ctrl_y = mid_y * 1.25
        sx, sy = _clip_to_box(source, ctrl_x, ctrl_y)
        tx, ty = _clip_to_box(target, ctrl_x, ctrl_y)
        label_x = 0.25 * sx + 0.5 * ctrl_x + 0.25 * tx
        label_y = 0.25 * sy + 0.5 * ctrl_y + 0.25 * ty
        return f"M{sx:.1f},{sy:.1f} Q{ctrl_x:.1f},{ctrl_y:.1f} {tx:.1f},{ty:.1f}", label_x, label_y

    if spec.direction == "TB" and target.y > source.y + source.height:
        sx, sy = source.cx, source.y + source.height + 2
        tx, ty = target.cx, target.y - 2
        mid = (sy + ty) / 2
        return f"M{sx:.1f},{sy:.1f} C{sx:.1f},{mid:.1f} {tx:.1f},{mid:.1f} {tx:.1f},{ty:.1f}", (sx + tx) / 2, mid

    if spec.direction == "LR" and target.x > source.x + source.width:
        sx, sy = source.x + source.width + 2, source.cy
        tx, ty = target.x - 2, target.cy
        mid = (sx + tx) / 2
        return f"M{sx:.1f},{sy:.1f} C{mid:.1f},{sy:.1f} {mid:.1f},{ty:.1f} {tx:.1f},{ty:.1f}", mid, (sy + ty) / 2

    sx, sy = _clip_to_box(source, target.cx, target.cy)
    tx, ty = _clip_to_box(target, source.cx, source.cy)
    return f"M{sx:.1f},{sy:.1f} L{tx:.1f},{ty:.1f}", (sx + tx) / 2, (sy + ty) / 2


def render_diagram_svg(spec: DiagramSpec, style: dict[str, Any]) -> RenderedDiagram:
    if spec.layout == "cycle":
        _layout_cycle(spec)
    else:
        _layout_layered(spec)

    by_id = {node.id: node for node in spec.nodes}
    nodes_right = max(node.x + node.width for node in spec.nodes)
    nodes_bottom = max(node.y + node.height for node in spec.nodes)
    far_edge = nodes_right if spec.direction == "TB" else nodes_bottom
    has_back_edges = any(_is_back_edge(spec, by_id[edge.source], by_id[edge.target]) for edge in spec.edges)
    loop_room = BACK_EDGE_OFFSET * 0.8 if has_back_edges else 0.0

    min_x = min(node.x for node in spec.nodes) - MARGIN
    min_y = min(node.y for node in spec.nodes) - MARGIN
    max_x = nodes_right + MARGIN + (loop_room if spec.direction == "TB" else 0)
    max_y = nodes_bottom + MARGIN + (loop_room if spec.direction == "LR" else 0)
    width = max_x - min_x
    height = max_y - min_y

    node_fill = escape(str(style.get("node_fill") or "#FFFFFF"))
    node_stroke = escape(str(style.get("node_stroke") or "#000000"))
    node_text = escape(str(style.get("node_text") or "#000000"))
    emphasis_fill = escape(str(style.get("emphasis_fill") or "#940000"))
    emphasis_text = escape(str(style.get("emphasis_text") or "#FFFFFF"))
    edge_color = escape(str(style.get("edge") or "#000000"))
    edge_label = escape(str(style.get("edge_label") or edge_color))
    font = escape(str(style.get("font_family") or "Arial, Helvetica, sans-serif"), quote=True)
    stroke_width = float(style.get("stroke_width") or 1.4)
    radius = float(style.get("corner_radius") or 0)

    title = spec.caption or spec.nodes[0].label
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{min_x:.1f} {min_y:.1f} {width:.1f} {height:.1f}" '
        f'width="{width:.0f}" height="{height:.0f}" role="img" aria-label="{escape(title, quote=True)}" '
        f'font-family="{font}" preserveAspectRatio="xMidYMid meet">',
        f"<title>{escape(title)}</title>",
        "<defs>"
        '<marker id="sm-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        f'<path d="M0,0 L10,5 L0,10 z" fill="{edge_color}" /></marker>'
        "</defs>",
    ]

    for edge in spec.edges:
        path, label_x, label_y = _edge_path(spec, by_id[edge.source], by_id[edge.target], far_edge=far_edge)
        parts.append(
            f'<path d="{path}" fill="none" stroke="{edge_color}" stroke-width="{stroke_width}" marker-end="url(#sm-arrow)" />',
        )
        if edge.label:
            label_w = len(edge.label) * DETAIL_PX * CHAR_WIDTH + 8
            parts.append(
                f'<rect x="{label_x - label_w / 2:.1f}" y="{label_y - 8:.1f}" width="{label_w:.1f}" height="16" fill="#FFFFFF" />'
                f'<text x="{label_x:.1f}" y="{label_y + 3.5:.1f}" text-anchor="middle" font-size="{DETAIL_PX}" fill="{edge_label}">{escape(edge.label)}</text>',
            )

    for node in spec.nodes:
        fill = emphasis_fill if node.emphasis else node_fill
        stroke = emphasis_fill if node.emphasis else node_stroke
        ink = emphasis_text if node.emphasis else node_text
        parts.append(
            f'<rect x="{node.x:.1f}" y="{node.y:.1f}" width="{node.width:.1f}" height="{node.height:.1f}" '
            f'rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}" />',
        )
        y = node.y + PAD_Y + LABEL_PX
        for line in node.label_lines:
            parts.append(
                f'<text x="{node.cx:.1f}" y="{y:.1f}" text-anchor="middle" font-size="{LABEL_PX}" font-weight="700" fill="{ink}">{escape(line)}</text>',
            )
            y += LABEL_PX * LINE_HEIGHT
        if node.detail_lines:
            y += 4 - (LABEL_PX - DETAIL_PX)
            for line in node.detail_lines:
                parts.append(
                    f'<text x="{node.cx:.1f}" y="{y:.1f}" text-anchor="middle" font-size="{DETAIL_PX}" fill="{ink}">{escape(line)}</text>',
                )
                y += DETAIL_PX * LINE_HEIGHT

    parts.append("</svg>")
    return RenderedDiagram(svg="".join(parts), width=round(width, 1), height=round(height, 1))


def diagram_summary(spec: DiagramSpec) -> str:
    """Plain-language description used as text-generation context and alt text."""
    labels = ", ".join(node.label for node in spec.nodes)
    return f"{spec.layout} diagram with {len(spec.nodes)} nodes: {labels}"
