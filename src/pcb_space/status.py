"""Project stage: schematic → seed → placed → routed → fab."""

from __future__ import annotations

import fnmatch
import subprocess
from pathlib import Path

from .check import check_job
from .compile import compile_design
from .language import load_place_file
from .project import (
    board_net_names,
    packed_reason,
    pcb_cli,
    resolve_project,
)
from .refs import refs_report
from .schematic import lint_zen, parse_zen_nets


def _file_info(path: Path | None) -> dict:
    if path is None:
        return {"path": None, "exists": False}
    info = {"path": str(path), "exists": path.exists(), "packed": False}
    if path.exists() and path.suffix == ".kicad_pcb":
        text = path.read_text()
        info["packed"] = packed_reason(path, text) is not None
        info["packed_reason"] = packed_reason(path, text)
    return info


def _pcb_build(zen: Path, root: Path) -> dict:
    cli = pcb_cli()
    from shutil import which

    if not Path(cli).exists() and which("pcb") is None:
        return {"ran": False, "ok": None, "detail": "pcb (Zener) not on PATH"}
    proc = subprocess.run(
        [str(cli), "build", str(zen)],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    return {
        "ran": True,
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "detail": out[-1500:],
    }


def _best_pcb(proj) -> Path | None:
    for p in (proj.routed, proj.placed, proj.seed):
        if p and p.exists():
            return p
    return None


def _uncovered_nets(place: Path | None, pcb: Path | None, zen: Path | None) -> list[str]:
    patterns: list[str] = []
    if place and place.exists():
        try:
            design = load_place_file(place)
        except Exception:
            design = None
        if design:
            for req in design.netreqs:
                patterns.extend(req.nets)
    names: list[str] = []
    if pcb and pcb.exists():
        names = board_net_names(pcb.read_text())
    elif zen and zen.exists():
        names = [n.name for n in parse_zen_nets(zen.read_text())]
    if not names:
        return []
    if not patterns:
        return names
    return [
        n
        for n in names
        if not any(fnmatch.fnmatch(n, pat) for pat in patterns)
    ]


def status_job(path: Path) -> dict:
    proj = resolve_project(path)
    pcb = _best_pcb(proj)
    locks: dict = {"ok": None, "failures": [], "pcb": str(pcb) if pcb else None}
    if proj.place and proj.place.exists() and pcb:
        try:
            job = compile_design(load_place_file(proj.place))
            fails = check_job(job, pcb)
            locks = {"ok": fails == [], "failures": fails, "pcb": str(pcb)}
        except Exception as exc:  # noqa: BLE001
            locks = {"ok": False, "failures": [str(exc)], "pcb": str(pcb)}
    refs: dict = {}
    if proj.place and proj.place.exists() and pcb:
        try:
            job = compile_design(load_place_file(proj.place))
            refs = refs_report(job.places, pcb.read_text())
            refs["pcb"] = str(pcb)
        except Exception as exc:  # noqa: BLE001
            refs = {"error": str(exc), "missing": []}
    lint = []
    if proj.zen and proj.zen.exists():
        lint = lint_zen(proj.zen.read_text())
    build = (
        _pcb_build(proj.zen, proj.root)
        if proj.zen and proj.zen.exists()
        else {"ran": False, "ok": None, "detail": "no .zen"}
    )
    return {
        "name": proj.name,
        "root": str(proj.root),
        "stage": proj.stage(),
        "zen": str(proj.zen) if proj.zen else None,
        "place": str(proj.place) if proj.place else None,
        "seed": _file_info(proj.seed),
        "placed": _file_info(proj.placed),
        "routed": _file_info(proj.routed),
        "fab": _file_info(proj.fab),
        "pcb_build": build,
        "lint": lint,
        "locks": locks,
        "refs_missing": refs.get("missing") or [],
        "nets_uncovered": _uncovered_nets(proj.place, pcb, proj.zen),
        "errors": proj.errors,
        "do_not": [
            "pcb layout on placed/, routed/, or fab/ (duplicates footprints)",
            "pcb-space place on a packed board — seed is layout/<name>/layout.kicad_pcb",
        ],
    }


def nets_job(path: Path, *, stub: bool = False) -> dict:
    from .schematic import stub_netreqs

    proj = resolve_project(path)
    pcb = _best_pcb(proj)
    uncovered = _uncovered_nets(proj.place, pcb, proj.zen)
    stub_text = ""
    if stub and proj.zen and proj.zen.exists():
        stub_text = stub_netreqs(proj.zen.read_text())
    zen_nets = (
        [{"ident": n.ident, "kind": n.kind, "name": n.name} for n in parse_zen_nets(proj.zen.read_text())]
        if proj.zen and proj.zen.exists()
        else []
    )
    return {
        "zen_nets": zen_nets,
        "uncovered": uncovered,
        "stub": stub_text or None,
        "error": None if not uncovered else f"uncovered nets: {', '.join(uncovered)}",
    }
