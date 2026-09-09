"""Emit (and optionally run) a KiCadRoutingTools plan from a compiled job."""

from __future__ import annotations

import os
import shlex
from pathlib import Path

from .compile import CompiledJob


def krt_commands(job: CompiledJob, pcb: Path, krt_home: Path | None = None) -> list[list[str]]:
    krt_home = Path(
        krt_home or os.environ.get("KRT_HOME", str(Path.home() / "Downloads" / "KiCadRoutingTools"))
    )
    py = krt_home / ".venv" / "bin" / "python"
    if not py.exists():
        py = Path("python3")
    router = krt_home / "py_router"
    skip = [f"!{p}" for p in job.skip_autoroute_patterns]
    cmds: list[list[str]] = []

    work = pcb.parent / "pcbspace_route"
    s0 = work / "00_seed.kicad_pcb"
    cmds.append([str(py), str(router / "copy_board.py"), str(pcb), str(s0)])

    prev = s0
    if job.planes:
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

    for pair in job.krt.get("usb_pairs") or []:
        s_usb = work / "02_usb.kicad_pcb"
        usb_cls = next((c for c in job.classes if c.name == pair["class"]), None)
        gap = usb_cls.diff_pair_gap_mm if usb_cls else 0.15
        width = usb_cls.diff_pair_width_mm or (usb_cls.track_width_mm if usb_cls else 0.2)
        cmds.append(
            [
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
                "--diff-pair-intra-match",
                "--keep-input-copper",
            ]
        )
        prev = s_usb

    s_sig = work / "03_signals.kicad_pcb"
    power = job.krt.get("power_nets") or []
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
        "F.Cu",
        "In1.Cu",
        "In2.Cu",
        "B.Cu",
        "--keep-input-copper",
    ]
    if power:
        cmd += ["--power-nets", *power, "--power-nets-widths", *widths]
    for group in job.krt.get("length_match") or []:
        cmd += ["--length-match-group", *group["nets"]]
        cmd += ["--length-match-tolerance", str(group.get("tolerance_mm", 2.0))]
    cmds.append(cmd)
    return cmds


def render_script(cmds: list[list[str]]) -> str:
    lines = ["#!/usr/bin/env bash", "set -euo pipefail"]
    for cmd in cmds:
        lines.append(" ".join(shlex.quote(x) for x in cmd))
    return "\n".join(lines) + "\n"
