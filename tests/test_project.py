"""init / status / seed / refs / lint — Zener contract."""

from __future__ import annotations

import json
from pathlib import Path

from pcb_space.cli import main
from pcb_space.initproj import init_job
from pcb_space.project import packed_reason, resolve_project
from pcb_space.refs import refs_report
from pcb_space.schematic import lint_zen, stub_netreqs
from pcb_space.seed import seed_job
from pcb_space.status import status_job
from pcb_space.compile import compile_design
from pcb_space.language import load_place_file


ROOT = Path(__file__).resolve().parents[1]
C3 = ROOT / "examples" / "c3_usb"
PLACE = C3 / "c3_usb.place.py"
ZEN = C3 / "c3_usb.zen"
SEED = C3 / "layout" / "c3_usb" / "layout.kicad_pcb"
PLACED = C3 / "layout" / "c3_usb" / "placed" / "layout.kicad_pcb"
ROUTED = C3 / "layout" / "c3_usb" / "routed" / "layout.kicad_pcb"


def test_packed_reason_seed_ok_placed_blocked():
    assert packed_reason(SEED) is None
    assert packed_reason(PLACED) is not None
    assert "placed/" in packed_reason(PLACED)
    assert packed_reason(ROUTED) is not None
    assert "copper" in packed_reason(ROUTED) or "routed/" in packed_reason(ROUTED)


def test_resolve_c3_usb():
    proj = resolve_project(C3)
    assert proj.name == "c3_usb"
    assert proj.zen == ZEN
    assert proj.place == PLACE
    assert proj.seed == SEED
    assert proj.stage() == "fab"


def test_status_c3_usb():
    data = status_job(C3)
    assert data["stage"] == "fab"
    assert data["lint"] == []
    assert data["refs_missing"] == []
    assert "J1" not in data["nets_uncovered"]
    assert "USB_DP" not in data["nets_uncovered"]


def test_lint_c3_usb_ok():
    assert lint_zen(ZEN.read_text()) == []


def test_lint_usbc_needs_both_orientations():
    bad = """
USB_DP = Net("USB_DP")
USB_DN = Net("USB_DN")
CC1 = Net("CC1")
USBC(
    name = "J1",
    DP1 = USB_DP,
    DN1 = USB_DN,
    CC1 = CC1,
)
Board(name = "x", layers = 2, layout_path = "layout/x")
"""
    fails = lint_zen(bad)
    assert any("DP2" in f or "both orientations" in f for f in fails)
    assert any("CC2" in f or "5.1" in f for f in fails)


def test_lint_esp32_usb_pins():
    bad = """
USB_DP = Net("USB_DP")
USB_DN = Net("USB_DN")
ESP32(
    name = "U1",
    IO18 = USB_DP,
    IO19 = USB_DN,
)
Board(name = "x", layers = 2, layout_path = "layout/x")
"""
    fails = lint_zen(bad)
    assert any("IO19" in f for f in fails)
    assert any("IO18" in f for f in fails)


def test_stub_netreqs_from_c3_zen():
    text = stub_netreqs(ZEN.read_text())
    assert "USB_DP" in text and "usb_hs" in text
    assert "VBUS" in text and "power" in text
    assert "CC1" in text


def test_refs_zener_path_to_kicad():
    job = compile_design(load_place_file(PLACE))
    report = refs_report(job.places, SEED.read_text())
    assert report["missing"] == []
    assert report["zener_to_kicad"]["R_CC1"] == "R2" or "R_CC1" in report["zener_to_kicad"]
    assert any(r["place"] == "J1" and r["kicad"] == "J1" for r in report["places"])


def test_seed_refuses_copper_seed(tmp_path: Path):
    init_job(tmp_path, name="t")
    seed = tmp_path / "layout" / "t" / "layout.kicad_pcb"
    seed.parent.mkdir(parents=True)
    seed.write_text(ROUTED.read_text())
    result = seed_job(tmp_path)
    assert result.get("error")
    assert "copper" in result["error"] or "routed" in result["error"]


def test_init_and_cli_status(tmp_path: Path, capsys):
    rc = main(["init", "blink", "-C", str(tmp_path)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert (tmp_path / "blink.zen").exists()
    assert (tmp_path / "blink.place.py").exists()
    assert (tmp_path / "pcb.toml").exists()
    assert "pcb layout" in (tmp_path / "BOARD.md").read_text()
    rc = main(["status", str(tmp_path)])
    assert rc == 0
    st = json.loads(capsys.readouterr().out)
    assert st["stage"] == "schematic"
    assert st["name"] == "blink"


def test_cli_lint_c3(capsys):
    rc = main(["lint", str(ZEN)])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["ok"] is True


def test_cli_refs_c3(capsys):
    rc = main(["refs", str(PLACE), "--pcb", str(SEED)])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["missing"] == []


def test_place_cli_refuses_routed(tmp_path: Path, capsys):
    rc = main(
        [
            "place",
            str(PLACE),
            "--pcb",
            str(ROUTED),
            "--krt-home",
            str(tmp_path / "no-krt"),
        ]
    )
    assert rc == 2
    data = capsys.readouterr().out
    assert "routed/" in data or "copper" in data
