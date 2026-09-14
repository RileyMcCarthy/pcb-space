"""Make a Zener-applied .kicad_sch show net names on pin stubs.

`pcb apply schematic` drops a 1.27 mm local label on the pin (invisible at
A1-page zoom) and only draws wires for Power()/Ground() symbols. This
rewriter:

- ICs/connectors only (skip R/C/L — those already have GND/VCC symbols)
- hide on-box pin names so they do not fight the net labels
- signal nets (2+ pins): a straight stub as long as the name, with the
  local label sitting on the wire (underlined), not beside it
- stubs that would hit another symbol or label are pushed out or skipped
- unused one-pin nets are left unlabeled
- power nets: keep existing GND/VCC symbols
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from pathlib import Path

from .sexp import matching_paren, new_uuid

_COMP = re.compile(
    r'\(comp \(ref "([^"]+)"\)\s+\(value "([^"]*)"\)\s+\(footprint "([^"]*)"',
)
_NET_BLOCK = re.compile(
    r'\(net \(code "[^"]*"\) \(name "([^"]*)"\)(.*?)(?=\n    \(net |\n  \)\n\))',
    re.S,
)
_NODE = re.compile(r'\(node \(ref "([^"]+)"\) \(pin "([^"]*)"\)')


def parse_netlist(text: str) -> tuple[list[dict], list[dict]]:
    comps = [
        {
            "ref": m.group(1),
            "value": m.group(2),
            "footprint": m.group(3).split(":")[-1],
        }
        for m in _COMP.finditer(text)
    ]
    nets = []
    for m in _NET_BLOCK.finditer(text):
        nodes = [{"ref": r, "pin": p} for r, p in _NODE.findall(m.group(2))]
        nets.append({"name": m.group(1), "nodes": nodes})
    return comps, nets

_PIN_AT = re.compile(r"\(at\s+([0-9.+-]+)\s+([0-9.+-]+)(?:\s+([0-9.+-]+))?\)")
_PIN_NUM = re.compile(r'\(number "([^"]*)"')
_LIB_ID = re.compile(r'\(lib_id "([^"]+)"\)')
_REF = re.compile(r'\(property "Reference" "([^"]*)"')
_INST_AT = re.compile(r"\(at\s+([0-9.+-]+)\s+([0-9.+-]+)(?:\s+([0-9.+-]+))?\)")
_WIRE_XY = re.compile(r"\(xy\s+([0-9.+-]+)\s+([0-9.+-]+)\)")

_POWER_NETS = {
    "GND",
    "VCC",
    "VDD",
    "VSS",
    "VBUS",
    "VIN",
    "+12V",
    "+5V",
    "+3V3",
    "P3V3",
    "3V3",
    "DVDD1",
    "DVDD2",
}
_STUB_MIN = 5.08
_FONT = 1.27
_CHAR_W = 0.95
_PASSIVE_REF = re.compile(r"^[RCL]\d")
_RECT = re.compile(
    r"\(rectangle\s+\(start\s+([0-9.+-]+)\s+([0-9.+-]+)\)\s+\(end\s+([0-9.+-]+)\s+([0-9.+-]+)\)",
    re.S,
)


def is_power_net(name: str) -> bool:
    n = (name or "").strip()
    if not n or n.startswith("unconnected") or n.endswith(".NC"):
        return False
    if n in _POWER_NETS or n.startswith("+") or n.startswith("-"):
        return True
    if n.upper() in _POWER_NETS:
        return True
    return n.upper().startswith("VCC") or n.upper().startswith("VDD")


def pin_to_net(nets: list[dict]) -> dict[tuple[str, str], str]:
    out: dict[tuple[str, str], str] = {}
    for net in nets:
        name = net["name"]
        if not name or name.startswith("unconnected") or name.endswith(".NC"):
            continue
        for node in net["nodes"]:
            out[(node["ref"], node["pin"])] = name
            if "@" in node["pin"]:
                out.setdefault((node["ref"], node["pin"].split("@", 1)[0]), name)
    return out


def _rotate(x: float, y: float, deg: float) -> tuple[float, float]:
    rad = math.radians(deg)
    c, s = math.cos(rad), math.sin(rad)
    return x * c - y * s, x * s + y * c


def _top_spans(text: str, tag: str, *, after: int = 0) -> list[tuple[int, int]]:
    needle = f"\n\t({tag}"
    spans: list[tuple[int, int]] = []
    start = after
    while True:
        j = text.find(needle, start)
        if j < 0:
            break
        open_at = text.find("(", j)
        end = matching_paren(text, open_at)
        spans.append((open_at, end + 1))
        start = end + 1
    return spans


def _lib_symbols_range(text: str) -> tuple[int, int]:
    j = text.find("(lib_symbols")
    if j < 0:
        return (-1, -1)
    return (j, matching_paren(text, j) + 1)


def parse_lib_pins(lib_block: str) -> dict[str, tuple[float, float, float]]:
    """pin number → (x, y, rot°) in the symbol's local frame (connection point)."""
    pins: dict[str, tuple[float, float, float]] = {}
    pos = 0
    while True:
        j = lib_block.find("\n\t\t\t\t(pin ", pos)
        if j < 0:
            j = lib_block.find("\n\t\t\t(pin ", pos)
        if j < 0:
            break
        open_at = lib_block.find("(", j)
        end = matching_paren(lib_block, open_at)
        block = lib_block[open_at : end + 1]
        pos = end + 1
        am = _PIN_AT.search(block)
        nm = _PIN_NUM.search(block)
        if not am or not nm:
            continue
        pins[nm.group(1)] = (
            float(am.group(1)),
            float(am.group(2)),
            float(am.group(3) or 0),
        )
    return pins


def _is_passive(ref: str) -> bool:
    return bool(_PASSIVE_REF.match(ref or ""))


def _label_box(
    name: str, x: float, y: float, rot: int, justify: str = "left"
) -> tuple[float, float, float, float]:
    w = max(len(name), 1) * _FONT * _CHAR_W + 0.6
    h = _FONT * 1.45
    if rot == 0:
        if justify == "left":
            return (x, y - h, x + w, y + 0.2)
        return (x - w, y - h, x, y + 0.2)
    # 90°: readable bottom-to-top. Local +X is world −Y.
    if justify == "left":
        return (x - h, y - w, x + 0.2, y)
    return (x - h, y, x + 0.2, y + w)


def _boxes_overlap(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
    gap: float = 0.4,
) -> bool:
    return not (a[2] + gap <= b[0] or b[2] + gap <= a[0] or a[3] + gap <= b[1] or b[3] + gap <= a[1])


def parse_lib_bodies(text: str) -> dict[str, tuple[float, float, float, float] | None]:
    lo, hi = _lib_symbols_range(text)
    if lo < 0:
        return {}
    body = text[lo:hi]
    out: dict[str, tuple[float, float, float, float] | None] = {}
    pos = 0
    while True:
        j = body.find("\n\t\t(symbol ", pos)
        if j < 0:
            break
        open_at = body.find("(", j)
        end = matching_paren(body, open_at)
        block = body[open_at : end + 1]
        pos = end + 1
        m = re.match(r'\(symbol "([^"]+)"', block)
        if not m:
            continue
        r = _RECT.search(block)
        if not r:
            out[m.group(1)] = None
            continue
        x0, y0, x1, y1 = (float(r.group(i)) for i in range(1, 5))
        out[m.group(1)] = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
    return out


def parse_libs(text: str) -> dict[str, dict[str, tuple[float, float, float]]]:
    lo, hi = _lib_symbols_range(text)
    if lo < 0:
        return {}
    body = text[lo:hi]
    libs: dict[str, dict[str, tuple[float, float, float]]] = {}
    pos = 0
    while True:
        j = body.find("\n\t\t(symbol ", pos)
        if j < 0:
            break
        open_at = body.find("(", j)
        end = matching_paren(body, open_at)
        block = body[open_at : end + 1]
        pos = end + 1
        m = re.match(r'\(symbol "([^"]+)"', block)
        if not m:
            continue
        libs[m.group(1)] = parse_lib_pins(block)
    return libs


def _wire_points(text: str) -> set[tuple[float, float]]:
    pts: set[tuple[float, float]] = set()
    for start, end in _top_spans(text, "wire"):
        for xm, ym in _WIRE_XY.findall(text[start:end]):
            pts.add((round(float(xm), 2), round(float(ym), 2)))
    return pts


def _near_wire(pts: set[tuple[float, float]], x: float, y: float, tol: float = 0.3) -> bool:
    rx, ry = round(x, 2), round(y, 2)
    if (rx, ry) in pts:
        return True
    for px, py in pts:
        if abs(px - x) <= tol and abs(py - y) <= tol:
            return True
    return False


def _hide_lib_pin_names(text: str) -> str:
    """Stop on-box pin names (VIN, D0, …) from colliding with net labels."""
    lo, hi = _lib_symbols_range(text)
    if lo < 0:
        return text
    body = text[lo:hi]
    skip = {"GND", "VCC", "R_Small", "C_Small"}
    pos = 0
    chunks: list[str] = []
    last = 0
    while True:
        j = body.find("\n\t\t(symbol ", pos)
        if j < 0:
            break
        open_at = body.find("(", j)
        end = matching_paren(body, open_at)
        block = body[open_at : end + 1]
        pos = end + 1
        m = re.match(r'\(symbol "([^"]+)"', block)
        if not m or m.group(1) in skip:
            continue
        if "(pin_names" in block:
            new = re.sub(
                r"\(pin_names\b[^)]*\)",
                "(pin_names\n\t\t\t\t(offset 0.508)\n\t\t\t\t(hide yes)\n\t\t\t)",
                block,
                count=1,
            )
            if new == block:
                new = block.replace(
                    "(pin_names",
                    "(pin_names\n\t\t\t\t(hide yes)",
                    1,
                )
        else:
            insert = "\n\t\t\t(pin_names\n\t\t\t\t(offset 0.508)\n\t\t\t\t(hide yes)\n\t\t\t)"
            nl = block.find("\n", 8)
            new = block[:nl] + insert + block[nl:] if nl > 0 else block
        if new != block:
            chunks.append((open_at, end + 1, new))
    if not chunks:
        return text
    parts: list[str] = []
    cur = 0
    for a, b, new in chunks:
        abs_a, abs_b = lo + a, lo + b
        parts.append(text[cur:abs_a])
        parts.append(new)
        cur = abs_b
    parts.append(text[cur:])
    return "".join(parts)


def _instance_bodies(
    text: str, bodies: dict[str, tuple[float, float, float, float] | None]
) -> list[tuple[str, tuple[float, float, float, float]]]:
    lo, hi = _lib_symbols_range(text)
    out: list[tuple[str, tuple[float, float, float, float]]] = []
    for start, end in _top_spans(text, "symbol"):
        if lo <= start < hi:
            continue
        block = text[start:end]
        lib_m = _LIB_ID.search(block)
        ref_m = _REF.search(block)
        at_m = _INST_AT.search(block)
        if not lib_m or not ref_m or not at_m:
            continue
        lib_id = lib_m.group(1)
        ref = ref_m.group(1)
        if ref.startswith("#PWR") or lib_id in ("GND", "VCC"):
            continue
        box = bodies.get(lib_id)
        if not box:
            continue
        ix, iy = float(at_m.group(1)), float(at_m.group(2))
        irot = float(at_m.group(3) or 0)
        corners = [
            _rotate(box[0], box[1], irot),
            _rotate(box[2], box[1], irot),
            _rotate(box[2], box[3], irot),
            _rotate(box[0], box[3], irot),
        ]
        xs = [ix + c[0] for c in corners]
        ys = [iy + c[1] for c in corners]
        out.append((ref, (min(xs), min(ys), max(xs), max(ys))))
    return out


def _strip_local_labels(text: str) -> str:
    lo, hi = _lib_symbols_range(text)
    pieces: list[str] = []
    last = 0
    for start, end in _top_spans(text, "label"):
        if lo <= start < hi:
            continue
        prefix = start
        while prefix > last and text[prefix - 1] in " \t":
            prefix -= 1
        if prefix > last and text[prefix - 1] == "\n":
            prefix -= 1
        pieces.append(text[last:prefix])
        last = end
        if last < len(text) and text[last] == "\n":
            last += 1
    pieces.append(text[last:])
    return "".join(pieces)


def _stub_delta(world_rot: float, length: float) -> tuple[float, float]:
    rad = math.radians(world_rot)
    return (-length * math.cos(rad), -length * math.sin(rad))


def _text_width(name: str) -> float:
    return max(len(name), 1) * _FONT * _CHAR_W


def _underline_pose(dx: float, dy: float) -> tuple[int, str]:
    """Label at the far end of the stub; text runs back along the wire, upright.

    Never use 180°/270° — those flip the glyphs off the wire. Horizontal
    names stay at 0°; vertical names stay at 90°. Justify picks the side
    so the string sits on the stub toward the pin.
    """
    if abs(dx) >= abs(dy):
        return 0, "left" if dx < 0 else "right"
    return 90, "left" if dy > 0 else "right"


def _fmt(n: float) -> str:
    s = f"{n:.4f}".rstrip("0").rstrip(".")
    return s if s else "0"


def _wire_sexp(x0: float, y0: float, x1: float, y1: float) -> str:
    uid = new_uuid()
    return (
        f'\t(wire\n'
        f'\t\t(pts\n'
        f'\t\t\t(xy {_fmt(x0)} {_fmt(y0)}) (xy {_fmt(x1)} {_fmt(y1)})\n'
        f'\t\t)\n'
        f'\t\t(stroke\n'
        f'\t\t\t(width 0)\n'
        f'\t\t\t(type default)\n'
        f'\t\t)\n'
        f'\t\t(uuid "{uid}")\n'
        f'\t)\n'
    )


def _local_label_sexp(name: str, x: float, y: float, rot: int, justify: str) -> str:
    uid = new_uuid()
    return (
        f'\t(label "{name}"\n'
        f'\t\t(at {_fmt(x)} {_fmt(y)} {rot})\n'
        f'\t\t(effects\n'
        f'\t\t\t(font\n'
        f'\t\t\t\t(size {_FONT} {_FONT})\n'
        f'\t\t\t)\n'
        f'\t\t\t(justify {justify} bottom)\n'
        f'\t\t)\n'
        f'\t\t(uuid "{uid}")\n'
        f'\t)\n'
    )


def _power_symbol_sexp(net: str, x: float, y: float, *, gnd: bool) -> str:
    uid = new_uuid()
    lib = "GND" if gnd else "VCC"
    ref = f"#PWR{uid.replace('-', '')[:16]}"
    # GND hangs down from the pin; VCC sits above.
    val_y = y + 3.81 if gnd else y - 3.81
    return (
        f'\t(symbol\n'
        f'\t\t(lib_id "{lib}")\n'
        f'\t\t(at {_fmt(x)} {_fmt(y)} 0)\n'
        f'\t\t(unit 1)\n'
        f'\t\t(body_style 1)\n'
        f'\t\t(in_bom no)\n'
        f'\t\t(on_board no)\n'
        f'\t\t(dnp no)\n'
        f'\t\t(uuid "{uid}")\n'
        f'\t\t(property "Reference" "{ref}"\n'
        f'\t\t\t(at {_fmt(x)} {_fmt(y)} 0)\n'
        f'\t\t\t(hide yes)\n'
        f'\t\t\t(effects (font (size 1.27 1.27)))\n'
        f'\t\t)\n'
        f'\t\t(property "Value" "{net}"\n'
        f'\t\t\t(at {_fmt(x)} {_fmt(val_y)} 0)\n'
        f'\t\t\t(effects (font (size 1.27 1.27)))\n'
        f'\t\t)\n'
        f'\t\t(pin "1"\n'
        f'\t\t\t(uuid "{new_uuid()}")\n'
        f'\t\t)\n'
        f'\t)\n'
    )


def _pack_signal_jobs(
    jobs: list[dict],
    obstacles: list[tuple[str, tuple[float, float, float, float]]],
) -> None:
    """Straight stub as long as the name; label sits on the wire."""
    placed: list[tuple[float, float, float, float]] = []
    columns: dict[tuple, list[dict]] = defaultdict(list)
    for job in jobs:
        if job["power"]:
            continue
        columns[(job["ref"], int(round(job["wrot"] / 90)) % 4)].append(job)
    for group in columns.values():
        group.sort(key=lambda j: (round(j["wy"], 2), round(j["wx"], 2)))
        for job in group:
            tw = _text_width(job["net"])
            extra = 0.0
            placed_ok = False
            for _ in range(14):
                length = max(_STUB_MIN, tw) + extra
                dx, dy = _stub_delta(job["wrot"], length)
                sx, sy = job["wx"] + dx, job["wy"] + dy
                rot, just = _underline_pose(dx, dy)
                box = _label_box(job["net"], sx, sy, rot, just)
                hit = any(_boxes_overlap(box, other) for other in placed)
                hit = hit or any(
                    ref != job["ref"] and _boxes_overlap(box, body)
                    for ref, body in obstacles
                )
                if not hit:
                    job["lx"] = sx
                    job["ly"] = sy
                    job["lrot"] = rot
                    job["ljust"] = just
                    placed.append(box)
                    placed_ok = True
                    break
                extra += 2.54
            if not placed_ok:
                job["skip"] = True


def annotate_sch_nets(sch_text: str, netlist_text: str) -> str:
    """Return a schematic with pin stubs + net names. Power keeps global symbols."""
    _comps, nets = parse_netlist(netlist_text)
    lookup = pin_to_net(nets)
    degree = {n["name"]: len(n["nodes"]) for n in nets}
    if not lookup:
        return sch_text
    text = _hide_lib_pin_names(sch_text)
    libs = parse_libs(text)
    bodies = parse_lib_bodies(text)
    obstacles = _instance_bodies(text, bodies)
    lo, hi = _lib_symbols_range(text)
    text = _strip_local_labels(text)
    wires = _wire_points(text)
    jobs: list[dict] = []
    for start, end in _top_spans(text, "symbol"):
        if lo <= start < hi:
            continue
        block = text[start:end]
        lib_m = _LIB_ID.search(block)
        ref_m = _REF.search(block)
        at_m = _INST_AT.search(block)
        if not lib_m or not ref_m or not at_m:
            continue
        lib_id = lib_m.group(1)
        ref = ref_m.group(1)
        if ref.startswith("#PWR") or lib_id in ("GND", "VCC") or _is_passive(ref):
            continue
        pins = libs.get(lib_id) or {}
        if not pins:
            continue
        ix, iy = float(at_m.group(1)), float(at_m.group(2))
        irot = float(at_m.group(3) or 0)
        for pnum, (px, py, prot) in pins.items():
            net = lookup.get((ref, pnum))
            if not net:
                continue
            lx, ly = _rotate(px, py, irot)
            wx, wy = ix + lx, iy + ly
            wrot = (prot + irot) % 360
            power = is_power_net(net)
            if not power and degree.get(net, 0) < 2:
                continue
            jobs.append(
                {
                    "ref": ref,
                    "net": net,
                    "wx": wx,
                    "wy": wy,
                    "wrot": wrot,
                    "power": power,
                    "skip_power": power and _near_wire(wires, wx, wy),
                }
            )
    _pack_signal_jobs(jobs, obstacles)
    extras: list[str] = []
    for job in jobs:
        if job.get("skip_power"):
            continue
        if job.get("skip"):
            continue
        if job["power"]:
            dx, dy = _stub_delta(job["wrot"], _STUB_MIN)
            sx, sy = job["wx"] + dx, job["wy"] + dy
            extras.append(_wire_sexp(job["wx"], job["wy"], sx, sy))
            gnd = job["net"].upper() in ("GND", "VSS")
            extras.append(_power_symbol_sexp(job["net"], sx, sy, gnd=gnd))
            continue
        lx = job.get("lx")
        ly = job.get("ly")
        if lx is None:
            tw = _text_width(job["net"])
            dx, dy = _stub_delta(job["wrot"], max(_STUB_MIN, tw))
            lx, ly = job["wx"] + dx, job["wy"] + dy
            rot, just = _underline_pose(dx, dy)
        else:
            rot, just = job.get("lrot", 0), job.get("ljust", "left")
        extras.append(_wire_sexp(job["wx"], job["wy"], lx, ly))
        extras.append(_local_label_sexp(job["net"], lx, ly, rot, just))
    if not extras:
        return text
    if not text.endswith("\n"):
        text += "\n"
    close = text.rstrip()
    if not close.endswith(")"):
        return text + "".join(extras)
    return close[:-1] + "\n" + "".join(extras) + ")\n"


def annotate_sch_file(sch_path: Path, netlist_path: Path) -> bool:
    sch_path = Path(sch_path)
    netlist_path = Path(netlist_path)
    if not sch_path.exists() or not netlist_path.exists():
        return False
    new = annotate_sch_nets(sch_path.read_text(), netlist_path.read_text())
    if new == sch_path.read_text():
        return False
    sch_path.write_text(new)
    return True
