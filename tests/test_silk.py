from pathlib import Path

from pcb_space.compile import compile_design
from pcb_space.language import load_place_file
from pcb_space.silk import legalize_silk, ref_font_mm, silk_job


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_ref_font_scales_with_courtyard():
    assert ref_font_mm(1.0) == 0.5
    assert ref_font_mm(3.0) == 0.6
    assert ref_font_mm(14.0) == 0.8


def test_legalize_shrinks_default_1mm_ref(tmp_path: Path):
    src = (FIXTURES / "tiny.kicad_pcb").read_text()
    job = compile_design(load_place_file(ROOT / "examples" / "blinky.place.py"))
    new, report = legalize_silk(src, job.board_size_mm)
    assert report["moved"]
    ref = new.split('(property "Reference"', 1)[1].split('(property "Value"', 1)[0]
    assert "(size 1 1)" not in ref
    assert "(size 0.6 0.6)" in ref or "(size 0.5 0.5)" in ref


def test_silk_job_writes_copy(tmp_path: Path):
    import shutil

    pcb = tmp_path / "tiny.kicad_pcb"
    shutil.copy(FIXTURES / "tiny.kicad_pcb", pcb)
    shutil.copy(FIXTURES / "tiny.kicad_pro", tmp_path / "tiny.kicad_pro")
    job = compile_design(load_place_file(ROOT / "examples" / "blinky.place.py"))
    out = tmp_path / "silk.kicad_pcb"
    result = silk_job(job, pcb, out=out, backup=False)
    assert Path(result["pcb"]).exists()
    assert pcb.read_text() != out.read_text()
