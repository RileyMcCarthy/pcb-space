"""pcb-space build: staged compiler, incremental by default."""

from __future__ import annotations

import json
from pathlib import Path

from pcb_space.build import build_job, planned_stages
from pcb_space.cli import main
from pcb_space.initproj import init_job


ROOT = Path(__file__).resolve().parents[1]
C3 = ROOT / "examples" / "c3_usb"


def test_plan_incremental_from_each_stage():
    assert planned_stages("empty", upto="fab") == [
        "schematic",
        "seed",
        "place",
        "route",
        "fab",
    ]
    assert planned_stages("schematic", upto="seed") == ["schematic", "seed"]
    assert planned_stages("seeded", upto="place") == ["place"]
    assert planned_stages("placed", upto="fab") == ["route", "fab"]
    assert planned_stages("routed", upto="fab") == ["fab"]
    assert planned_stages("fab", upto="fab") == []


def test_plan_force_and_from():
    assert planned_stages("fab", upto="fab", force=True) == [
        "schematic",
        "seed",
        "place",
        "route",
        "fab",
    ]
    assert planned_stages("fab", upto="seed", force=True) == ["schematic", "seed"]
    assert planned_stages("fab", upto="fab", start_from="place") == [
        "place",
        "route",
        "fab",
    ]
    assert planned_stages("fab", upto="schematic", start_from="schematic") == [
        "schematic"
    ]


def test_dry_run_c3_already_fab():
    result = build_job(C3, dry_run=True)
    assert result["error"] is None
    assert result["plan"] == []
    assert result["stage_before"] == "fab"
    assert "new PCBA" not in (result.get("message") or "")  # dry-run skips the message


def test_dry_run_c3_force_upto_seed():
    result = build_job(C3, dry_run=True, force=True, upto="seed")
    assert result["plan"] == ["schematic", "seed"]
    assert result["toolchain"]["pcb_space"]


def test_cli_build_dry_run(capsys):
    rc = main(["build", str(C3), "--dry-run"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["plan"] == []
    assert data["dry_run"] is True


def test_cli_build_from_fab_dry_run(capsys):
    rc = main(["build", str(C3), "--from", "fab", "--dry-run"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["plan"] == ["fab"]


def test_build_init_project_plan(tmp_path: Path):
    init_job(tmp_path, name="blink")
    result = build_job(tmp_path, dry_run=True, upto="fab")
    assert result["plan"] == ["schematic", "seed", "place", "route", "fab"]
    assert result["stage_before"] == "schematic"


def test_build_noop_writes_no_lock(tmp_path: Path):
    result = build_job(C3)
    assert result["plan"] == []
    assert result["error"] is None
    assert "new PCBA" in result["message"]
    assert result.get("lock") is None
