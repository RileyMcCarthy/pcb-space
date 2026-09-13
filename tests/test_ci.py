"""CI must run every test; merge requires pytest + c3-usb-fab."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "test.yml"


def test_ci_workflow_exists():
    assert WORKFLOW.exists()
    text = WORKFLOW.read_text()
    assert "\n  pytest:\n" in text
    assert "\n  c3-usb-fab:\n" in text
    assert "\n  krt-4layer:\n" in text


def test_unit_job_skips_kicad_marker():
    text = WORKFLOW.read_text()
    assert 'pytest -q -m "not kicad"' in text


def test_kicad_job_runs_the_full_suite():
    text = WORKFLOW.read_text()
    assert "All tests (kicad-cli required, no skips)" in text
    assert "PCBSPACE_REQUIRE_KICAD: \"1\"" in text or "PCBSPACE_REQUIRE_KICAD: '1'" in text
    # Must not limit the kicad job to one file.
    assert "pytest -q tests/test_c3_usb.py" not in text
    # Full suite: a pytest -q line without -m not kicad after the All tests step.
    assert "pytest -q --tb=short" in text


def test_kicad_job_installs_kicad_10():
    text = WORKFLOW.read_text()
    assert "ppa:kicad/kicad-10.0-releases" in text
    assert "need KiCad 10.x" in text


def test_krt_job_pins_router_and_routes_4layer():
    text = WORKFLOW.read_text()
    assert "3244726b2c15668fb109a0bb24384750a054af40" in text
    assert "github.com/drandyhaas/KiCadRoutingTools" in text
    assert "examples/buck_sw/buck_sw.place.py" in text
    assert "pcb-space place" in text
    assert "pcb-space route" in text
