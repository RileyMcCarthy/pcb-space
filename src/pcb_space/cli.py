from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .apply import apply_job
from .build import STAGES, build_job
from .check import check_job
from .compile import compile_design
from .initproj import init_job
from .language import load_place_file
from .project import resolve_project
from .refs import refs_report
from .route import route_job
from .fab import fab_job
from .place import place_job
from .review import review_job
from .schematic import lint_zen
from .seed import seed_job
from .silk import silk_job
from .source import check_footprint, import_part, parse_body_mm, search_parts
from .status import nets_job, status_job


def _job(place: Path):
    return compile_design(load_place_file(place))


def _pcb_path(args: argparse.Namespace, job) -> Path:
    raw = getattr(args, "pcb", None) or job.pcb or ""
    if not raw:
        return Path("")
    p = Path(raw)
    if p.exists():
        return p.resolve()
    alt = Path(args.place).resolve().parent / raw
    if alt.exists():
        return alt.resolve()
    return p


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
    pcb = _pcb_path(args, job)
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
    pcb = _pcb_path(args, job)
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


def cmd_source_search(args: argparse.Namespace) -> int:
    data = search_parts(args.query, fab=args.fab, limit=args.limit)
    json.dump(data, sys.stdout, indent=2)
    sys.stdout.write("\n")
    if data.get("errors"):
        return 1
    if not data.get("hits"):
        return 1
    return 0


def cmd_source_import(args: argparse.Namespace) -> int:
    result = import_part(
        args.query,
        Path(args.out),
        kind=args.kind,
        footprint=Path(args.footprint) if args.footprint else None,
        body=args.body,
        manufacturer=args.manufacturer or "",
        fab=args.fab,
    )
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    rec = result["record"]
    if rec.get("status") == "ok":
        return 0
    if rec.get("status") == "gate_failed":
        return 1
    return 2


def cmd_source_check(args: argparse.Namespace) -> int:
    body = parse_body_mm(args.body) if args.body else None
    report = check_footprint(Path(args.path), body_mm=body, tol_mm=args.tol)
    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0 if report.get("ok") else 1


def cmd_place(args: argparse.Namespace) -> int:
    job = _job(Path(args.place))
    pcb = _pcb_path(args, job)
    if not pcb:
        print("pass --pcb path/to/layout.kicad_pcb", file=sys.stderr)
        return 2
    result = place_job(
        job,
        pcb,
        krt_home=Path(args.krt_home) if args.krt_home else None,
        out=Path(args.output) if args.output else None,
        force=not args.no_force,
    )
    json.dump(result, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    if result.get("error"):
        return 2
    krt = result.get("krt") or {}
    rc = krt.get("returncode")
    if rc in (0, None):
        return 0
    if rc == 4:
        return 0
    return 1


def _route_pcb_path(args: argparse.Namespace, job) -> Path:
    pcb = _pcb_path(args, job)
    if getattr(args, "pcb", None) or not pcb:
        return pcb
    placed = pcb.parent / "placed" / pcb.name
    if placed.exists():
        return placed
    return pcb


def _fab_pcb_path(args: argparse.Namespace, job) -> Path:
    pcb = _pcb_path(args, job)
    if getattr(args, "pcb", None) or not pcb:
        return pcb
    routed = pcb.parent / "routed" / pcb.name
    if routed.exists():
        return routed
    placed = pcb.parent / "placed" / pcb.name
    if placed.exists():
        return placed
    return pcb


def _review_pcb_path(args: argparse.Namespace, job) -> Path:
    pcb = _pcb_path(args, job)
    if getattr(args, "pcb", None) or not pcb:
        return pcb
    fab = pcb.parent / "fab" / pcb.name
    if fab.exists():
        return fab
    routed = pcb.parent / "routed" / pcb.name
    if routed.exists():
        return routed
    placed = pcb.parent / "placed" / pcb.name
    if placed.exists():
        return placed
    return pcb


def cmd_review(args: argparse.Namespace) -> int:
    job = _job(Path(args.place))
    pcb = _review_pcb_path(args, job)
    if not pcb:
        print("pass --pcb path/to/routed/layout.kicad_pcb", file=sys.stderr)
        return 2
    result = review_job(
        job,
        pcb,
        place=Path(args.place),
        out_dir=Path(args.output) if args.output else None,
        open_html=not args.no_open,
    )
    json.dump(result, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    if result.get("error"):
        return 1
    return 0


def cmd_silk(args: argparse.Namespace) -> int:
    job = _job(Path(args.place))
    pcb = _review_pcb_path(args, job)
    if not pcb:
        print("pass --pcb path/to/layout.kicad_pcb", file=sys.stderr)
        return 2
    result = silk_job(
        job,
        pcb,
        out=Path(args.output) if args.output else None,
        backup=not args.no_backup,
    )
    json.dump(result, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


def cmd_fab(args: argparse.Namespace) -> int:
    job = _job(Path(args.place))
    pcb = _fab_pcb_path(args, job)
    if not pcb:
        print("pass --pcb path/to/routed/layout.kicad_pcb", file=sys.stderr)
        return 2
    result = fab_job(
        job,
        pcb,
        out_dir=Path(args.output) if args.output else None,
        components=Path(args.components) if args.components else None,
        insert_fids=not args.no_fiducials,
    )
    json.dump(result, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    if result.get("error"):
        return 1
    if result.get("drc_copper_errors"):
        return 1
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    try:
        result = build_job(
            Path(args.path),
            upto=args.upto,
            start_from=args.start_from,
            force=args.force,
            dry_run=args.dry_run,
            krt_home=Path(args.krt_home) if args.krt_home else None,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    json.dump(result, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    if result.get("error"):
        return 2
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    dest = Path(args.dir)
    name = args.name
    if name and args.dir == ".":
        as_dir = Path(name)
        if as_dir.is_dir() or "/" in name.replace("\\", "/"):
            dest = as_dir
            name = None
    try:
        result = init_job(
            dest,
            name=name,
            width=args.width,
            height=args.height,
            layers=args.layers,
            stackup=args.stackup,
            force=args.force,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    json.dump(result, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    if result.get("error") and not result.get("written"):
        return 1
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    try:
        result = status_job(Path(args.path))
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    json.dump(result, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


def cmd_seed(args: argparse.Namespace) -> int:
    try:
        result = seed_job(Path(args.path), force=args.force)
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    json.dump(result, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 2 if result.get("error") else 0


def cmd_refs(args: argparse.Namespace) -> int:
    place = Path(args.place)
    job = _job(place)
    pcb = _pcb_path(args, job)
    if not pcb:
        try:
            proj = resolve_project(place)
        except (FileNotFoundError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
        pcb = proj.seed or Path("")
    if not pcb or not Path(pcb).exists():
        print("pass --pcb path/to/layout.kicad_pcb (seed or placed)", file=sys.stderr)
        return 2
    result = refs_report(job.places, Path(pcb).read_text())
    result["pcb"] = str(pcb)
    json.dump(result, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 1 if result.get("missing") else 0


def cmd_lint(args: argparse.Namespace) -> int:
    try:
        proj = resolve_project(Path(args.path))
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if not proj.zen or not proj.zen.exists():
        print("no .zen — schematic is Zener", file=sys.stderr)
        return 2
    fails = lint_zen(proj.zen.read_text())
    json.dump({"zen": str(proj.zen), "ok": fails == [], "failures": fails}, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 1 if fails else 0


def cmd_nets(args: argparse.Namespace) -> int:
    try:
        result = nets_job(Path(args.place), stub=args.stub)
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    json.dump(result, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


def cmd_route(args: argparse.Namespace) -> int:
    job = _job(Path(args.place))
    pcb = _route_pcb_path(args, job)
    if not pcb:
        print("pass --pcb path/to/placed/layout.kicad_pcb", file=sys.stderr)
        return 2
    result = route_job(
        job,
        pcb,
        krt_home=Path(args.krt_home) if args.krt_home else None,
        out=Path(args.output) if args.output else None,
        run=not args.script_only,
    )
    json.dump(result, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    if result.get("error"):
        return 1
    steps = result.get("steps") or []
    if steps and steps[-1].get("returncode") not in (0, None):
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="pcb-space",
        description="Zener schematic, then place/route/fab in front of KiCad.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    bld = sub.add_parser(
        "build",
        help="schematic → seed → place → route → fab (skips finished stages)",
    )
    bld.add_argument("path", nargs="?", default=".", help=".place.py, .zen, or project directory")
    bld.add_argument(
        "--upto",
        choices=STAGES,
        default="fab",
        help="Stop after this stage (default fab)",
    )
    bld.add_argument(
        "--from",
        dest="start_from",
        choices=STAGES,
        help="Rebuild from this stage (new copper from here)",
    )
    bld.add_argument(
        "--force",
        action="store_true",
        help="Rebuild from schematic through --upto (new PCBA)",
    )
    bld.add_argument("--dry-run", action="store_true", help="Print the plan, do not run")
    bld.add_argument("--krt-home")
    bld.set_defaults(func=cmd_build)

    ini = sub.add_parser("init", help="Write pcb.toml, .zen, and .place.py")
    ini.add_argument("name", nargs="?", help="Board name (default: directory name)")
    ini.add_argument("-C", "--dir", default=".", help="Project directory")
    ini.add_argument("--width", type=float, default=40.0)
    ini.add_argument("--height", type=float, default=30.0)
    ini.add_argument("--layers", type=int, default=2)
    ini.add_argument("--stackup", default="jlcpcb_2l_1oz")
    ini.add_argument("--force", action="store_true")
    ini.set_defaults(func=cmd_init)

    st = sub.add_parser("status", help="Stage: schematic / seeded / placed / routed / fab")
    st.add_argument("path", nargs="?", default=".", help=".place.py, .zen, or project directory")
    st.set_defaults(func=cmd_status)

    sd = sub.add_parser("seed", help="pcb layout --no-open on the .zen (never placed/)")
    sd.add_argument("path", nargs="?", default=".", help=".place.py, .zen, or project directory")
    sd.add_argument("--force", action="store_true")
    sd.set_defaults(func=cmd_seed)

    rf = sub.add_parser("refs", help="Map Place() / Zener names to KiCad references")
    rf.add_argument("place")
    rf.add_argument("--pcb")
    rf.set_defaults(func=cmd_refs)

    ln = sub.add_parser("lint", help="USB-C / MCU USB / layout_path checks on the .zen")
    ln.add_argument("path", nargs="?", default=".", help=".zen or project directory")
    ln.set_defaults(func=cmd_lint)

    nt = sub.add_parser("nets", help="NetReq coverage vs .zen / board nets")
    nt.add_argument("place")
    nt.add_argument("--stub", action="store_true", help="Print NetReq() lines from the .zen")
    nt.set_defaults(func=cmd_nets)

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

    r = sub.add_parser("route", help="Route USB pairs then signals (KRT)")
    r.add_argument("place")
    r.add_argument("--pcb")
    r.add_argument("--krt-home")
    r.add_argument("-o", "--output")
    r.add_argument("--script-only", action="store_true", help="Write the plan script, do not run it")
    r.set_defaults(func=cmd_route)

    pl = sub.add_parser("place", help="Lock CSS poses and legalize unlocked parts (KRT)")
    pl.add_argument("place")
    pl.add_argument("--pcb")
    pl.add_argument("--krt-home")
    pl.add_argument("-o", "--output")
    pl.add_argument("--no-force", action="store_true", help="Do not re-seed; only repair")
    pl.set_defaults(func=cmd_place)

    sk = sub.add_parser("silk", help="Legalize F.SilkS reference text (size + slots)")
    sk.add_argument("place")
    sk.add_argument("--pcb")
    sk.add_argument("-o", "--output", help="Write a copy (default: edit the board in place)")
    sk.add_argument("--no-backup", action="store_true")
    sk.set_defaults(func=cmd_silk)

    rv = sub.add_parser("review", help="HTML review: schematic, copper SVGs, 3D GLB")
    rv.add_argument("place")
    rv.add_argument("--pcb")
    rv.add_argument("-o", "--output", help="Output directory (default: layout/.../review)")
    rv.add_argument("--no-open", action="store_true", help="Write HTML but do not open a browser")
    rv.set_defaults(func=cmd_review)

    f = sub.add_parser("fab", help="JLCPCB package: Gerbers, drill, BOM, CPL, fab notes")
    f.add_argument("place")
    f.add_argument("--pcb")
    f.add_argument("-o", "--output", help="Output directory (default: layout/.../fab)")
    f.add_argument("--components", help="components/ dir with SOURCE.json")
    f.add_argument("--no-fiducials", action="store_true")
    f.set_defaults(func=cmd_fab)

    s = sub.add_parser("source", help="Search distributors and attach symbols/footprints")
    ss = s.add_subparsers(dest="source_cmd", required=True)

    ssearch = ss.add_parser("search", help="Search LCSC (DigiKey/Mouser if keys are set)")
    ssearch.add_argument("query")
    ssearch.add_argument("--fab", default="jlcpcb", choices=("jlcpcb", "any"))
    ssearch.add_argument("--limit", type=int, default=10)
    ssearch.set_defaults(func=cmd_source_search)

    simp = ss.add_parser("import", help="Write a Zener component package + SOURCE.json")
    simp.add_argument("query")
    simp.add_argument("-o", "--out", default="components")
    simp.add_argument("--kind", default="auto", choices=("auto", "generic", "ic"))
    simp.add_argument("--footprint", help="Existing .kicad_mod to copy into the package")
    simp.add_argument("--body", help="Datasheet body LxW mm, e.g. 1.5x1.5")
    simp.add_argument("--manufacturer", default="")
    simp.add_argument("--fab", default="jlcpcb", choices=("jlcpcb", "any"))
    simp.set_defaults(func=cmd_source_import)

    schk = ss.add_parser("check", help="Fail if footprint body does not match datasheet")
    schk.add_argument("path", help="Package dir, .zen, or .kicad_mod")
    schk.add_argument("--body", help="Datasheet body LxW mm")
    schk.add_argument("--tol", type=float, default=0.2)
    schk.set_defaults(func=cmd_source_check)

    args = p.parse_args(argv)
    return args.func(args)


def source_main(argv: list[str] | None = None) -> int:
    """Entry point for the `pcb-source` alias."""
    if argv is None:
        argv = sys.argv[1:]
    return main(["source", *argv])


if __name__ == "__main__":
    raise SystemExit(main())
