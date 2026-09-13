"""Datasheet pin-lock: PINS.json vs CAD/zen pad map.

EasyEDA can attach a land that matches the body and still swap OUT1/OUT3.
A PINS.json next to SOURCE.json is the datasheet table; CAD must match it.
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
    path = Path(path)
    if path.is_file() and path.suffix.lower() == ".json":
        data = json.loads(path.read_text())
        if isinstance(data, dict) and data.get("pins") and isinstance(data["pins"], dict):
            data = data["pins"]
        return {str(k): list(v) if not isinstance(v, str) else [v] for k, v in data.items()}
    if path.is_dir():
        pins_json = path / "PINS.json"
        if pins_json.exists():
            return load_pin_lock(pins_json)
        source = path / "SOURCE.json"
        if source.exists():
            rec = json.loads(source.read_text())
            lock = rec.get("pins_lock")
            if isinstance(lock, dict) and lock:
                return {str(k): list(v) if not isinstance(v, str) else [v] for k, v in lock.items()}
    return None


def load_cad_pins(path: Path) -> dict[str, list[str]]:
    path = Path(path)
    if path.is_dir():
        zens = list(path.glob("*.zen"))
        if zens:
            zen_pins = parse_zen_pins(zens[0].read_text())
            if zen_pins:
                return zen_pins
        source = path / "SOURCE.json"
        if source.exists():
            rec = json.loads(source.read_text())
            if rec.get("symbol"):
                sym = path / rec["symbol"]
                if sym.exists():
                    return group_pins(parse_symbol(sym)["pins"])
            if rec.get("pins"):
                return {str(k): list(v) for k, v in rec["pins"].items()}
        syms = list(path.glob("*.kicad_sym"))
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
            "note": "no PINS.json / pins_lock" + (" (required)" if require else ""),
            "cad": cad,
        }
    report = pin_lock_report(cad, lock)
    report["pin_ok"] = report["ok"]
    if report["mismatches"]:
        report["note"] = "; ".join(report["mismatches"][:6])
    else:
        report["note"] = None
    return report
