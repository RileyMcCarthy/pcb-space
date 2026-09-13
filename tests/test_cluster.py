from pathlib import Path

from pcb_space.cluster import cluster_sensitive
from pcb_space.compile import compile_design
from pcb_space.copper import airwire_span_mm
from pcb_space.language import load_place_file

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _board() -> str:
    src = (FIXTURES / "tiny.kicad_pcb").read_text()
    extra = """
	(footprint "Inductor"
		(layer "F.Cu")
		(uuid "33333333-3333-3333-3333-333333333333")
		(at 25.0000 5.0000 0)
		(property "Reference" "L1"
			(at 0 -2 0)
			(layer "F.SilkS")
		)
		(attr smd)
		(fp_rect (start -2 -1) (end 2 1) (stroke (width 0.05) (type default)) (fill none) (layer "F.CrtYd"))
		(pad "1" smd rect
			(at 0 0)
			(size 0.8 0.8)
			(layers "F.Cu" "F.Paste" "F.Mask")
			(net 1 "USB_DP")
		)
	)
"""
    return src.rstrip()[:-1] + extra + ")\n"


def test_cluster_pulls_unlocked_inductor_to_switch_node(tmp_path: Path):
    text = _board()
    before = airwire_span_mm(text)["USB_DP"]
    assert before > 15
    place = tmp_path / "sw.place.py"
    place.write_text(
        "Board(width=40, height=20, layers=2, stackup='jlcpcb_2l_1oz')\n"
        "Place('J1', at=(5, 5), locked=True, reason='buck IC')\n"
        "NetReq('USB_DP', kind='switch_node', max_mm=8)\n"
    )
    job = compile_design(load_place_file(place))
    new, moves = cluster_sensitive(job, text)
    assert moves
    assert moves[0]["ref"] == "L1"
    after = airwire_span_mm(new)["USB_DP"]
    assert after < before
    assert after <= 8.1
