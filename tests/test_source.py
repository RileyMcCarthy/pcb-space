import json
from pathlib import Path

import pytest

from pcb_space.cli import main, source_main
from pcb_space.eda import group_pins, parse_symbol, pin_ident
from pcb_space.source import check_footprint, import_part, parse_body_mm, search_parts

FIXTURES = Path(__file__).resolve().parent / "fixtures"
UDFN = FIXTURES / "udfn_1x1.kicad_mod"


class _FakeResp:
    def __init__(self, payload: dict):
        self._raw = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._raw


def _opener(payload):
    def open_fn(req, timeout=20):
        return _FakeResp(payload)

    return open_fn


def test_parse_body_from_jlc_package():
    assert parse_body_mm("DFN-4-EP(1.5x1.5)") == (1.5, 1.5)
    assert parse_body_mm("1.5x1.5") == (1.5, 1.5)


def test_search_lcsc_mocked():
    payload = {
        "components": [
            {
                "lcsc": 919459,
                "mfr": "TPS61023DRLR",
                "package": "SOT-563",
                "is_basic": False,
                "is_preferred": False,
                "description": "boost",
                "stock": 100,
                "price": 0.26,
            }
        ]
    }
    data = search_parts("TPS61023DRLR", opener=_opener(payload))
    assert data["hits"][0]["mpn"] == "TPS61023DRLR"
    assert data["hits"][0]["lcsc"] == "C919459"
    assert any(s["vendor"] == "digikey" for s in data["skipped"])


def test_sht40_body_gate_fails():
    report = check_footprint(UDFN, body_mm=(1.5, 1.5), tol_mm=0.2)
    assert report["ok"] is False
    assert report["fab_mm"] == [1.0, 1.0]
    assert report["pads"] == 5
    assert "wrong land" in (report["note"] or "")


def test_matching_body_passes():
    report = check_footprint(UDFN, body_mm=(1.0, 1.0), tol_mm=0.2)
    assert report["ok"] is True


def test_import_generic_writes_package(tmp_path: Path):
    payload = {
        "components": [
            {
                "lcsc": 1525,
                "mfr": "CL05B104KO5NNNC",
                "package": "0402",
                "is_basic": True,
                "description": "100nF 16V X7R 0402",
                "stock": 10,
                "price": 0.006,
            }
        ]
    }
    result = import_part(
        "100nF 0402",
        tmp_path,
        kind="generic",
        manufacturer="Samsung",
        opener=_opener(payload),
    )
    pkg = Path(result["package"])
    assert (pkg / "SOURCE.json").exists()
    rec = json.loads((pkg / "SOURCE.json").read_text())
    assert rec["kind"] == "generic"
    assert rec["status"] == "ok"
    assert rec["lcsc"] == "C1525"
    assert "Part(mpn" in (pkg / "part.zen").read_text()


def test_select_hit_requires_pick_when_ambiguous():
    hits = [
        {"mpn": "DRV8262DDVR", "lcsc": "C33828788"},
        {"mpn": "DRV8262DDWR", "lcsc": "C22427252"},
    ]
    from pcb_space.source import select_hit

    assert select_hit("DRV8262", hits) is None
    assert select_hit("DRV8262", hits, pick="C33828788")["mpn"] == "DRV8262DDVR"
    assert select_hit("C33828788", hits)["mpn"] == "DRV8262DDVR"


def test_import_ic_lists_hits_does_not_fetch_easyeda(tmp_path: Path):
    payload = {
        "components": [
            {"lcsc": 1, "mfr": "DRV8262DDVR", "package": "HTSSOP-44", "stock": 4, "price": 1},
            {"lcsc": 2, "mfr": "DRV8262DDWR", "package": "HTSSOP-44", "stock": 9, "price": 1},
        ]
    }
    result = import_part("DRV8262", tmp_path, kind="ic", opener=_opener(payload))
    assert result["package"] is None
    assert result["record"]["status"] == "pick"
    assert not list(tmp_path.rglob("*.kicad_mod"))


def test_import_ic_needs_pins_even_with_land(tmp_path: Path):
    payload = {
        "components": [
            {
                "lcsc": 51118,
                "mfr": "AP2112K-3.3TRG1",
                "package": "SOT-25-5",
                "stock": 1,
                "price": 0.2,
            }
        ]
    }
    result = import_part(
        "C51118",
        tmp_path,
        kind="ic",
        footprint=UDFN,
        body="1.0x1.0",
        opener=_opener(payload),
    )
    assert result["record"]["status"] == "needs_pin_lock"
    assert result["record"]["gates"]["ok"] is False


def test_import_ic_ok_with_footprint_and_pins(tmp_path: Path):
    payload = {
        "components": [
            {
                "lcsc": 51118,
                "mfr": "AP2112K-3.3TRG1",
                "package": "SOT-25-5",
                "stock": 1,
                "price": 0.2,
            }
        ]
    }
    pins = tmp_path / "PINS.json"
    pins.write_text(json.dumps({"P1": ["1"], "P2": ["2"], "P3": ["3"], "P4": ["4"], "P5": ["5"]}))
    result = import_part(
        "C51118",
        tmp_path / "out",
        kind="ic",
        footprint=UDFN,
        body="1.0x1.0",
        pins=pins,
        opener=_opener(payload),
    )
    assert result["record"]["status"] == "ok"
    assert not (Path(result["package"]) / "PINS.json").exists()
    zens = list(Path(result["package"]).glob("*.zen"))
    assert zens
    assert "definition" in zens[0].read_text()


def test_import_ic_with_wrong_land_fails_gate(tmp_path: Path):
    payload = {
        "components": [
            {
                "lcsc": 2909890,
                "mfr": "SHT40-AD1B-R2",
                "package": "DFN-4-EP(1.5x1.5)",
                "is_basic": False,
                "description": "humidity",
                "stock": 1,
                "price": 2.0,
            }
        ]
    }
    result = import_part(
        "SHT40-AD1B",
        tmp_path,
        kind="ic",
        footprint=UDFN,
        body="1.5x1.5",
        manufacturer="Sensirion",
        opener=_opener(payload),
    )
    assert result["record"]["status"] == "gate_failed"
    assert result["record"]["gates"]["ok"] is False


def test_source_cli_check(capsys):
    rc = main(["source", "check", str(UDFN), "--body", "1.5x1.5"])
    assert rc == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False


def test_parse_symbol_pins(tmp_path: Path):
    p = tmp_path / "x.kicad_sym"
    p.write_text(
        '(kicad_symbol_lib (symbol "U"\n'
        '  (pin unspecified line (name "VIN") (number "1"))\n'
        '  (pin unspecified line (name "GND") (number "2"))\n'
        '  (pin unspecified line (name "GND") (number "3"))\n'
        "))\n"
    )
    parsed = parse_symbol(p)
    assert parsed["pins"] == [("VIN", "1"), ("GND", "2"), ("GND", "3")]
    g = group_pins(parsed["pins"])
    assert g["VIN"] == ["1"]
    assert g["GND"] == ["2", "3"]
    assert pin_ident("3V3") == "P3V3"


def test_pcb_source_alias_help():
    with pytest.raises(SystemExit) as e:
        source_main(["search", "-h"])
    assert e.value.code == 0


def test_forma_pod_sht40_land_fails_if_present():
    p = Path(
        "/Users/rileymccarthy/Downloads/forma-pod-github/forma-pod-zener/footprints/"
        "UDFN-4-1EP_1x1mm_P0.65mm_EP0.48x0.48mm.kicad_mod"
    )
    if not p.exists():
        pytest.skip("Forma Pod tree not on this machine")
    report = check_footprint(p, body_mm=(1.5, 1.5), tol_mm=0.2)
    assert report["ok"] is False
    assert report["fab_mm"][0] == pytest.approx(1.0, abs=0.05)
