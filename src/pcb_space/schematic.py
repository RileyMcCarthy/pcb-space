"""Read a Zener .zen enough to lint USB-C/MCU wiring and stub NetReq."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .sexp import matching_paren


_ASSIGN_NET = re.compile(
    r'(?m)^([A-Za-z_]\w*)\s*=\s*(Net|Power|Ground)\(\s*"([^"]+)"\s*\)'
)
_KWARG = re.compile(r"([A-Za-z_]\w*)\s*=\s*([A-Za-z_]\w*|\"[^\"]*\")")
_BOARD = re.compile(r"Board\s*\(")
_VALUE_51K = re.compile(r'value\s*=\s*"5\.1\s*k', re.I)


@dataclass
class ZenNet:
    ident: str
    kind: str  # net | power | ground
    name: str


def parse_zen_nets(text: str) -> list[ZenNet]:
    out: list[ZenNet] = []
    seen: set[str] = set()
    for m in _ASSIGN_NET.finditer(text):
        ident, kind, name = m.group(1), m.group(2).lower(), m.group(3)
        if name in seen:
            continue
        seen.add(name)
        out.append(ZenNet(ident=ident, kind=kind, name=name))
    return out


def _call_after(text: str, match: re.Match[str]) -> str:
    open_at = text.find("(", match.start())
    if open_at < 0:
        return ""
    end = matching_paren(text, open_at)
    return text[open_at : end + 1]


def _kwargs(block: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in _KWARG.finditer(block):
        val = m.group(2)
        if val.startswith('"'):
            val = val.strip('"')
        out[m.group(1)] = val
    return out


def _usb_c_calls(text: str) -> list[dict[str, str]]:
    calls: list[dict[str, str]] = []
    for m in re.finditer(r"\b(USBC|USB_C|TYPE_C)\s*\(", text):
        calls.append(_kwargs(_call_after(text, m)))
    # Instantiation via a bound module: USBC = Module("...TYPE-C...") then USBC(
    if "TYPE-C" in text or "USB_C" in text or "TYPE_C" in text:
        for m in re.finditer(r"^[A-Za-z_]\w*\s*\(", text, re.M):
            name = m.group(0)[:-1]
            if name in ("Board", "Resistor", "Capacitor", "Led", "Module"):
                continue
            block = _call_after(text, m)
            kw = _kwargs(block)
            if "DP1" in kw or "CC1" in kw:
                if kw not in calls:
                    calls.append(kw)
    return calls


def _esp32_calls(text: str) -> list[dict[str, str]]:
    if "ESP32" not in text:
        return []
    calls: list[dict[str, str]] = []
    for m in re.finditer(r"\bESP32[A-Za-z0-9_]*\s*\(", text):
        calls.append(_kwargs(_call_after(text, m)))
    return calls


def lint_zen(text: str) -> list[str]:
    """Electrical checks the schematic skill currently keeps as prose."""
    fails: list[str] = []
    nets = {n.ident: n for n in parse_zen_nets(text)}
    names = {n.name for n in parse_zen_nets(text)}

    if not _BOARD.search(text):
        fails.append("no Board() — Zener needs Board(..., layout_path=...)")
    elif "layout_path" not in text:
        fails.append("Board() missing layout_path (pcb layout writes layout/<name>/)")

    usb_calls = _usb_c_calls(text)
    if usb_calls:
        for kw in usb_calls:
            ref = kw.get("name", "USB-C")
            dp1, dp2 = kw.get("DP1"), kw.get("DP2")
            dn1, dn2 = kw.get("DN1"), kw.get("DN2")
            if not dp1 or not dp2:
                fails.append(f"{ref}: USB-C needs DP1 and DP2 (both orientations)")
            elif dp1 != dp2:
                fails.append(f"{ref}: DP1={dp1} and DP2={dp2} must be the same net")
            if not dn1 or not dn2:
                fails.append(f"{ref}: USB-C needs DN1 and DN2 (both orientations)")
            elif dn1 != dn2:
                fails.append(f"{ref}: DN1={dn1} and DN2={dn2} must be the same net")
            if "CC1" not in kw or "CC2" not in kw:
                fails.append(f"{ref}: USB-C UFP needs CC1 and CC2")
        if not _VALUE_51K.search(text):
            fails.append("USB-C UFP needs 5.1 kΩ Rd on CC1 and CC2 to GND")
        if "CC1" not in names and "CC1" not in nets:
            fails.append("missing Net(\"CC1\")")
        if "CC2" not in names and "CC2" not in nets:
            fails.append("missing Net(\"CC2\")")

    for kw in _esp32_calls(text):
        if "USB_DP" not in names and "USB_DP" not in nets:
            continue
        io19 = kw.get("IO19")
        io18 = kw.get("IO18")
        if io19 != "USB_DP":
            fails.append(
                f"ESP32 IO19 should be USB_DP (got {io19!r}); "
                "ESP32-C3-MINI-1 datasheet Table 3-1"
            )
        if io18 != "USB_DN":
            fails.append(
                f"ESP32 IO18 should be USB_DN (got {io18!r}); "
                "ESP32-C3-MINI-1 datasheet Table 3-1"
            )

    return fails


def netreqs_from_zen(text: str) -> list[tuple[tuple[str, ...], str, dict]]:
    """Suggested NetReq groups: (nets, kind, kwargs)."""
    nets = parse_zen_nets(text)
    used: set[str] = set()
    out: list[tuple[tuple[str, ...], str, dict]] = []
    by_name = {n.name: n for n in nets}
    dp = by_name.get("USB_DP")
    dn = by_name.get("USB_DN")
    if dp and dn:
        out.append(((dp.name, dn.name), "usb_hs", {"z_diff_ohm": 90, "pair": True}))
        used.update((dp.name, dn.name))
    power = tuple(n.name for n in nets if n.kind in ("power", "ground") and n.name not in used)
    if power:
        out.append((power, "power", {"volts": 3.3, "amps": 0.5}))
        used.update(power)
    rest = tuple(n.name for n in nets if n.name not in used)
    if rest:
        out.append((rest, "digital", {}))
    return out


def stub_netreqs(text: str) -> str:
    lines: list[str] = []
    for nets, kind, kw in netreqs_from_zen(text):
        args = ", ".join(repr(n) for n in nets)
        bits = []
        for k, v in kw.items():
            bits.append(f"{k}={v}" if isinstance(v, bool) else f"{k}={v!r}")
        extra = (", " + ", ".join(bits)) if bits else ""
        lines.append(f"NetReq({args}, kind={kind!r}{extra})")
    return "\n".join(lines) + ("\n" if lines else "")
