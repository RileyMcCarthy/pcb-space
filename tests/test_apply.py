import json
import shutil
from pathlib import Path

from pcb_space.apply import apply_job
from pcb_space.check import check_job
from pcb_space.compile import compile_design
from pcb_space.language import load_place_file
from pcb_space.sexp import board_footprint_spans, footprint_at, footprint_reference

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_apply_moves_and_locks_j1(tmp_path: Path):
    pcb = tmp_path / "tiny.kicad_pcb"
    shutil.copy(FIXTURES / "tiny.kicad_pcb", pcb)
    shutil.copy(FIXTURES / "tiny.kicad_pro", tmp_path / "tiny.kicad_pro")

    job = compile_design(load_place_file(ROOT / "examples" / "blinky.place.py"))
    result = apply_job(job, pcb, backup=True)
    assert result["missing"] == []
    assert "J1" in result["placed"]

    text = pcb.read_text()
    block = None
    for start, end in board_footprint_spans(text):
        b = text[start:end]
        if footprint_reference(b) == "J1":
            block = b
            break
    assert block is not None
    at = footprint_at(block)
    assert at is not None
    assert abs(at[0] - 19.0) < 0.01
    assert abs(at[1] - 5.0) < 0.01
    assert abs(at[2] - 90) < 0.01
    assert "(locked yes)" in block or "locked)" in block
    assert '(name "EDGE")' in text

    pro = json.loads((tmp_path / "tiny.kicad_pro").read_text())
    names = [c["name"] for c in pro["net_settings"]["classes"]]
    assert "USB" in names
    assert "Power" in names

    assert check_job(job, pcb) == []


def test_check_fails_if_connector_moves(tmp_path: Path):
    pcb = tmp_path / "tiny.kicad_pcb"
    shutil.copy(FIXTURES / "tiny.kicad_pcb", pcb)
    shutil.copy(FIXTURES / "tiny.kicad_pro", tmp_path / "tiny.kicad_pro")
    job = compile_design(load_place_file(ROOT / "examples" / "blinky.place.py"))
    apply_job(job, pcb, backup=False)
    text = pcb.read_text().replace("(at 19.0000 5.0000 90)", "(at 1.0000 1.0000 0)")
    pcb.write_text(text)
    failures = check_job(job, pcb)
    assert any("J1 moved" in f for f in failures)
