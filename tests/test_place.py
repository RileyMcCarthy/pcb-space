import shutil
from pathlib import Path

from pcb_space.apply import apply_job
from pcb_space.compile import compile_design
from pcb_space.intent import intent_from_job, place_edge
from pcb_space.language import load_place_file
from pcb_space.model import PlaceSpec
from pcb_space.refs import build_alias_index, resolve_ref
from pcb_space.sexp import has_edge_cuts_shape

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_alias_j1_to_u3(tmp_path: Path):
    src = (FIXTURES / "tiny.kicad_pcb").read_text()
    src = src.replace('(property "Reference" "J1"', '(property "Reference" "U3"')
    src = src.replace(
        '(property "Value" "USB"',
        '(property "Path" "J1.TYPE_C"\n\t\t\t(at 0 0 0)\n\t\t\t(layer "F.SilkS")\n\t\t)\n\t\t(property "Value" "USB"',
    )
    pcb = tmp_path / "t.kicad_pcb"
    pcb.write_text(src)
    idx = build_alias_index(pcb.read_text())
    assert resolve_ref("U3", idx) == "U3"
    assert resolve_ref("J1", idx) == "U3"


def test_apply_resolves_alias_and_inserts_outline(tmp_path: Path):
    src = (FIXTURES / "tiny.kicad_pcb").read_text()
    src = src.replace('(property "Reference" "J1"', '(property "Reference" "U3"')
    src = src.replace(
        '(property "Value" "USB"',
        '(property "Path" "J1.TYPE_C"\n\t\t\t(at 0 0 0)\n\t\t\t(layer "F.SilkS")\n\t\t)\n\t\t(property "Value" "USB"',
    )
    # drop existing outline
    start = src.find("\t(gr_rect")
    end = src.find("\t(footprint")
    src = src[:start] + src[end:]
    assert not has_edge_cuts_shape(src)

    pcb = tmp_path / "tiny.kicad_pcb"
    pcb.write_text(src)
    shutil.copy(FIXTURES / "tiny.kicad_pro", tmp_path / "tiny.kicad_pro")
    job = compile_design(load_place_file(ROOT / "examples" / "blinky.place.py"))
    result = apply_job(job, pcb, backup=False)
    assert result["missing"] == []
    assert result["aliases"]["J1"] == "U3"
    text = pcb.read_text()
    assert has_edge_cuts_shape(text)
    assert "(locked yes)" in text


def test_place_edge_usb_is_east_not_north():
    p = PlaceSpec(ref="J1", right=0, top=0, bottom=0, locked=True)
    assert place_edge(p) == "east"


def test_c3_intent_locks_j1():
    job = compile_design(load_place_file(ROOT / "examples" / "c3_usb" / "c3_usb.place.py"))
    intent = intent_from_job(job, {"J1": "U3"})
    assert set(intent["must_lock"]) == {"U3", "U1"}
    edges = {e["ref"]: e["edge"] for e in intent["edge_connectors"]}
    assert edges == {"U3": "south"}
    assert intent["legality_budget"]["oob_count"] == 1.0
    assert intent["envelope"]["rect"] == [0.0, 0.0, 40.0, 30.0]
    assert any(k["name"] == "ANTENNA" for k in intent["keepouts"])


def test_has_edge_cuts_shape_sees_gr_rect():
    src = (FIXTURES / "tiny.kicad_pcb").read_text()
    assert has_edge_cuts_shape(src)
    start = src.find("\t(gr_rect")
    end = src.find("\t(footprint")
    stripped = src[:start] + src[end:]
    assert not has_edge_cuts_shape(stripped)


def test_place_job_without_engine_still_applies(tmp_path: Path):
    from pcb_space.place import place_job

    pcb = tmp_path / "tiny.kicad_pcb"
    shutil.copy(FIXTURES / "tiny.kicad_pcb", pcb)
    shutil.copy(FIXTURES / "tiny.kicad_pro", tmp_path / "tiny.kicad_pro")
    job = compile_design(load_place_file(ROOT / "examples" / "blinky.place.py"))
    out = tmp_path / "tiny_placed.kicad_pcb"
    result = place_job(job, pcb, krt_home=tmp_path / "no-krt", out=out, force=True)
    assert "not found" in (result.get("error") or "")
    assert Path(result["intent"]).exists()
    intent = __import__("json").loads(Path(result["intent"]).read_text())
    assert intent["must_lock"] == ["J1"]
    text = out.read_text()
    assert has_edge_cuts_shape(text)
    assert "(locked yes)" in text


def test_place_job_default_out_is_subdir(tmp_path: Path):
    from pcb_space.place import place_job

    pcb = tmp_path / "tiny.kicad_pcb"
    shutil.copy(FIXTURES / "tiny.kicad_pcb", pcb)
    shutil.copy(FIXTURES / "tiny.kicad_pro", tmp_path / "tiny.kicad_pro")
    job = compile_design(load_place_file(ROOT / "examples" / "blinky.place.py"))
    result = place_job(job, pcb, krt_home=tmp_path / "no-krt")
    assert Path(result["pcb"]) == tmp_path / "placed" / "tiny.kicad_pcb"
