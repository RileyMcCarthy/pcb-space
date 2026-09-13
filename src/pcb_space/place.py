"""Legalize unlocked parts with KiCadRoutingTools, honouring CSS locks."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from .apply import apply_job
from .compile import CompiledJob
from .intent import intent_from_job
from .project import packed_reason
from .refs import build_alias_index
from .silk import silk_job


SIBLINGS = (".kicad_pro", ".kicad_prl", ".kicad_dru")


def krt_python(krt_home: Path) -> Path:
    py = krt_home / ".venv" / "bin" / "python"
    if py.exists():
        return py
    return Path("python3")


def copy_with_siblings(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    sbase = str(src)[: -len(".kicad_pcb")]
    dbase = str(dst)[: -len(".kicad_pcb")]
    for ext in SIBLINGS:
        s = Path(sbase + ext)
        if s.exists():
            shutil.copy2(s, dbase + ext)


def place_job(
    job: CompiledJob,
    pcb: Path,
    *,
    krt_home: Path | None = None,
    out: Path | None = None,
    force: bool = True,
) -> dict:
    pcb = Path(pcb)
    reason = packed_reason(pcb)
    if reason:
        return {
            "pcb": str(pcb),
            "error": reason,
            "krt": None,
        }
    krt_home = Path(
        krt_home or os.environ.get("KRT_HOME", str(Path.home() / "Downloads" / "KiCadRoutingTools"))
    )
    # Sibling `*_placed.kicad_pro` in the seed directory makes `pcb layout`
    # refuse the project (multiple .kicad_pro). Keep the placed board in a
    # subdirectory.
    out = Path(out) if out else pcb.parent / "placed" / pcb.name
    work = out.with_name(out.stem + ".preseed.kicad_pcb")
    copy_with_siblings(pcb, work)
    applied = apply_job(job, work, backup=False)
    aliases = {k: v for k, v in (applied.get("aliases") or {}).items() if v}
    aliases.update(build_alias_index(work.read_text()))
    intent = intent_from_job(job, aliases)
    intent_path = out.with_name(out.stem + ".intent.json")
    intent_path.write_text(json.dumps(intent, indent=2) + "\n")

    seed = krt_home / "py_placer" / "place_seed.py"
    result = {
        "pcb": str(out),
        "preseed": str(work),
        "intent": str(intent_path),
        "applied": applied,
        "krt": None,
        "krt_home": str(krt_home),
    }
    if not seed.exists():
        copy_with_siblings(work, out)
        result["pcb"] = str(out)
        result["error"] = f"KRT place_seed.py not found under {krt_home}"
        return result

    ignore = [str(n) for n in (job.krt.get("power_nets") or [])]
    cmd = [
        str(krt_python(krt_home)),
        "-X",
        "utf8",
        str(seed),
        str(work),
        str(out),
        "--intent",
        str(intent_path),
        "--anchors-first",
    ]
    if force:
        cmd.append("--force")
    if ignore:
        cmd.extend(["--ignore-nets", *ignore])
    proc = subprocess.run(cmd, capture_output=True, text=True)
    result["krt"] = {
        "cmd": cmd,
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "")[-4000:],
        "stderr": (proc.stderr or "")[-2000:],
    }
    if out.exists():
        wbase = str(work)[: -len(".kicad_pcb")]
        obase = str(out)[: -len(".kicad_pcb")]
        for ext in SIBLINGS:
            s, d = Path(wbase + ext), Path(obase + ext)
            if s.exists() and not d.exists():
                shutil.copy2(s, d)
        result["silk"] = silk_job(job, out, backup=False)
    else:
        copy_with_siblings(work, out)
        result["error"] = result["error"] if result.get("error") else "place_seed wrote nothing"
    return result
