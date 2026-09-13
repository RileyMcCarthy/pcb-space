"""c3_usb is the worked PCBA: compile → check placed/routed → silk → JLC package."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from pcb_space.check import check_job
from pcb_space.cli import main
from pcb_space.compile import compile_design
from pcb_space.fab import bom_refs, cpl_refs, fab_job, jlc_bom, kicad_cli, lcsc_index
from pcb_space.language import load_place_file
from pcb_space.route import krt_commands
from pcb_space.silk import legalize_silk, silk_job


ROOT = Path(__file__).resolve().parents[1]
C3 = ROOT / "examples" / "c3_usb"
PLACE = C3 / "c3_usb.place.py"
SEED = C3 / "layout" / "c3_usb" / "layout.kicad_pcb"
PLACED = C3 / "layout" / "c3_usb" / "placed" / "layout.kicad_pcb"
ROUTED = C3 / "layout" / "c3_usb" / "routed" / "layout.kicad_pcb"
BOM = C3 / "layout" / "c3_usb" / "fab" / "bom.csv"
CPL = C3 / "layout" / "c3_usb" / "fab" / "cpl.csv"


def _job():
    return compile_design(load_place_file(PLACE))


def test_c3_usb_files_are_in_the_tree():
    assert PLACE.exists()
    assert (C3 / "c3_usb.zen").exists()
    assert SEED.exists()
    assert PLACED.exists()
    assert ROUTED.exists()
    assert BOM.exists()
    assert CPL.exists()


def test_c3_usb_compiles_to_2l_usb_floor():
    job = _job()
    assert job.board_size_mm == (40.0, 30.0)
    assert job.layers == 2
    assert job.stackup == "jlcpcb_2l_1oz"
    cls = next(c for c in job.classes if c.name == "USB")
    assert cls.diff_pair_width_mm == 0.10
    assert cls.diff_pair_gap_mm == 0.10
    assert cls.clearance_mm == 0.10
    locked = {p.ref: p for p in job.places if p.locked}
    assert locked["J1"].rot == 0
    assert locked["U1"].rot == 90
    assert locked["J1"].reason.lower().startswith("usb-c")


def test_c3_usb_cli_compile(capsys):
    rc = main(["compile", str(PLACE)])
    assert rc == 0
    out = capsys.readouterr().out
    assert '"name": "USB"' in out
    assert "USB_DP" in out


def test_c3_usb_check_placed():
    assert check_job(_job(), PLACED) == []


def test_c3_usb_check_routed():
    assert check_job(_job(), ROUTED) == []


def test_c3_usb_cli_check_routed(capsys):
    rc = main(["check", str(PLACE), "--pcb", str(ROUTED)])
    assert rc == 0
    assert capsys.readouterr().out.strip() == "ok"


def test_c3_usb_route_plan_is_two_layer():
    job = _job()
    cmds = krt_commands(job, PLACED, work=Path("/tmp/c3-usb-route-test"))
    joined = "\n".join(" ".join(c) for c in cmds)
    assert "qfn_fanout.py" in joined
    assert "underpad" in joined
    assert "route_diff.py" in joined
    assert "--impedance" not in joined
    assert "route_planes.py" in joined


def test_c3_usb_bom_every_row_has_lcsc():
    sources = lcsc_index(C3 / "components")
    rows, missing = jlc_bom(ROUTED.read_text(), sources)
    assert missing == []
    assert rows
    assert all(r["LCSC Part #"].startswith("C") for r in rows)
    assert any("C165948" in r["LCSC Part #"] for r in rows)
    assert any("C2838502" in r["LCSC Part #"] for r in rows)


def test_c3_usb_committed_bom_matches_cpl():
    refs: set[str] = set()
    for line in BOM.read_text().splitlines()[1:]:
        if not line.strip():
            continue
        fields = line.split(",")
        lcsc, footprint, comment = fields[-1], fields[-2], fields[0]
        designators = fields[1:-2]
        refs.update(d.strip() for d in designators if d.strip())
        assert lcsc.startswith("C")
        assert comment and footprint
    assert refs <= cpl_refs(CPL.read_text())
    assert "J1" in refs and "U1" in refs
    assert len(refs) == 19


def test_c3_usb_silk_shrinks_0402_refs():
    job = _job()
    new, report = legalize_silk(ROUTED.read_text(), job.board_size_mm)
    sizes = {m["ref"]: m["size"] for m in report["moved"] if isinstance(m.get("size"), float)}
    assert sizes.get("C2") == 0.5
    assert sizes.get("J1") == 0.8
    assert sizes.get("U1") == 0.8
    ref = new.split('(property "Reference" "C2"', 1)[1].split('(property "Value"', 1)[0]
    assert "(size 0.5 0.5)" in ref


def test_c3_usb_silk_job_copy(tmp_path: Path):
    job = _job()
    dest = tmp_path / "layout.kicad_pcb"
    result = silk_job(job, ROUTED, out=dest, backup=False)
    assert Path(result["pcb"]).exists()
    assert result["silk"]["moved"]
    ref = dest.read_text().split('(property "Reference" "C2"', 1)[1].split('(property "Value"', 1)[0]
    assert "(size 0.5 0.5)" in ref


@pytest.mark.kicad
def test_c3_usb_fab_package(tmp_path: Path):
    cli = kicad_cli()
    if not cli.exists() and not shutil.which(str(cli)):
        pytest.skip("kicad-cli not installed")
    job = _job()
    out = tmp_path / "fab"
    result = fab_job(job, ROUTED, out_dir=out, components=C3 / "components")
    assert result.get("error") is None, result.get("error")
    assert result.get("missing_lcsc") == []
    assert result.get("drc_copper_errors") == 0
    assert (out / "bom.csv").exists()
    assert (out / "cpl.csv").exists()
    assert (out / "FAB_NOTES.md").exists()
    gerbers = list((out / "gerbers").glob("*"))
    assert gerbers, "kicad-cli wrote no gerbers"
    assert (out / "layout-PTH.drl").exists() or list(out.glob("*.drl"))
    rows, missing = jlc_bom((out / "layout.kicad_pcb").read_text(), lcsc_index(C3 / "components"))
    assert missing == []
    assert bom_refs(rows) <= cpl_refs((out / "cpl.csv").read_text())
