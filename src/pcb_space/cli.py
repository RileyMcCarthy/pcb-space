from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .apply import apply_job
from .check import check_job
from .compile import compile_design
from .language import load_place_file
from .route import krt_commands, render_script


def _job(place: Path):
    return compile_design(load_place_file(place))


def cmd_compile(args: argparse.Namespace) -> int:
    job = _job(Path(args.place))
    data = job.to_dict()
    text = json.dumps(data, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(text)
        print(args.output)
    else:
        sys.stdout.write(text)
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    job = _job(Path(args.place))
    pcb = Path(args.pcb or job.pcb or "")
    if not pcb:
        print("pass --pcb path/to/layout.kicad_pcb", file=sys.stderr)
        return 2
    result = apply_job(job, pcb, backup=not args.no_backup)
    print(json.dumps(result, indent=2))
    if result["missing"]:
        print("warning: missing refs:", ", ".join(result["missing"]), file=sys.stderr)
        return 1
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    job = _job(Path(args.place))
    pcb = Path(args.pcb or job.pcb or "")
    if not pcb:
        print("pass --pcb path/to/layout.kicad_pcb", file=sys.stderr)
        return 2
    failures = check_job(job, pcb)
    if not failures:
        print("ok")
        return 0
    for f in failures:
        print("FAIL", f)
    return 1


def cmd_route(args: argparse.Namespace) -> int:
    job = _job(Path(args.place))
    pcb = Path(args.pcb or job.pcb or "")
    if not pcb:
        print("pass --pcb path/to/layout.kicad_pcb", file=sys.stderr)
        return 2
    cmds = krt_commands(job, pcb, Path(args.krt_home) if args.krt_home else None)
    script = render_script(cmds)
    out = Path(args.output) if args.output else pcb.parent / "pcbspace_route.sh"
    out.write_text(script)
    out.chmod(0o755)
    print(out)
    if args.run:
        import subprocess

        r = subprocess.run(["bash", str(out)])
        return r.returncode
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="pcb-space",
        description="Compile Place/NetReq intent into KiCad geometry and engine jobs.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("compile", help="Print compiled JSON")
    c.add_argument("place")
    c.add_argument("-o", "--output")
    c.set_defaults(func=cmd_compile)

    a = sub.add_parser("apply", help="Lock poses, write net classes and keepouts")
    a.add_argument("place")
    a.add_argument("--pcb")
    a.add_argument("--no-backup", action="store_true")
    a.set_defaults(func=cmd_apply)

    k = sub.add_parser("check", help="Fail if locked parts moved or keepouts missing")
    k.add_argument("place")
    k.add_argument("--pcb")
    k.set_defaults(func=cmd_check)

    r = sub.add_parser("route", help="Write a KiCadRoutingTools plan script")
    r.add_argument("place")
    r.add_argument("--pcb")
    r.add_argument("--krt-home")
    r.add_argument("-o", "--output")
    r.add_argument("--run", action="store_true", help="Run the script after writing it")
    r.set_defaults(func=cmd_route)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
