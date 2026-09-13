"""Emit and run a KiCadRoutingTools plan from a compiled job."""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

from .apply import apply_job
from .compile import CompiledJob
from .intent import place_edge
from .place import copy_with_siblings, krt_python


def copper_layers(n: int) -> list[str]:
    if n <= 2:
        return ["F.Cu", "B.Cu"]
    return ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]


def layer_costs(job: CompiledJob) -> list[str]:
    layers = copper_layers(job.layers)
    costs = {name: 1.0 for name in layers}
    for _net, layer in job.planes:
        if layer in costs:
            costs[layer] = 3.0
    if job.layers <= 2:
        return ["1.0", "1.0"]
    return [str(costs[name]) for name in layers]


def krt_commands(
    job: CompiledJob,
    pcb: Path,
    krt_home: Path | None = None,
    work: Path | None = None,
) -> list[list[str]]:
    krt_home = Path(
        krt_home or os.environ.get("KRT_HOME", str(Path.home() / "Downloads" / "KiCadRoutingTools"))
    )
    py = krt_python(krt_home)
    router = krt_home / "py_router"
    skip = [f"!{p}" for p in job.skip_autoroute_patterns]
    layers = copper_layers(job.layers)
    costs = layer_costs(job)
    floor = "0.10" if job.layers <= 2 else "0.16"
    work = Path(work) if work else Path(pcb).parent / "routed"
    cmds: list[list[str]] = []
    prev = Path(pcb)

    # USB-C 0.5 mm pitch: surface routing cannot leave the pin row. KRT's
    # own rescue says qfn_fanout underpad + via-in-pad on the receptacle.
    edge_refs = [
        p.ref for p in job.places if p.locked and place_edge(p) in ("east", "south", "west", "north")
    ]
    if job.krt.get("usb_pairs") and edge_refs:
        s_fo = work / "01_connector_fanout.kicad_pcb"
        cmds.append(
            [
                str(py),
                "-X",
                "utf8",
                str(router / "qfn_fanout.py"),
                str(prev),
                "--output",
                str(s_fo),
                "--component",
                edge_refs[0],
                "--nets",
                "*",
                "!GND",
                "--escape-method",
                "underpad",
                "--allow-via-in-pad",
                "--fab-tier",
                "advanced",
                "--width",
                floor,
                "--clearance",
                floor,
                "--via-size",
                "0.25",
                "--via-drill",
                "0.15",
                "--grid-step",
                "0.05" if job.layers <= 2 else "0.1",
            ]
        )
        prev = s_fo

    pour_first = bool(job.planes) and job.layers > 2
    if pour_first:
        s1 = work / "01_planes.kicad_pcb"
        cmds.append(
            [
                str(py),
                "-X",
                "utf8",
                str(router / "route_planes.py"),
                str(prev),
                str(s1),
                "--nets",
                *[n for n, _ in job.planes],
                "--plane-layers",
                *[l for _, l in job.planes],
            ]
        )
        prev = s1

    for i, pair in enumerate(job.krt.get("usb_pairs") or []):
        s_usb = work / f"02_usb_{i}.kicad_pcb"
        usb_cls = next((c for c in job.classes if c.name == pair["class"]), None)
        gap = usb_cls.diff_pair_gap_mm if usb_cls else 0.16
        width = usb_cls.diff_pair_width_mm or (usb_cls.track_width_mm if usb_cls else 0.16)
        clr = usb_cls.clearance_mm if usb_cls else 0.16
        if gap < clr:
            gap = clr
        cmd = [
            str(py),
            "-X",
            "utf8",
            str(router / "route_diff.py"),
            str(prev),
            str(s_usb),
            "--nets",
            *pair["nets"],
            "--track-width",
            str(width),
            "--diff-pair-gap",
            str(gap),
            "--clearance",
            str(clr),
            "--layers",
            *layers,
            "--layer-costs",
            *costs,
            "--diff-pair-intra-match",
            "--keep-input-copper",
            "--grid-step",
            "0.05" if job.layers <= 2 else "0.1",
        ]
        # 4-layer 90 Ω is manufacturable. 1.6 mm 2-layer is not — width is
        # already clamped; do not pass --impedance or KRT will widen it again.
        if job.layers >= 4:
            cmd.extend(["--impedance", "90"])
        cmds.append(cmd)
        prev = s_usb

    s_sig = work / "03_signals.kicad_pcb"
    power = [str(n) for n in (job.krt.get("power_nets") or [])]
    widths = []
    for name in power:
        cls = next((c for c in job.classes if name in c.patterns or c.name == "Power"), None)
        widths.append(str(cls.track_width_mm if cls else 0.4))
    cmd = [
        str(py),
        "-X",
        "utf8",
        str(router / "route.py"),
        str(prev),
        str(s_sig),
        "--nets",
        "*",
        *skip,
        "--layers",
        *layers,
        "--layer-costs",
        *costs,
        "--track-width",
        floor,
        "--clearance",
        floor,
        "--grid-step",
        "0.05" if job.layers <= 2 else "0.1",
        "--max-ripup",
        "5",
        "--no-bga-zones",
        "--keep-input-copper",
    ]
    if power:
        cmd.extend(["--power-nets", *power, "--power-nets-widths", *widths])
    for group in job.krt.get("length_match") or []:
        cmd.extend(["--length-match-group", *group["nets"]])
        cmd.extend(["--length-match-tolerance", str(group.get("tolerance_mm", 2.0))])
    cmds.append(cmd)
    prev = s_sig

    # Dense 2-layer: route both sides first, pour GND last, then finalize.
    if job.layers <= 2 and "GND" in power:
        s_pour = work / "04_gnd_pour.kicad_pcb"
        cmds.append(
            [
                str(py),
                "-X",
                "utf8",
                str(router / "route_planes.py"),
                str(prev),
                str(s_pour),
                "--nets",
                "GND",
                "GND",
                "--plane-layers",
                "F.Cu",
                "B.Cu",
            ]
        )
        prev = s_pour
        s_fin = work / "05_finalize.kicad_pcb"
        fin = [
            str(py),
            "-X",
            "utf8",
            str(router / "route.py"),
            str(prev),
            str(s_fin),
            "--nets",
            "*",
            *skip,
            "--layers",
            *layers,
            "--layer-costs",
            *costs,
            "--track-width",
            floor,
            "--clearance",
            floor,
            "--grid-step",
            "0.05",
            "--keep-input-copper",
        ]
        if power:
            fin.extend(["--power-nets", *power, "--power-nets-widths", *widths])
        cmds.append(fin)
    return cmds


def render_script(cmds: list[list[str]]) -> str:
    lines = ["#!/usr/bin/env bash", "set -euo pipefail"]
    for cmd in cmds:
        lines.append(" ".join(shlex.quote(x) for x in cmd))
    return "\n".join(lines) + "\n"


def _default_routed_out(pcb: Path) -> Path:
    if pcb.parent.name == "placed":
        return pcb.parent.parent / "routed" / pcb.name
    return pcb.parent / "routed" / pcb.name


def route_job(
    job: CompiledJob,
    pcb: Path,
    *,
    krt_home: Path | None = None,
    out: Path | None = None,
    run: bool = True,
) -> dict:
    pcb = Path(pcb)
    krt_home = Path(
        krt_home or os.environ.get("KRT_HOME", str(Path.home() / "Downloads" / "KiCadRoutingTools"))
    )
    out = Path(out) if out else _default_routed_out(pcb)
    work = out.parent
    work.mkdir(parents=True, exist_ok=True)

    seed = work / "00_seed.kicad_pcb"
    copy_with_siblings(pcb, seed)
    applied = apply_job(job, seed, backup=False)
    cmds = krt_commands(job, seed, krt_home, work=work)
    script_path = work / "pcbspace_route.sh"
    script_path.write_text(render_script(cmds))
    script_path.chmod(0o755)

    result = {
        "pcb": str(out),
        "seed": str(seed),
        "script": str(script_path),
        "applied": applied,
        "krt_home": str(krt_home),
        "cmds": cmds,
        "steps": [],
        "error": None,
    }
    if not run:
        return result

    router = krt_home / "py_router" / "route.py"
    if not router.exists():
        result["error"] = f"KRT route.py not found under {krt_home}"
        return result

    last_board = seed
    for cmd in cmds:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        step = {
            "cmd": cmd,
            "returncode": proc.returncode,
            "stdout": (proc.stdout or "")[-4000:],
            "stderr": (proc.stderr or "")[-2000:],
        }
        result["steps"].append(step)
        # copy_board / route write the last path argument that ends with .kicad_pcb
        boards = [a for a in cmd if str(a).endswith(".kicad_pcb")]
        if len(boards) >= 2:
            last_board = Path(boards[-1])
        missing = len(boards) >= 2 and not Path(boards[-1]).exists()
        if proc.returncode != 0 or missing:
            tool = next((a for a in cmd if str(a).endswith(".py")), str(cmd[:3]))
            why = f"rc={proc.returncode}"
            if missing:
                why += f", no output {boards[-1]}"
            result["error"] = f"step failed {why}: {tool}"
            if last_board.exists():
                copy_with_siblings(last_board, out)
            return result

    if last_board.exists() and last_board.resolve() != out.resolve():
        copy_with_siblings(last_board, out)
    elif last_board.exists() and not out.exists():
        copy_with_siblings(last_board, out)
    result["pcb"] = str(out)
    return result
