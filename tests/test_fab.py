import json
from pathlib import Path

from pcb_space.compile import compile_design
from pcb_space.apply import write_dru
from pcb_space.fab import (
    bom_refs,
    copper_drc_errors,
    copper_gerber_layers,
    cpl_refs,
    insert_fiducials,
    jlc_bom,
    jlc_cpl_from_board,
    kicad_pos_to_jlc_cpl,
    lcsc_index,
    via_in_pad,
)
from pcb_space.language import load_place_file


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_copper_layers_2l():
    assert "F.Cu" in copper_gerber_layers(2)
    assert "In1.Cu" not in copper_gerber_layers(2)
    assert "Edge.Cuts" in copper_gerber_layers(2)


def test_jlc_bom_uses_source_lcsc(tmp_path: Path):
    pkg = tmp_path / "components" / "X" / "Y"
    pkg.mkdir(parents=True)
    (pkg / "SOURCE.json").write_text(
        json.dumps({"mpn": "USB", "lcsc": "C165948"})
    )
    src = (FIXTURES / "tiny.kicad_pcb").read_text()
    src = src.replace('(property "Value" "USB"', '(property "Mpn" "USB"\n\t\t\t(at 0 0)\n\t\t\t(layer "F.Fab")\n\t\t)\n\t\t(property "Value" "USB"')
    idx = lcsc_index(tmp_path / "components")
    rows, missing = jlc_bom(src, idx)
    assert missing == []
    assert rows[0]["LCSC Part #"] == "C165948"
    assert "J1" in rows[0]["Designator"]


def test_pos_to_cpl_columns():
    raw = 'Ref,Val,Package,PosX,PosY,Rot,Side\n"J1","USB","USB-C",20.0,-25.85,0,top\n'
    cpl = kicad_pos_to_jlc_cpl(raw)
    assert cpl.startswith("Designator,Mid X,Mid Y,Rotation,Layer")
    assert "J1,20.0,-25.85,0,Top" in cpl.replace(" ", "") or "J1,20.0,-25.85,0,Top" in cpl


def test_jlc_cpl_from_board_negates_y():
    src = (FIXTURES / "tiny.kicad_pcb").read_text()
    cpl = jlc_cpl_from_board(src)
    assert cpl.startswith("Designator,Mid X,Mid Y,Rotation,Layer")
    assert "J1,5.000000,-5.000000,0.000000,Top" in cpl
    assert "FID" not in cpl


def test_jlc_cpl_skips_exclude_from_pos():
    src = (FIXTURES / "tiny.kicad_pcb").read_text()
    src = src.replace("(attr smd)", "(attr smd exclude_from_pos_files)")
    assert cpl_refs(jlc_cpl_from_board(src)) == set()


def test_insert_fiducials(tmp_path: Path):
    text = (FIXTURES / "tiny.kicad_pcb").read_text()
    job = compile_design(load_place_file(ROOT / "examples" / "blinky.place.py"))
    new, spots = insert_fiducials(text, job.board_size_mm)
    assert len(spots) == 3
    assert "FID1" in new
    assert "(attr smd exclude_from_bom exclude_from_pos_files)" in new
    again, spots2 = insert_fiducials(new, job.board_size_mm)
    assert spots2[0][0].startswith("FID")
    assert again.count('(property "Reference" "FID1"') == 1


def test_via_in_pad_detects_centered_via():
    src = (FIXTURES / "tiny.kicad_pcb").read_text()
    # pad at local 0,0; footprint at 5,5. Insert a via on that pad.
    stripped = src.rstrip()
    via = '\t(via\n\t\t(at 5.0 5.0)\n\t\t(size 0.25)\n\t\t(drill 0.15)\n\t\t(layers "F.Cu" "B.Cu")\n\t\t(net "USB_DP")\n\t)\n'
    text = stripped[:-1] + via + ")\n"
    hits = via_in_pad(text)
    assert hits
    assert hits[0]["pad"].startswith("J1")


def test_via_in_pad_ignores_grazing_via():
    src = (FIXTURES / "tiny.kicad_pcb").read_text()
    stripped = src.rstrip()
    # Pad 0.8×0.8 at (5,5). Via centre is inside; copper 0.25 sticks out.
    via = '\t(via\n\t\t(at 5.35 5.0)\n\t\t(size 0.25)\n\t\t(drill 0.15)\n\t\t(layers "F.Cu" "B.Cu")\n\t\t(net "USB_DP")\n\t)\n'
    text = stripped[:-1] + via + ")\n"
    assert via_in_pad(text) == []


def test_via_in_pad_ignores_via_beside_rotated_pad():
    src = (FIXTURES / "tiny.kicad_pcb").read_text()
    src = src.replace("(at 5.0000 5.0000 0)", "(at 5.0000 5.0000 90)")
    stripped = src.rstrip()
    # Pad is 0.8×0.8 at local 0,0. After 90° the land is still 0.8 square.
    # A via 1.2 mm away in world X is outside the pad; world AABB of an
    # unrotated 0.8×2-style mis-parse must not count it.
    via = '\t(via\n\t\t(at 6.5 5.0)\n\t\t(size 0.25)\n\t\t(drill 0.15)\n\t\t(layers "F.Cu" "B.Cu")\n\t\t(net "USB_DP")\n\t)\n'
    text = stripped[:-1] + via + ")\n"
    assert via_in_pad(text) == []


def test_copper_drc_filters_footprint_shorts_and_silk():
    drc = {
        "violations": [
            {
                "type": "shorting_items",
                "severity": "error",
                "items": [
                    {"description": "Pad 2 [GND] of U1 on F.Cu"},
                    {"description": "Pad 3 [3V3] of U1 on F.Cu"},
                ],
            },
            {
                "type": "silk_over_copper",
                "severity": "error",
                "items": [],
            },
            {
                "type": "diff_pair_gap_out_of_range",
                "severity": "error",
                "items": [],
            },
            {
                "type": "shorting_items",
                "severity": "error",
                "items": [
                    {"description": "Track [USB_DP] on F.Cu, length 1 mm"},
                    {"description": "Pad 1 [GND] of J1 on F.Cu"},
                ],
            },
            {
                "type": "clearance",
                "severity": "error",
                "description": "Clearance violation (netclass 'Default' clearance 0.1600 mm; actual 0.1500 mm)",
            },
            {
                "type": "clearance",
                "severity": "error",
                "description": "Clearance violation (netclass 'Default' clearance 0.1600 mm; actual 0.0500 mm)",
            },
        ]
    }
    err = copper_drc_errors(drc, floor_mm=0.10)
    assert len(err) == 2
    assert err[0]["items"][0]["description"].startswith("Track")
    assert "0.0500" in err[1]["description"]


def test_write_dru_usb_floor(tmp_path: Path):
    pcb = tmp_path / "layout.kicad_pcb"
    pcb.write_text("(kicad_pcb (version 20241229))\n")
    job = compile_design(load_place_file(ROOT / "examples" / "c3_usb" / "c3_usb.place.py"))
    write_dru(job, pcb)
    dru = (tmp_path / "layout.kicad_dru").read_text()
    assert "min 0.10mm" in dru
    assert "0.13mm" not in dru


def test_bom_subset_of_cpl():
    rows = [{"Designator": "C1,C2"}, {"Designator": "J1"}]
    cpl = "Designator,Mid X,Mid Y,Rotation,Layer\nC1,0,0,0,Top\nC2,1,0,0,Top\nJ1,2,0,0,Top\n"
    assert bom_refs(rows) <= cpl_refs(cpl)
