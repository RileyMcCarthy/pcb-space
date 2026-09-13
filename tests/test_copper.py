from pathlib import Path

from pcb_space.compile import compile_design
from pcb_space.copper import (
    airwire_span_mm,
    power_ampacity_failures,
    unrouted_nets,
)
from pcb_space.language import load_place_file

FIXTURES = Path(__file__).resolve().parent / "fixtures"
ROOT = Path(__file__).resolve().parents[1]


def _two_pad(net_id=1, net="USB_DP", x2=15.0) -> str:
    src = (FIXTURES / "tiny.kicad_pcb").read_text()
    if net != "USB_DP":
        src = src.replace('(net 1 "USB_DP")', f'(net {net_id} "{net}")')
    extra = f"""
	(footprint "X"
		(layer "F.Cu")
		(uuid "33333333-3333-3333-3333-333333333333")
		(at {x2:.4f} 5.0000 0)
		(property "Reference" "U9"
			(at 0 -2 0)
			(layer "F.SilkS")
		)
		(attr smd)
		(pad "1" smd rect
			(at 0 0)
			(size 0.8 0.8)
			(layers "F.Cu" "F.Paste" "F.Mask")
			(net {net_id} "{net}")
		)
	)
"""
    return src.rstrip()[:-1] + extra + ")\n"


def test_unrouted_two_pads():
    text = _two_pad()
    assert "USB_DP" in unrouted_nets(text)


def test_airwire_span():
    text = _two_pad()
    assert 9.5 < airwire_span_mm(text)["USB_DP"] < 10.5


def test_ampacity_fails_skinny_high_current(tmp_path: Path):
    text = _two_pad(net_id=3, net="GND", x2=15)
    text = text.rstrip()[:-1] + """
	(segment
		(start 5 5)
		(end 15 5)
		(width 0.16)
		(layer "F.Cu")
		(net 3)
	)
)
"""
    p = tmp_path / "p.place.py"
    p.write_text(
        "Board(size_mm=(20, 10), layers=2, stackup='jlcpcb_2l_1oz')\n"
        "NetReq('GND', kind='power', volts=0, amps=5)\n"
    )
    job = compile_design(load_place_file(p))
    fails = power_ampacity_failures(job, text)
    assert fails
    assert "GND" in fails[0]


def test_ampacity_ok_with_plane(tmp_path: Path):
    text = (FIXTURES / "tiny.kicad_pcb").read_text()
    p = tmp_path / "p.place.py"
    p.write_text(
        "Board(size_mm=(20, 10), layers=4, stackup='jlcpcb_4l_1oz',\n"
        "      planes=[('GND', 'In1.Cu')])\n"
        "NetReq('GND', kind='power', volts=0, amps=5)\n"
    )
    job = compile_design(load_place_file(p))
    assert power_ampacity_failures(job, text) == []


def test_switch_default_max_mm():
    job = compile_design(load_place_file(ROOT / "examples" / "forma_pod.place.py"))
    sw = next(n for n in job.nets if n.kind == "switch_node")
    assert sw.max_length_mm == 8.0
