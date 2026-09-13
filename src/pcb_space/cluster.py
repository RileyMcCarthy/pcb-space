"""Pull unlocked analog/switch-node parts toward their net cluster."""

from __future__ import annotations

import math
import re

from .compile import CompiledJob
from .copper import _match, pads_by_net
from .geom import footprint_box_local
from .sexp import board_footprint_spans, footprint_at, footprint_reference


def set_footprint_at(block: str, x: float, y: float, rot: float) -> str:
    m = re.search(r"\n\t\t\(at [0-9.+-]+ [0-9.+-]+(?: [0-9.+-]+)?\)", block)
    new = f"\n\t\t(at {x:.4f} {y:.4f} {rot:g})"
    if m:
        return block[: m.start()] + new + block[m.end() :]
    m = re.search(r"\(at [0-9.+-]+ [0-9.+-]+(?: [0-9.+-]+)?\)", block)
    if not m:
        return block
    new = f"(at {x:.4f} {y:.4f} {rot:g})"
    return block[: m.start()] + new + block[m.end() :]


def _aabb(block: str, at: tuple[float, float, float]) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = footprint_box_local(block, "courtyard")
    fx, fy, rot = at
    rad = math.radians(-rot)
    c, s = math.cos(rad), math.sin(rad)
    xs, ys = [], []
    for px, py in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        wx = fx + px * c - py * s
        wy = fy + px * s + py * c
        xs.append(wx)
        ys.append(wy)
    return (min(xs), min(ys), max(xs), max(ys))


def _overlap(a, b, gap: float = 0.2) -> bool:
    return not (
        a[2] + gap <= b[0] or b[2] + gap <= a[0] or a[3] + gap <= b[1] or b[3] + gap <= a[1]
    )


def cluster_sensitive(job: CompiledJob, text: str) -> tuple[str, list[dict]]:
    """Move unlocked parts on analog/SW nets toward locked pads on the same net."""
    locked = {p.ref for p in job.places if p.locked}
    pads = pads_by_net(text)
    spans = {start: (start, end) for start, end in board_footprint_spans(text)}
    blocks = {
        footprint_reference(text[s:e]) or "?": (s, e, text[s:e])
        for s, e in board_footprint_spans(text)
    }
    moves: list[dict] = []
    new_pos: dict[str, tuple[float, float, float]] = {}

    targets: list[tuple[str, float, str, float, float]] = []
    for net in job.nets:
        if net.kind not in ("analog", "switch_node"):
            continue
        cap = float(net.max_length_mm or (8.0 if net.kind == "switch_node" else 25.0))
        for name, sites in pads.items():
            if not _match(name, net.patterns) or len(sites) < 2:
                continue
            anchors = [(r, x, y) for r, x, y in sites if r in locked]
            if not anchors:
                anchors = sites
            tx = sum(p[1] for p in anchors) / len(anchors)
            ty = sum(p[2] for p in anchors) / len(anchors)
            for ref, px, py in sites:
                if ref in locked:
                    continue
                targets.append((ref, cap, name, tx, ty))

    # Unique ref: use the tightest cap / first target
    seen: set[str] = set()
    for ref, cap, name, tx, ty in targets:
        if ref in seen or ref not in blocks:
            continue
        seen.add(ref)
        s, e, block = blocks[ref]
        at = footprint_at(block) or (0.0, 0.0, 0.0)
        # pad offset from footprint origin — use first pad of this ref on this net
        pad = next(((x, y) for r, x, y in pads.get(name, []) if r == ref), (at[0], at[1]))
        dist = math.hypot(pad[0] - tx, pad[1] - ty)
        want = min(5.0, max(2.0, cap * 0.5))
        if dist <= want + 0.05:
            continue
        scale = (dist - want) / dist if dist else 0
        dx = (tx - pad[0]) * scale
        dy = (ty - pad[1]) * scale
        nx, ny, nrot = at[0] + dx, at[1] + dy, at[2]
        trial = set_footprint_at(block, nx, ny, nrot)
        trial_box = _aabb(trial, (nx, ny, nrot))
        clash = False
        for other, (_os, _oe, oblock) in blocks.items():
            if other == ref:
                continue
            oat = new_pos.get(other) or footprint_at(oblock) or (0.0, 0.0, 0.0)
            if _overlap(trial_box, _aabb(oblock if other not in new_pos else set_footprint_at(oblock, *oat), oat)):
                clash = True
                break
        if clash:
            continue
        new_pos[ref] = (nx, ny, nrot)
        blocks[ref] = (s, e, trial)
        moves.append({"ref": ref, "net": name, "from": [at[0], at[1]], "to": [nx, ny]})

    if not moves:
        return text, []
    # rebuild from the end so offsets stay valid
    pieces = []
    last = 0
    ordered = sorted((blocks[r][0], r) for r in blocks)
    for start, ref in ordered:
        _s, end, block = blocks[ref]
        pieces.append(text[last:start])
        pieces.append(block if ref in new_pos else text[start:end])
        last = end
    pieces.append(text[last:])
    return "".join(pieces), moves
