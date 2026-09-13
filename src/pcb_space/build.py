"""One command: schematic → seed → place → route → fab.

Default is incremental: already-committed copper is left alone. ``--force``
or ``--from`` is an opt-in rebuild (a new PCBA).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from . import __version__
from .check import check_job
from .compile import compile_design
from .fab import fab_job, kicad_cli
from .language import load_place_file
from .place import place_job
from .project import Project, pcb_cli, resolve_project, zener_build
from .refs import refs_report
from .route import route_job
from .schematic import lint_zen
from .seed import seed_job


STAGES = ("schematic", "seed", "place", "route", "fab")

# Project.stage() name → last finished build stage (or None).
_DONE = {
    "empty": None,
    "place": None,
    "schematic": None,
    "seeded": "seed",
    "placed": "place",
    "routed": "route",
    "fab": "fab",
}


def planned_stages(
    current: str,
    *,
    upto: str = "fab",
    force: bool = False,
    start_from: str | None = None,
) -> list[str]:
    if upto not in STAGES:
        raise ValueError(f"upto must be one of {STAGES}, got {upto!r}")
    end = STAGES.index(upto)
    if start_from:
        if start_from not in STAGES:
            raise ValueError(f"--from must be one of {STAGES}, got {start_from!r}")
        start = STAGES.index(start_from)
    elif force:
        start = 0
    else:
        done = _DONE.get(current)
        start = 0 if done is None else STAGES.index(done) + 1
    if start > end:
        return []
    return list(STAGES[start : end + 1])


def toolchain() -> dict:
    pcb_ver = _cmd_version(pcb_cli(), ["--version"])
    kicad_ver = _cmd_version(kicad_cli(), ["version"])
    krt = os.environ.get("KRT_HOME", str(Path.home() / "Downloads" / "KiCadRoutingTools"))
    return {
        "pcb_space": __version__,
        "pcb": pcb_ver,
        "kicad_cli": kicad_ver,
        "krt_home": krt,
    }


def _cmd_version(exe: Path, args: list[str]) -> str | None:
    if not Path(exe).exists() and shutil.which(str(exe)) is None:
        return None
    proc = subprocess.run([str(exe), *args], capture_output=True, text=True)
    text = (proc.stdout or proc.stderr or "").strip()
    if proc.returncode != 0 or not text:
        return None
    return text.splitlines()[0].strip()


def _lock_path(proj: Project) -> Path:
    if proj.seed:
        return proj.seed.parent / "pcbspace.lock.json"
    return proj.root / "layout" / proj.name / "pcbspace.lock.json"


def _write_lock(proj: Project, result: dict) -> Path:
    path = _lock_path(proj)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "name": proj.name,
        "toolchain": result.get("toolchain"),
        "plan": result.get("plan"),
        "stage": result.get("stage_after"),
    }
    path.write_text(json.dumps(doc, indent=2) + "\n")
    return path


def _need_place(proj: Project) -> tuple:
    if not proj.place or not proj.place.exists():
        raise ValueError("no .place.py — write Place()/NetReq() before place/route/fab")
    job = compile_design(load_place_file(proj.place))
    return job, proj.place


def _run_schematic(proj: Project) -> dict:
    if not proj.zen or not proj.zen.exists():
        return {"stage": "schematic", "error": "no .zen — schematic is Zener"}
    fails = lint_zen(proj.zen.read_text())
    step: dict = {"stage": "schematic", "lint": fails, "error": None}
    if fails:
        step["error"] = "lint: " + "; ".join(fails)
        return step
    built = zener_build(proj.zen, proj.root)
    step["pcb_build"] = built
    if not built.get("ok"):
        step["error"] = built.get("detail") or "pcb build failed"
    return step


def _run_seed(proj: Project, *, force: bool) -> dict:
    target = proj.place or proj.zen
    if target is None:
        return {"stage": "seed", "error": "no .zen / .place.py"}
    out = seed_job(target, force=force)
    return {
        "stage": "seed",
        "seed": out.get("seed"),
        "error": out.get("error"),
        "returncode": out.get("returncode"),
    }


def _run_place(proj: Project, *, krt_home: Path | None) -> dict:
    try:
        job, _place = _need_place(proj)
    except ValueError as exc:
        return {"stage": "place", "error": str(exc)}
    if not proj.seed or not proj.seed.exists():
        return {"stage": "place", "error": "no seed — run seed first"}
    out = place_job(job, proj.seed, krt_home=krt_home)
    step: dict = {"stage": "place", "pcb": out.get("pcb"), "error": out.get("error")}
    if step["error"]:
        return step
    placed = Path(out["pcb"])
    fails = check_job(job, placed)
    step["check"] = fails
    if fails:
        step["error"] = "check: " + "; ".join(fails)
        return step
    refs = refs_report(job.places, placed.read_text())
    step["refs_missing"] = refs.get("missing") or []
    if refs.get("missing"):
        step["error"] = refs["error"]
    return step


def _run_route(proj: Project, *, krt_home: Path | None) -> dict:
    try:
        job, _place = _need_place(proj)
    except ValueError as exc:
        return {"stage": "route", "error": str(exc)}
    pcb = proj.placed
    if not pcb or not pcb.exists():
        return {"stage": "route", "error": "no placed/ board — run place first"}
    out = route_job(job, pcb, krt_home=krt_home)
    step: dict = {"stage": "route", "pcb": out.get("pcb"), "error": out.get("error")}
    if step["error"]:
        return step
    routed = Path(out["pcb"])
    fails = check_job(job, routed)
    step["check"] = fails
    if fails:
        step["error"] = "check: " + "; ".join(fails)
    return step


def _run_fab(proj: Project) -> dict:
    try:
        job, _place = _need_place(proj)
    except ValueError as exc:
        return {"stage": "fab", "error": str(exc)}
    pcb = proj.routed if proj.routed and proj.routed.exists() else proj.placed
    if not pcb or not pcb.exists():
        return {"stage": "fab", "error": "no routed/ (or placed/) board"}
    components = proj.root / "components"
    out = fab_job(
        job,
        pcb,
        components=components if components.is_dir() else None,
    )
    return {
        "stage": "fab",
        "fab": out.get("fab"),
        "error": out.get("error"),
        "drc_copper_errors": out.get("drc_copper_errors"),
        "missing_lcsc": out.get("missing_lcsc"),
    }


def build_job(
    path: Path,
    *,
    upto: str = "fab",
    start_from: str | None = None,
    force: bool = False,
    dry_run: bool = False,
    krt_home: Path | None = None,
) -> dict:
    path = Path(path)
    proj = resolve_project(path)
    plan = planned_stages(
        proj.stage(), upto=upto, force=force, start_from=start_from
    )
    result: dict = {
        "name": proj.name,
        "root": str(proj.root),
        "stage_before": proj.stage(),
        "plan": plan,
        "steps": [],
        "toolchain": toolchain(),
        "dry_run": dry_run,
        "force": force,
        "error": None,
        "message": None,
    }
    if dry_run:
        result["stage_after"] = proj.stage()
        return result
    if not plan:
        result["stage_after"] = proj.stage()
        result["message"] = (
            f"already {proj.stage()}; pass --force or --from to rebuild "
            "(that is a new PCBA)"
        )
        return result

    krt_home = Path(krt_home) if krt_home else None
    for stage in plan:
        proj = resolve_project(path)
        if stage == "schematic":
            step = _run_schematic(proj)
        elif stage == "seed":
            step = _run_seed(proj, force=force or start_from == "seed")
        elif stage == "place":
            step = _run_place(proj, krt_home=krt_home)
        elif stage == "route":
            step = _run_route(proj, krt_home=krt_home)
        elif stage == "fab":
            step = _run_fab(proj)
        else:
            step = {"stage": stage, "error": f"unknown stage {stage}"}
        result["steps"].append(step)
        if step.get("error"):
            result["error"] = f"{stage}: {step['error']}"
            break

    proj = resolve_project(path)
    result["stage_after"] = proj.stage()
    if not result["error"]:
        result["lock"] = str(_write_lock(proj, result))
    return result
