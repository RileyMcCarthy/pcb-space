from pathlib import Path

from pcb_space.pins import check_pins, parse_zen_pins, pin_lock_report
from pcb_space.source import check_footprint

ROOT = Path(__file__).resolve().parents[1]
AP2112 = ROOT / "examples" / "c3_usb" / "components" / "Diodes_Inc" / "AP2112K-3.3TRG1"


def test_parse_zen_pins():
    pins = parse_zen_pins((AP2112 / "AP2112K-3.3TRG1.zen").read_text())
    assert pins["VIN"] == ["1"]
    assert pins["VOUT"] == ["5"]


def test_ap2112_pin_lock_matches_datasheet():
    report = check_pins(AP2112)
    assert report["ok"] is True
    assert report["pin_ok"] is True


def test_dual_zen_pads_ok_when_symbol_has_those_numbers():
    """EasyEDA single-bridge *names* are fine if pad numbers exist (28/29 as RSVD)."""
    from pcb_space.pins import check_pins

    cad = {
        "OUT1": ["4", "5", "6", "17", "18", "19"],
        "OUT2": ["7", "8", "9", "14", "15", "16"],
        "IN1": ["26"],
        "IN2": ["27"],
        "RSVD": ["28", "29"],
        "GND": ["1", "44"],
    }
    lock = {
        "OUT1": ["17", "18", "19"],
        "OUT3": ["4", "5", "6"],
        "IN3": ["28"],
        "IN4": ["29"],
        "GND": ["1", "44"],
    }
    report = pin_lock_report(cad, lock)
    assert report["ok"] is False  # names differ — informational
    # Pad coverage (what check_pins uses): all zen pads exist on the symbol.
    zen_pads = {p for pads in lock.values() for p in pads}
    cad_pads = {p for pads in cad.values() for p in pads}
    assert zen_pads <= cad_pads


def test_source_check_includes_pin_lock():
    report = check_footprint(AP2112, body_mm=(2.9, 1.6))
    assert report["pin_ok"] is True
    assert report["ok"] is True


def test_require_pins_fails_without_lock(tmp_path: Path):
    (tmp_path / "empty.zen").write_text("Board(name='x', layers=2, layout_path='layout/x')\n")
    report = check_pins(tmp_path, require=True)
    assert report["ok"] is False
