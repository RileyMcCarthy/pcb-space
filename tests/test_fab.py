import csv
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
    via_in_pad_blockers,
    write_bom_csv,
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


def test_write_bom_csv_quotes_grouped_designators(tmp_path: Path):
    path = tmp_path / "bom.csv"
    write_bom_csv(
        [
            {
                "Comment": "100n",
                "Designator": "C13,C14,C2,C3",
                "Footprint": "C_0603_1608Metric",
                "LCSC Part #": "C14663",
            }
        ],
        path,
    )
    rows = list(csv.DictReader(path.open()))
    assert rows[0]["Designator"] == "C13,C14,C2,C3"
    assert rows[0]["LCSC Part #"] == "C14663"
    assert rows[0]["Footprint"] == "C_0603_1608Metric"


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


def test_jlc_bom_skips_through_hole_without_lcsc():
    src = (FIXTURES / "tiny.kicad_pcb").read_text()
    src = src.replace("(attr smd)", "(attr through_hole)")
    src = src.replace('(pad "1" smd rect', '(pad "1" thru_hole circle')
    rows, missing = jlc_bom(src, {})
    assert rows == []
    assert missing == []


def test_via_in_pad_blockers_flag_passives_not_usb():
    hits = [
        {"via": (1, 1), "pad": "C7.2"},
        {"via": (2, 2), "pad": "J1.A6"},
        {"via": (3, 3), "pad": "J5.MP"},
        {"via": (4, 4), "pad": "U1.3"},
        {"via": (5, 5), "pad": "R19.1"},
        {"via": (6, 6), "pad": "L9.2"},
    ]
    blocked = {h["pad"] for h in via_in_pad_blockers(hits)}
    assert blocked == {"C7.2", "J5.MP", "R19.1", "L9.2"}


def test_via_in_pad_skips_through_hole_pads():
    src = (FIXTURES / "tiny.kicad_pcb").read_text()
    src = src.replace('(pad "1" smd rect', '(pad "1" thru_hole circle')
    stripped = src.rstrip()
    via = '\t(via\n\t\t(at 5.0 5.0)\n\t\t(size 0.25)\n\t\t(drill 0.15)\n\t\t(layers "F.Cu" "B.Cu")\n\t\t(net "USB_DP")\n\t)\n'
    text = stripped[:-1] + via + ")\n"
    assert via_in_pad(text) == []


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


def test_insert_fiducials_skips_occupied_corner():
    src = (FIXTURES / "tiny.kicad_pcb").read_text()
    # Move the fixture USB off the NW corner so that corner is a valid fiducial.
    src = src.replace("(at 5.0000 5.0000 0)", "(at 20.0000 15.0000 0)")
    # 40×30 board: SW fiducial is (4, 26). Park a courtyard there so
    # insert_fiducials must take NW (4, 4) instead.
    extra = """
	(footprint "Block"
		(layer "F.Cu")
		(uuid "55555555-5555-5555-5555-555555555555")
		(at 4.0000 26.0000 0)
		(property "Reference" "J9"
			(at 0 -2 0)
			(layer "F.SilkS")
		)
		(attr smd)
		(fp_rect (start -3 -3) (end 3 3) (stroke (width 0.05) (type default)) (fill none) (layer "F.CrtYd"))
		(pad "1" smd rect
			(at 0 0)
			(size 0.8 0.8)
			(layers "F.Cu" "F.Paste" "F.Mask")
		)
	)
"""
    text = src.rstrip()[:-1] + extra + ")\n"
    _new, spots = insert_fiducials(text, (40.0, 30.0))
    xy = {(round(x, 1), round(y, 1)) for _n, x, y in spots}
    assert (4.0, 26.0) not in xy
    assert (4.0, 4.0) in xy
    assert len(spots) == 3


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
            {
                "type": "length_out_of_range",
                "severity": "error",
                "description": "Track length out of range (rule 'analog_max_length' max length 25 mm; actual 40 mm)",
            },
        ]
    }
    err = copper_drc_errors(drc, floor_mm=0.10)
    assert len(err) == 2
    assert err[0]["items"][0]["description"].startswith("Track")
    assert "0.0500" in err[1]["description"]
    four = {
        "violations": [
            {
                "type": "clearance",
                "severity": "error",
                "description": "Clearance violation (netclass 'Default' clearance 0.1600 mm; actual 0.1490 mm)",
            }
        ]
    }
    assert copper_drc_errors(four, floor_mm=0.127) == []
    assert len(copper_drc_errors(four, floor_mm=0.16)) == 1


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
