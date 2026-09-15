"""Pin lock: .zen definition vs .kicad_sym pad numbers.

EasyEDA graphics are fine. Names follow the board's .zen (e.g. dual vs
single H-bridge). We only require every zen pad number to exist on the symbol.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .eda import group_pins, parse_symbol, pin_ident

_ZEN_DEF = re.compile(
    r'\(\s*"([A-Za-z0-9_]+)"\s*,\s*\[([^\]]*)\]',
)


def parse_zen_pins(text: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for name, raw in _ZEN_DEF.findall(text):
        nums = [n.strip().strip('"').strip("'") for n in raw.split(",") if n.strip()]
        if nums:
            out.setdefault(name, []).extend(nums)
    return out


def normalize_pins(pins: dict) -> dict[str, frozenset[str]]:
    grouped: dict[str, set[str]] = {}
    for name, nums in pins.items():
        key = pin_ident(str(name))
        grouped.setdefault(key, set()).update(str(n) for n in nums)
    return {k: frozenset(v) for k, v in grouped.items()}


def pin_lock_report(cad: dict, lock: dict) -> dict:
    cad_n = normalize_pins(cad)
    lock_n = normalize_pins(lock)
    mismatches: list[str] = []
    for name, pads in sorted(lock_n.items()):
        if name not in cad_n:
            mismatches.append(f"{name}: missing in CAD (lock {sorted(pads)})")
        elif cad_n[name] != pads:
            mismatches.append(
                f"{name}: CAD pads {sorted(cad_n[name])} vs datasheet {sorted(pads)}"
            )
    skip_extra = {"NC", "DNC", "EP", "PAD"}
    for name, pads in sorted(cad_n.items()):
        if name in lock_n or name in skip_extra:
            continue
        mismatches.append(f"{name}: extra in CAD {sorted(pads)}")
    return {
        "ok": not mismatches,
        "mismatches": mismatches,
        "cad": {k: sorted(v) for k, v in cad_n.items()},
        "lock": {k: sorted(v) for k, v in lock_n.items()},
    }


def load_pin_lock(path: Path) -> dict[str, list[str]] | None:
    """Zen definition is the lock. A JSON path is only for `source import --pins`."""
    path = Path(path)
    if path.is_file() and path.suffix.lower() == ".json":
        data = json.loads(path.read_text())
        if isinstance(data, dict) and data.get("pins") and isinstance(data["pins"], dict):
            data = data["pins"]
        return {str(k): list(v) if not isinstance(v, str) else [v] for k, v in data.items()}
    if path.is_file() and path.suffix == ".zen":
        zp = parse_zen_pins(path.read_text())
        return zp or None
    if path.is_dir():
        zens = list(path.glob("*.zen"))
        if zens:
            zp = parse_zen_pins(zens[0].read_text())
            if zp:
                return zp
    return None


def load_cad_pins(path: Path) -> dict[str, list[str]]:
    """CAD = .kicad_sym pad numbers, not the .zen names."""
    path = Path(path)
    if path.is_dir():
        source = path / "SOURCE.json"
        if source.exists():
            rec = json.loads(source.read_text())
            if rec.get("symbol"):
                sym = path / rec["symbol"]
                if sym.exists():
                    return group_pins(parse_symbol(sym)["pins"])
        syms = [p for p in path.glob("*.kicad_sym") if p.name != "pcbspace.kicad_sym"]
        if syms:
            return group_pins(parse_symbol(syms[0])["pins"])
        return {}
    if path.suffix == ".zen":
        return parse_zen_pins(path.read_text())
    if path.suffix == ".kicad_sym":
        return group_pins(parse_symbol(path)["pins"])
    if path.suffix == ".json":
        rec = json.loads(path.read_text())
        return {str(k): list(v) for k, v in (rec.get("pins") or rec).items()} if isinstance(rec, dict) else {}
    return {}


def check_pins(
    path: Path,
    *,
    pins: Path | dict | None = None,
    require: bool = False,
) -> dict:
    path = Path(path)
    lock = pins if isinstance(pins, dict) else None
    if lock is None and pins is not None:
        lock = load_pin_lock(Path(pins))
    if lock is None:
        lock = load_pin_lock(path)
    cad = load_cad_pins(path)
    if lock is None:
        return {
            "ok": not require,
            "pin_ok": None,
            "note": "no .zen pin definition" + (" (required)" if require else ""),
            "cad": cad,
        }
    zen_pads = {str(p) for pads in lock.values() for p in pads}
    cad_pads = {str(p) for pads in cad.values() for p in pads}
    missing = sorted(zen_pads - cad_pads)
    report = {
        "ok": not missing,
        "pin_ok": not missing,
        "mismatches": [f"zen pad {p} missing on .kicad_sym" for p in missing],
        "cad": cad,
        "lock": lock,
        "note": None if not missing else "; ".join(f"zen pad {p} missing on .kicad_sym" for p in missing[:6]),
    }
    return report
