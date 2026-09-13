"""Board copper census: unrouted nets, analog airwires, power ampacity."""

from __future__ import annotations

import fnmatch
import math
import re

from .compile import CompiledJob
from .sexp import board_footprint_spans, footprint_at, footprint_reference, matching_paren
from .stackup import ipc2221_width_mm

_NET_DEF = re.compile(r'\(net\s+(\d+)\s+"([^"]*)"\)')
_PAD_AT = re.compile(r"\(at\s+([0-9.+-]+)\s+([0-9.+-]+)(?:\s+([0-9.+-]+))?\)")
_WIDTH = re.compile(r"\(width\s+([0-9.+-]+)\)")


def net_table(text: str) -> dict[int, str]:
    return {int(i): name for i, name in _NET_DEF.findall(text)}


def _iter_board_tag(text: str, tag: str):
    token = f"({tag}"
    start = 0
    while True:
        j = text.find(token, start)
        if j < 0:
            return
        nxt = j + len(token)
        if nxt < len(text) and (text[nxt].isalnum() or text[nxt] == "_"):
            start = nxt
            continue
        end = matching_paren(text, j)
        yield text[j : end + 1]
        start = end + 1


def _rotate(x: float, y: float, deg: float) -> tuple[float, float]:
    a = math.radians(-deg)
    c, s = math.cos(a), math.sin(a)
    return x * c - y * s, x * s + y * c


def _net_name_of(block: str, names: dict[int, str] | None = None) -> str:
    names = names or {}
    m = re.search(r'\(net "([^"]+)"\)', block)
    if m:
        raw = m.group(1)
        return names.get(int(raw), raw) if raw.isdigit() else raw
    m = re.search(r'\(net (\d+)(?: "([^"]*)")?\)', block)
    if not m:
        return ""
    if m.lastindex >= 2 and m.group(2):
        return m.group(2)
    return names.get(int(m.group(1)), "")


def pads_by_net(text: str) -> dict[str, list[tuple[str, float, float]]]:
    names = net_table(text)
    out: dict[str, list[tuple[str, float, float]]] = {}
    for start, end in board_footprint_spans(text):
        block = text[start:end]
        ref = footprint_reference(block) or "?"
        at = footprint_at(block) or (0.0, 0.0, 0.0)
        fx, fy, frot = at
        pos = 0
        while True:
            j = block.find("(pad ", pos)
            if j < 0:
                break
            k = matching_paren(block, j)
            pad = block[j : k + 1]
            pos = k + 1
            name = _net_name_of(pad, names)
            am = _PAD_AT.search(pad)
            if not name or not am:
                continue
            px, py = float(am.group(1)), float(am.group(2))
            lx, ly = _rotate(px, py, frot)
            out.setdefault(name, []).append((ref, fx + lx, fy + ly))
    return out


def copper_by_net(text: str) -> dict[str, dict[str, float]]:
    """Per net: segment count, via count, zone count, max track width mm."""
    names = net_table(text)
    hits: dict[str, dict[str, float]] = {}
    for tag in ("segment", "via", "zone"):
        for block in _iter_board_tag(text, tag):
            name = _net_name_of(block, names)
            if not name:
                continue
            rec = hits.setdefault(
                name, {"segment": 0, "via": 0, "zone": 0, "width": 0.0}
            )
            rec[tag] += 1
            if tag == "segment":
                wm = _WIDTH.search(block)
                if wm:
                    rec["width"] = max(rec["width"], float(wm.group(1)))
            if tag == "zone":
                rec["width"] = max(rec["width"], 10.0)
    return hits


def unrouted_nets(text: str) -> list[str]:
    pads = pads_by_net(text)
    copper = copper_by_net(text)
    open_nets: list[str] = []
    for name, sites in pads.items():
        if len(sites) < 2 or not name or name.startswith("unconnected-"):
            continue
        hit = copper.get(name) or {}
        if hit.get("segment") or hit.get("via") or hit.get("zone"):
            continue
        open_nets.append(name)
    return sorted(set(open_nets))


def airwire_span_mm(text: str) -> dict[str, float]:
    pads = pads_by_net(text)
    out: dict[str, float] = {}
    for name, sites in pads.items():
        if len(sites) < 2 or not name:
            continue
        span = 0.0
        for i, (_r1, x1, y1) in enumerate(sites):
            for _r2, x2, y2 in sites[i + 1 :]:
                span = max(span, math.hypot(x2 - x1, y2 - y1))
        out[name] = span
    return out


def _match(name: str, patterns: tuple[str, ...] | list[str]) -> bool:
    return any(fnmatch.fnmatch(name, pat) for pat in patterns)


def sensitive_airwire_failures(job: CompiledJob, text: str) -> list[str]:
    spans = airwire_span_mm(text)
    fails: list[str] = []
    for net in job.nets:
        if net.max_length_mm is None:
            continue
        for name, span in spans.items():
            if not _match(name, net.patterns):
                continue
            if span > float(net.max_length_mm) + 1e-6:
                fails.append(
                    f"{name} airwire {span:.1f} mm > max_mm {net.max_length_mm:g} "
                    f"({net.kind or net.class_name})"
                )
    return fails


def vias_on_no_via_nets(job: CompiledJob, text: str) -> list[str]:
    copper = copper_by_net(text)
    fails: list[str] = []
    for net in job.nets:
        if net.vias:
            continue
        for name, rec in copper.items():
            if rec.get("via") and _match(name, net.patterns):
                fails.append(f"{name} has {int(rec['via'])} via(s); NetReq vias=False")
    return fails


def power_ampacity_failures(job: CompiledJob, text: str) -> list[str]:
    """Fail when a power net's copper is narrower than IPC-2221 for its amps."""
    copper = copper_by_net(text)
    plane_nets = {n for n, _ in job.planes}
    fails: list[str] = []
    for net in job.nets:
        if net.kind != "power" or not net.amps or net.amps < 0.2:
            continue
        need = ipc2221_width_mm(float(net.amps))
        for name in [n for n in (list(copper) + list(plane_nets)) if _match(n, net.patterns)]:
            if name in plane_nets:
                continue
            have = (copper.get(name) or {}).get("width") or 0.0
            if have + 1e-6 < need * 0.85:
                fails.append(
                    f"{name} copper {have:.2f} mm < {need:.2f} mm required for "
                    f"{net.amps:g} A (add a plane or pour)"
                )
        # Pattern never seen as copper or plane
        if not any(_match(n, net.patterns) for n in list(copper) + list(plane_nets)):
            if net.amps >= 1.0:
                fails.append(
                    f"{net.patterns[0]} has no copper/plane for {net.amps:g} A "
                    f"(need ≥ {need:.2f} mm)"
                )
    return fails
