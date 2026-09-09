from pathlib import Path

from pcb_space.cli import main

ROOT = Path(__file__).resolve().parents[1]


def test_compile_cli_zero(capsys):
    rc = main(["compile", str(ROOT / "examples" / "blinky.place.py")])
    assert rc == 0
    out = capsys.readouterr().out
    assert '"name": "USB"' in out
    assert "USB_DP" in out
