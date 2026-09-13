"""Compile pcb-space Place/Keepout/Region into a KRT floorplan-intent JSON."""

from __future__ import annotations

from .compile import CompiledJob
from .layout import resolve_keepout, resolve_regions
from .model import BoardSpec, PlaceSpec
from .refs import resolve_ref


def _is_zero(v) -> bool:
    return v == 0 or v == 0.0 or v == "0"


def place_edge(p: PlaceSpec) -> str | None:
    """Mating edge from CSS: right=0 + left unset → east (centering uses top=bottom=0)."""
    if _is_zero(p.right) and p.left is None:
        return "east"
    if _is_zero(p.left) and p.right is None:
        return "west"
    if _is_zero(p.top) and p.bottom is None:
        return "north"
    if _is_zero(p.bottom) and p.top is None:
        return "south"
    return None


def intent_from_job(job: CompiledJob, aliases: dict[str, str] | None = None) -> dict:
    aliases = aliases or {}
    w, h = job.board_size_mm
    board = BoardSpec(
        size_mm=job.board_size_mm,
        padding=job.padding,
        layers=job.layers,
        stackup=job.stackup,
        pcb=job.pcb,
        planes=job.planes,
    )
    regions = resolve_regions(board, job.regions)
    must_lock = []
    edges = []
    for p in job.places:
        kref = resolve_ref(p.ref, aliases) or p.ref
        if p.locked:
            must_lock.append(kref)
        edge = place_edge(p)
        if edge:
            edges.append(
                {
                    "ref": kref,
                    "edge": edge,
                    "overhang_mm": {"min": 0.0, "max": 2.5},
                    "note": p.reason or "",
                }
            )
    keepouts = []
    for ko in job.keepouts:
        box = ko.box or resolve_keepout(ko, board, regions)
        keepouts.append(
            {
                "name": ko.name,
                "rect": [box[0], box[1], box[2], box[3]],
                "sides": ["F", "B"],
            }
        )
    blocks = []
    for name, rect in regions.items():
        blocks.append(
            {
                "name": name,
                "refs": [],
                "zone": [rect.x0, rect.y0, rect.x1, rect.y1],
                "side": "F",
            }
        )
    return {
        "schema": 1,
        "kind": "floorplan-intent",
        "units": "mm",
        "envelope": {"rect": [0.0, 0.0, float(w), float(h)], "tolerance_mm": 0.5},
        "must_lock": must_lock,
        "edge_connectors": edges,
        "keepouts": keepouts,
        "blocks": blocks,
        "legality_budget": {
            "overlap_area": 0.0,
            # Declared edge parts kiss Edge.Cuts; KRT's board-edge clearance
            # (typically 0.4 mm) then counts them as oob. Budget that.
            "oob_count": float(len(edges)),
        },
    }
