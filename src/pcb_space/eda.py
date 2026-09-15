"""EasyEDA / LCSC CAD fetch and KiCad symbol pin parse."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

from .sexp import matching_paren

_PIN_NAME = re.compile(r'\(name\s+"([^"]+)"')
_PIN_NUM = re.compile(r'\(number\s+"([^"]+)"')
_PIN_AT = re.compile(r"\(at\s+([0-9.+-]+)\s+([0-9.+-]+)(?:\s+([0-9.+-]+))?\)")
_PIN_LEN = re.compile(r"\(length\s+([0-9.+-]+)\)")
_PIN_TYPE = re.compile(r"\(pin\s+(\S+)")
_PROP = re.compile(r'\(property\s+"([^"]+)"\s+"([^"]*)"')
_SYM_NAME = re.compile(r'\(symbol\s+"([^"]+)"')


def find_easyeda2kicad() -> str | None:
    found = shutil.which("easyeda2kicad")
    if found:
        return found
    sibling = Path(sys.executable).parent / "easyeda2kicad"
    if sibling.exists():
        return str(sibling)
    return None


def fetch_easyeda(lcsc_id: str, dest: Path) -> dict:
    """Download symbol + footprint for an LCSC id into dest.

    Requires the `easyeda2kicad` CLI (`pip install easyeda2kicad`).
    """
    exe = find_easyeda2kicad()
    if not exe:
        raise RuntimeError(
            "easyeda2kicad is not installed. "
            "pip install easyeda2kicad  (optional extra: pcb-space[source])"
        )
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    prefix = dest / "easyeda"
    cmd = [
        exe,
        "--symbol",
        "--footprint",
        "--lcsc_id",
        lcsc_id if str(lcsc_id).upper().startswith("C") else f"C{lcsc_id}",
        "--output",
        str(prefix),
        "--overwrite",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"easyeda2kicad failed ({proc.returncode}): {proc.stderr or proc.stdout}"
        )
    sym = prefix.with_suffix(".kicad_sym")
    pretty = Path(str(prefix) + ".pretty")
    mods = list(pretty.glob("*.kicad_mod")) if pretty.is_dir() else []
    if not sym.exists() or not mods:
        raise RuntimeError(f"easyeda2kicad produced no CAD in {dest}: {proc.stdout}")
    return {
        "symbol": sym,
        "footprint": mods[0],
        "log": proc.stdout,
        "cad_origin": "easyeda",
    }


def parse_symbol(path: Path) -> dict:
    text = Path(path).read_text()
    names = _SYM_NAME.findall(text)
    symbol_name = names[0] if names else Path(path).stem
    props = dict(_PROP.findall(text))
    pins: list[tuple[str, str]] = []
    start = 0
    while True:
        j = text.find("(pin ", start)
        if j < 0:
            break
        end = matching_paren(text, j)
        block = text[j : end + 1]
        nm = _PIN_NAME.search(block)
        num = _PIN_NUM.search(block)
        if nm and num:
            pins.append((nm.group(1), num.group(1)))
        start = end + 1
    return {
        "name": symbol_name,
        "properties": props,
        "pins": pins,
        "manufacturer": props.get("Manufacturer") or props.get("manufacturer") or "",
        "datasheet": props.get("Datasheet") or "",
        "mpn": props.get("Value") or symbol_name,
    }


def extract_main_symbol(text: str) -> tuple[str, str]:
    """First top-level (symbol "Name" …) in a .kicad_sym and its name."""
    j = text.find("(symbol ")
    if j < 0:
        raise ValueError("no symbol in library")
    end = matching_paren(text, j)
    block = text[j : end + 1]
    nm = _SYM_NAME.search(block)
    return (nm.group(1) if nm else "SYM"), block


def parse_symbol_pins_geom(path: Path) -> list[dict]:
    text = Path(path).read_text()
    pins: list[dict] = []
    start = 0
    while True:
        j = text.find("(pin ", start)
        if j < 0:
            break
        end = matching_paren(text, j)
        block = text[j : end + 1]
        start = end + 1
        num = _PIN_NUM.search(block)
        at = _PIN_AT.search(block)
        if not num or not at:
            continue
        nm = _PIN_NAME.search(block)
        ln = _PIN_LEN.search(block)
        tp = _PIN_TYPE.search(block)
        pins.append(
            {
                "name": nm.group(1) if nm else num.group(1),
                "number": num.group(1),
                "x": float(at.group(1)),
                "y": float(at.group(2)),
                "rot": float(at.group(3) or 0),
                "length": float(ln.group(1) if ln else 2.54),
                "type": tp.group(1) if tp else "unspecified",
            }
        )
    return pins


def apply_zen_names_to_symbol(sym_sexp: str, pad_to_name: dict[str, str]) -> str:
    """Keep EasyEDA graphics and pad numbers; names come from the .zen definition."""
    out: list[str] = []
    last = 0
    start = 0
    s = sym_sexp
    while True:
        j = s.find("(pin ", start)
        if j < 0:
            out.append(s[last:])
            break
        end = matching_paren(s, j)
        block = s[j : end + 1]
        num = _PIN_NUM.search(block)
        if num and num.group(1) in pad_to_name:
            block = re.sub(
                r'\(name\s+"[^"]*"',
                f'(name "{pad_to_name[num.group(1)]}"',
                block,
                count=1,
            )
        out.append(s[last:j])
        out.append(block)
        last = end + 1
        start = end + 1
    return "".join(out)


def group_pins(pins: list[tuple[str, str]]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for name, number in pins:
        key = pin_ident(name)
        grouped.setdefault(key, []).append(number)
    return grouped


def pin_ident(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_]", "_", name).strip("_")
    if not s:
        return "PIN"
    if s[0].isdigit():
        s = "P" + s
    return s


def pin_kind(name: str) -> str:
    u = pin_ident(name).upper()
    if u in {"GND", "VSS", "AGND", "DGND", "PGND", "EP", "EH", "SHIELD"}:
        return "Ground"
    if u in {"VCC", "VDD", "VBUS", "VIN", "VOUT", "3V3", "P3V3", "V3V3", "VBAT", "5V", "P5V"}:
        return "Power"
    return "Net"
