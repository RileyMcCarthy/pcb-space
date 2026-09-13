"""Make a Zener-applied .kicad_sch show net names on pin stubs.

`pcb apply schematic` drops a 1.27 mm local label on the pin (invisible at
A1-page zoom) and only draws wires for Power()/Ground() symbols. This
rewriter:

- signal nets (2+ pins): short stub + local ``label`` (not a global arrow)
- adjacent pins on the same side get staggered stub lengths so names
  do not stack
- unused one-pin nets are left unlabeled
- power nets (GND, +12V, …): keep existing GND/VCC symbols; if a power pin
  has no wire, add a stub and a power symbol whose Value is the net
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
_STUB_SHORT = 3.81
_STUB_LONG = 10.16
_FONT = 1.27


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


def _label_rot(dx: float, dy: float) -> tuple[int, str]:
    if abs(dx) >= abs(dy):
        if dx >= 0:
            return 0, "left"
        return 180, "right"
    if dy >= 0:
        return 90, "left"
    return 270, "right"


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


def annotate_sch_nets(sch_text: str, netlist_text: str) -> str:
    """Return a schematic with pin stubs + net names. Power keeps global symbols."""
    _comps, nets = parse_netlist(netlist_text)
    lookup = pin_to_net(nets)
    degree = {n["name"]: len(n["nodes"]) for n in nets}
    if not lookup:
        return sch_text
    libs = parse_libs(sch_text)
    lo, hi = _lib_symbols_range(sch_text)
    text = _strip_local_labels(sch_text)
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
        if ref.startswith("#PWR") or lib_id in ("GND", "VCC"):
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
    columns: dict[tuple, list[dict]] = defaultdict(list)
    for job in jobs:
        if job["power"]:
            continue
        columns[(job["ref"], int(round(job["wrot"] / 90)) % 4)].append(job)
    for group in columns.values():
        group.sort(key=lambda j: (round(j["wy"], 2), round(j["wx"], 2)))
        for i, job in enumerate(group):
            job["length"] = _STUB_SHORT if i % 2 == 0 else _STUB_LONG
    extras: list[str] = []
    for job in jobs:
        if job.get("skip_power"):
            continue
        length = job.get("length", _STUB_SHORT)
        dx, dy = _stub_delta(job["wrot"], length)
        sx, sy = job["wx"] + dx, job["wy"] + dy
        extras.append(_wire_sexp(job["wx"], job["wy"], sx, sy))
        if job["power"]:
            gnd = job["net"].upper() in ("GND", "VSS")
            extras.append(_power_symbol_sexp(job["net"], sx, sy, gnd=gnd))
            continue
        rot, just = _label_rot(dx, dy)
        extras.append(_local_label_sexp(job["net"], sx, sy, rot, just))
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
