from pathlib import Path

from pcb_space.compile import compile_design
from pcb_space.language import load_place_file

ROOT = Path(__file__).resolve().parents[1]


def test_blinky_usb_compiles_to_a_pair():
    job = compile_design(load_place_file(ROOT / "examples" / "blinky.place.py"))
    usb = next(n for n in job.nets if n.class_name == "USB")
    assert usb.autoroute == "diff_pair"
    assert usb.patterns == ("USB_DP", "USB_DN")
    cls = next(c for c in job.classes if c.name == "USB")
    assert cls.diff_pair_gap_mm is not None
    assert cls.diff_pair_width_mm is not None
    assert cls.track_width_mm > 0.05
    # 2-layer loosely-coupled 90 Ω is ~2 mm — unusable at USB-C pitch.
    assert cls.diff_pair_width_mm <= 0.25
    assert cls.clearance_mm <= 0.20


def test_c3_usb_pair_fits_connector_pitch():
    job = compile_design(load_place_file(ROOT / "examples" / "c3_usb" / "c3_usb.place.py"))
    cls = next(c for c in job.classes if c.name == "USB")
    assert cls.diff_pair_width_mm == 0.10
    assert cls.diff_pair_gap_mm == 0.10
    assert cls.clearance_mm == 0.10


def test_analog_is_not_autorouted():
    job = compile_design(load_place_file(ROOT / "examples" / "forma_pod.place.py"))
    analog = [n for n in job.nets if n.kind == "analog"]
    assert analog
    assert all(n.autoroute is False for n in analog)
    assert "CH[1-9]*" in job.skip_autoroute_patterns
    assert "BOOST.BOOST_SW" in job.skip_autoroute_patterns


def test_locked_connectors_are_in_the_job():
    job = compile_design(load_place_file(ROOT / "examples" / "forma_pod.place.py"))
    locked = {p.ref: p for p in job.places if p.locked}
    assert locked["U26"].at == (47.2, 10.0)
    assert locked["U26"].rot == 90
    assert locked["U26"].left == 47.2
    assert locked["U28"].reason.startswith("FFC")


def test_power_width_grows_with_current(tmp_path: Path):
    def job_for(amps: float):
        p = tmp_path / f"p{amps}.place.py"
        p.write_text(
            "Board(size_mm=(10, 10))\n"
            f'NetReq("3V3", kind="power", amps={amps})\n'
        )
        return compile_design(load_place_file(p))

    light = next(c.track_width_mm for c in job_for(0.05).classes if c.name == "Power")
    heavy = next(c.track_width_mm for c in job_for(2.0).classes if c.name == "Power")
    assert heavy > light
