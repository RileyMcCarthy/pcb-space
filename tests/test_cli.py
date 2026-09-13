from pathlib import Path

from pcb_space.cli import main

ROOT = Path(__file__).resolve().parents[1]


def test_compile_cli_zero(capsys):
    rc = main(["compile", str(ROOT / "examples" / "blinky.place.py")])
    assert rc == 0
    out = capsys.readouterr().out
    assert '"name": "USB"' in out
    assert "USB_DP" in out


def test_place_cli_without_krt(tmp_path: Path, capsys):
    import shutil

    fixtures = Path(__file__).resolve().parent / "fixtures"
    pcb = tmp_path / "tiny.kicad_pcb"
    shutil.copy(fixtures / "tiny.kicad_pcb", pcb)
    shutil.copy(fixtures / "tiny.kicad_pro", tmp_path / "tiny.kicad_pro")
    out = tmp_path / "placed.kicad_pcb"
    rc = main(
        [
            "place",
            str(ROOT / "examples" / "blinky.place.py"),
            "--pcb",
            str(pcb),
            "--krt-home",
            str(tmp_path / "no-krt"),
            "-o",
            str(out),
        ]
    )
    assert rc == 2
    data = capsys.readouterr().out
    assert "place_seed.py not found" in data
    assert out.exists()
