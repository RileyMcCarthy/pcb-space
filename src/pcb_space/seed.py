"""Wrap ``pcb layout --no-open``. Seed only — never placed/routed/fab."""

from __future__ import annotations

import subprocess
from pathlib import Path
from shutil import which

from .project import packed_reason, pcb_cli, resolve_project


def seed_job(path: Path, *, force: bool = False) -> dict:
    proj = resolve_project(path)
    result: dict = {
        "zen": str(proj.zen) if proj.zen else None,
        "seed": str(proj.seed) if proj.seed else None,
        "cmd": None,
        "error": None,
    }
    if not proj.zen or not proj.zen.exists():
        result["error"] = (
            "no .zen next to the project. Schematic is Zener: write a .zen "
            "and run pcb build, then pcb-space seed."
        )
        return result
    if proj.seed:
        reason = packed_reason(proj.seed)
        if reason and not force:
            result["error"] = reason
            return result
    cli = pcb_cli()
    if not Path(cli).exists() and which("pcb") is None:
        result["error"] = (
            f"pcb (Zener) not found ({cli}). "
            "Install diodeinc/pcb — pcb-space does not replace it."
        )
        return result
    cmd = [str(cli), "layout", "--no-open", str(proj.zen)]
    result["cmd"] = cmd
    proc = subprocess.run(cmd, cwd=str(proj.root), capture_output=True, text=True)
    result["returncode"] = proc.returncode
    result["stdout"] = (proc.stdout or "")[-2000:]
    result["stderr"] = (proc.stderr or "")[-1500:]
    if proc.returncode != 0:
        result["error"] = (
            result["stderr"] or result["stdout"] or f"pcb layout exited {proc.returncode}"
        ).strip()[-500:]
        return result
    if proj.seed and proj.seed.exists():
        reason = packed_reason(proj.seed)
        if reason:
            result["error"] = "pcb layout wrote a packed board: " + reason
            return result
    elif proj.seed and not proj.seed.exists():
        result["error"] = f"pcb layout did not write {proj.seed}"
        return result
    return result
