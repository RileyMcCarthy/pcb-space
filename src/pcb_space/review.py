"""One-page HTML review: schematic netlist, KiCad PCB SVGs, GLB 3D."""

from __future__ import annotations

import base64
import html
import json
import os
import re
import shutil
import subprocess
import webbrowser
from pathlib import Path

from .compile import CompiledJob
from .fab import kicad_cli
from .sexp import matching_paren
from .silk import silk_job


def _default_review_dir(pcb: Path) -> Path:
    if pcb.parent.name in ("routed", "placed", "fab"):
        return pcb.parent.parent / "review"
    return pcb.parent / "review"


def find_zen(place: Path, pcb: Path) -> Path | None:
    from .project import find_zen as _find

    return _find(place, pcb)


def find_netlist(pcb: Path) -> Path | None:
    for parent in (pcb.parent, *pcb.parents):
        n = parent / "default.net"
        if n.exists():
            return n
    return None


def pcb_cli() -> Path:
    from .project import pcb_cli as _pcb_cli

    return _pcb_cli()


_PORT = re.compile(r'\("([^"]+)",\s*\[([^\]]*)\]')


def parse_symbol_ports(block: str) -> tuple[str, list[tuple[str, str]]]:
    name_m = re.search(r'name\s*=\s*"([^"]+)"', block)
    name = name_m.group(1) if name_m else "SYM"
    ports: list[tuple[str, str]] = []
    used_nums: set[str] = set()
    for m in _PORT.finditer(block):
        pads = [p.strip().strip('"') for p in m.group(2).split(",") if p.strip().strip('"')]
        num = pads[0] if pads else str(len(ports) + 1)
        if num in used_nums:
            num = f"{num}_{m.group(1)}"
        used_nums.add(num)
        ports.append((m.group(1), num))
    return name, ports


def kicad10_box_symbol(name: str, ports: list[tuple[str, str]], ref: str = "U") -> str:
    """KiCad 10 box symbol whose pin *names* match Zener io() ports."""
    n = max(len(ports), 1)
    left = ports[: (n + 1) // 2]
    right = ports[(n + 1) // 2 :]
    pitch = 2.54
    rows = max(len(left), len(right), 1)
    half_h = rows * pitch / 2
    half_w = 12.7
    pin_len = 3.81

    def pin_sexp(pname: str, pnum: str, x: float, y: float, rot: int) -> str:
        return (
            f'\t\t\t(pin unspecified line\n'
            f'\t\t\t\t(at {x:g} {y:g} {rot})\n'
            f'\t\t\t\t(length {pin_len})\n'
            f'\t\t\t\t(name "{pname}"\n'
            f'\t\t\t\t\t(effects (font (size 1.27 1.27)))\n'
            f'\t\t\t\t)\n'
            f'\t\t\t\t(number "{pnum}"\n'
            f'\t\t\t\t\t(effects (font (size 1.27 1.27)))\n'
            f'\t\t\t\t)\n'
            f'\t\t\t)\n'
        )

    pins = []
    for i, (pname, pnum) in enumerate(left):
        y = half_h - pitch / 2 - i * pitch
        pins.append(pin_sexp(pname, pnum, -(half_w + pin_len), y, 0))
    for i, (pname, pnum) in enumerate(right):
        y = half_h - pitch / 2 - i * pitch
        pins.append(pin_sexp(pname, pnum, half_w + pin_len, y, 180))
    return (
        "(kicad_symbol_lib\n"
        "\t(version 20251024)\n"
        '\t(generator "pcb-space")\n'
        '\t(generator_version "10.0")\n'
        f'\t(symbol "{name}"\n'
        "\t\t(exclude_from_sim no)\n"
        "\t\t(in_bom yes)\n"
        "\t\t(on_board yes)\n"
        f'\t\t(property "Reference" "{ref}"\n'
        f"\t\t\t(at 0 {half_h + 2.54:g} 0)\n"
        "\t\t\t(effects (font (size 1.27 1.27)))\n"
        "\t\t)\n"
        f'\t\t(property "Value" "{name}"\n'
        f"\t\t\t(at 0 {-half_h - 2.54:g} 0)\n"
        "\t\t\t(effects (font (size 1.27 1.27)))\n"
        "\t\t)\n"
        f'\t\t(symbol "{name}_0_1"\n'
        f"\t\t\t(rectangle\n"
        f"\t\t\t\t(start {-half_w:g} {half_h:g})\n"
        f"\t\t\t\t(end {half_w:g} {-half_h:g})\n"
        "\t\t\t\t(stroke (width 0.254) (type default))\n"
        "\t\t\t\t(fill (type background))\n"
        "\t\t\t)\n"
        "\t\t)\n"
        f'\t\t(symbol "{name}_1_1"\n'
        + "".join(pins)
        + "\t\t)\n"
        "\t)\n"
        ")\n"
    )


def rewrite_definition_symbols(components: Path) -> list[str]:
    """Emit KiCad-10 box symbols from Zener pin maps so pcb apply schematic can run.

    Layout zens keep Symbol(name=, definition=). That form has no graphics.
    EasyEDA .kicad_sym pin names often do not match Zener io() names.
    """
    changed: list[str] = []
    for zen in components.rglob("*.zen"):
        text = zen.read_text()
        needle = "symbol = Symbol("
        j = text.find(needle)
        if j < 0 or "definition" not in text[j : j + 8000]:
            continue
        sym_at = text.find("Symbol(", j)
        open_at = text.find("(", sym_at)
        end = matching_paren(text, open_at)
        block = text[open_at : end + 1]
        if "definition" not in block:
            continue
        name, ports = parse_symbol_ports(block)
        if not ports:
            continue
        pref_m = re.search(r'prefix\s*=\s*"([^"]+)"', text)
        ref = pref_m.group(1) if pref_m else "U"
        sym_path = zen.parent / "pcbspace.kicad_sym"
        sym_path.write_text(kicad10_box_symbol(name, ports, ref=ref))
        replace_end = end + 1
        if replace_end < len(text) and text[replace_end] == ",":
            replace_end += 1
        text = text[:sym_at] + 'Symbol("./pcbspace.kicad_sym"),' + text[replace_end:]
        zen.write_text(text)
        changed.append(str(zen.relative_to(components)))
    return changed


def export_zener_schematic(zen: Path, out_dir: Path, cli: Path) -> tuple[Path | None, list[dict]]:
    """Copy the Zener workspace, attach KiCad-10 symbols, pcb apply schematic, plot."""
    steps: list[dict] = []
    zen = Path(zen).resolve()
    out_dir = Path(out_dir).resolve()
    work = out_dir / "zener_sch"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    root = zen.parent
    shutil.copy2(zen, work / zen.name)
    if (root / "pcb.toml").exists():
        # Nested [workspace] inside the board tree makes `pcb build` fail.
        lines = [
            ln
            for ln in (root / "pcb.toml").read_text().splitlines()
            if not ln.startswith("[workspace]") and "pcb-version" not in ln
        ]
        (work / "pcb.toml").write_text("\n".join(lines).strip() + "\n")
    if (root / "components").is_dir():
        shutil.copytree(
            root / "components",
            work / "components",
            ignore=shutil.ignore_patterns("_easyeda", "__pycache__"),
        )
        rewrite_definition_symbols(work / "components")
    pcb_dir = root / ".pcb"
    if pcb_dir.is_dir():
        # Must copy, not symlink: pcb refuses symbol paths that resolve outside
        # this workspace ("must resolve inside a workspace or dependency package").
        shutil.copytree(
            pcb_dir.resolve(),
            work / ".pcb",
            ignore=shutil.ignore_patterns("__pycache__", ".git"),
        )
    board = (work / zen.name).read_text()
    if "schematic" not in board.split("Board(")[-1]:
        (work / zen.name).write_text(
            board.replace("layout_path = ", "schematic = True, layout_path = ", 1)
            if "layout_path" in board
            else board
        )
    elif "schematic = False" in board:
        (work / zen.name).write_text(board.replace("schematic = False", "schematic = True", 1))
    pcb = pcb_cli()
    env = _kicad_env()
    env["PATH"] = str(pcb.parent) + os.pathsep + env.get("PATH", "")
    proc = subprocess.run(
        [str(pcb), "apply", "schematic", "--no-open", "-f", "json", str(work / zen.name)],
        capture_output=True,
        text=True,
        cwd=work,
        env=env,
    )
    steps.append(
        {
            "cmd": [str(pcb), "apply", "schematic", "--no-open", str(work / zen.name)],
            "returncode": proc.returncode,
            "stdout": (proc.stdout or "")[-2000:],
            "stderr": (proc.stderr or "")[-2000:],
        }
    )
    schs = sorted(work.rglob("*.kicad_sch"))
    if not schs:
        return None, steps
    sch = schs[0]
    sch_dir = out_dir / "sch"
    sch_dir.mkdir(exist_ok=True)
    dest_sch = out_dir / "schematic.kicad_sch"
    shutil.copy2(sch, dest_sch)
    # Copy sibling project files kicad-cli may need, then drop the nested workspace.
    for ext in (".kicad_pro", ".kicad_prl"):
        sib = sch.with_suffix(ext)
        if sib.exists():
            shutil.copy2(sib, dest_sch.with_suffix(ext))
    steps.append(_export_sch_svg(cli, dest_sch, sch_dir))
    pdf = out_dir / "schematic.pdf"
    steps.append(
        _run(
            [
                str(cli),
                "sch",
                "export",
                "pdf",
                "--exclude-drawing-sheet",
                "--no-background-color",
                "-o",
                str(pdf),
                str(dest_sch),
            ]
        )
    )
    return dest_sch, steps


def find_schematic(place: Path, pcb: Path) -> Path | None:
    roots = [place.parent, pcb.parent, *list(pcb.parents)[:4]]
    for root in roots:
        hits = sorted(root.glob("*.kicad_sch"))
        if hits:
            return hits[0]
    return None


def find_bom(pcb: Path) -> Path | None:
    for parent in (pcb.parent, *pcb.parents):
        b = parent / "fab" / "bom.csv"
        if b.exists():
            return b
        if parent.name == "fab" and (parent / "bom.csv").exists():
            return parent / "bom.csv"
    return None


_COMP = re.compile(
    r'\(comp \(ref "([^"]+)"\)\s+\(value "([^"]*)"\)\s+\(footprint "([^"]*)"',
)
_NET_BLOCK = re.compile(
    r'\(net \(code "[^"]*"\) \(name "([^"]*)"\)(.*?)(?=\n    \(net |\n  \)\n\))',
    re.S,
)
_NODE = re.compile(r'\(node \(ref "([^"]+)"\) \(pin "([^"]*)"\)')


def parse_netlist(text: str) -> tuple[list[dict], list[dict]]:
    comps = [
        {
            "ref": m.group(1),
            "value": m.group(2),
            "footprint": m.group(3).split(":")[-1],
        }
        for m in _COMP.finditer(text)
    ]
    nets = []
    for m in _NET_BLOCK.finditer(text):
        nodes = [{"ref": r, "pin": p} for r, p in _NODE.findall(m.group(2))]
        nets.append({"name": m.group(1), "nodes": nodes})
    return comps, nets


def schematic_svg(nets: list[dict]) -> str:
    """Wiring-list schematic: one row per net, pins as cells. Not Eeschema."""
    rows = []
    for net in nets:
        by_ref: dict[str, list[str]] = {}
        for n in net["nodes"]:
            by_ref.setdefault(n["ref"], []).append(n["pin"])
        if not by_ref:
            continue
        if net["name"].endswith(".NC") and len(by_ref) == 1:
            continue
        rows.append((net["name"], by_ref))
    rows.sort(key=lambda r: (r[0] in ("GND",) , r[0]))
    row_h = 34
    width = 1180
    height = 48 + row_h * max(len(rows), 1)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="100%" style="background:#11160f">',
        '<style>text{font-family:ui-monospace,Menlo,monospace;font-size:12px}</style>',
        '<text x="16" y="22" fill="#8fad7a">Netlist schematic — pin connections from default.net</text>',
    ]
    y = 44
    for name, by_ref in rows:
        color = "#6ee7a0"
        if name in ("GND",):
            color = "#c4a574"
        elif name in ("VBUS", "3V3", "VIN"):
            color = "#e07a3d"
        elif "USB" in name:
            color = "#8cb4ff"
        parts.append(f'<text x="16" y="{y}" fill="{color}" font-weight="700">{html.escape(name)}</text>')
        x = 140
        for ref, pins in sorted(by_ref.items()):
            label = f"{ref}.{','.join(pins)}"
            tw = 8 * len(label) + 16
            if x + tw > width - 12:
                y += row_h
                x = 140
                height += row_h
            parts.append(
                f'<rect x="{x}" y="{y - 16}" width="{tw}" height="22" rx="4" '
                f'fill="#1c2618" stroke="{color}" stroke-width="1"/>'
            )
            parts.append(f'<text x="{x + 8}" y="{y}" fill="#e8f0e0">{html.escape(label)}</text>')
            x += tw + 8
        y += row_h
    parts[0] = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {max(height, y + 8)}" '
        f'width="100%" style="background:#11160f">'
    )
    parts.append("</svg>")
    return "\n".join(parts)


def _kicad_env() -> dict[str, str]:
    env = os.environ.copy()
    models = Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/3dmodels")
    if models.is_dir():
        env.setdefault("KICAD10_3DMODEL_DIR", str(models))
        env.setdefault("KICAD_3DMODEL_DIR", str(models))
    return env


def _run(cmd: list[str]) -> dict:
    proc = subprocess.run(cmd, capture_output=True, text=True, env=_kicad_env())
    return {
        "cmd": cmd,
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "")[-1500:],
        "stderr": (proc.stderr or "")[-1500:],
    }


def svg_cmd(cli: Path, pcb: Path, out: Path, layers: str, *, mirror: bool = False) -> list[str]:
    cmd = [
        str(cli),
        "pcb",
        "export",
        "svg",
        "--layers",
        layers,
        "--page-size-mode",
        "2",
        "--fit-page-to-board",
        "--exclude-drawing-sheet",
        "--check-zones",
        "--mode-single",
    ]
    if mirror:
        cmd.append("--mirror")
    cmd.extend(["-o", str(out), str(pcb)])
    return cmd


def _export_svg(cli: Path, pcb: Path, out: Path, layers: str, *, mirror: bool = False) -> dict:
    return _run(svg_cmd(cli, pcb, out, layers, mirror=mirror))


def _export_glb(cli: Path, pcb: Path, out: Path) -> dict:
    models = os.environ.get(
        "KICAD10_3DMODEL_DIR",
        "/Applications/KiCad/KiCad.app/Contents/SharedSupport/3dmodels",
    )
    return _run(
        [
            str(cli),
            "pcb",
            "export",
            "glb",
            "--force",
            "--subst-models",
            "--include-tracks",
            "--include-pads",
            "--include-zones",
            "--include-silkscreen",
            "--include-soldermask",
            "--no-dnp",
            "-D",
            f"KICAD10_3DMODEL_DIR={models}",
            "-o",
            str(out),
            str(pcb),
        ]
    )


def _export_sch_svg(cli: Path, sch: Path, out_dir: Path) -> dict:
    return _run(
        [
            str(cli),
            "sch",
            "export",
            "svg",
            "--exclude-drawing-sheet",
            "--no-background-color",
            "-o",
            str(out_dir),
            str(sch),
        ]
    )


def render_html(
    *,
    title: str,
    board_mm: tuple[float, float],
    layers: int,
    stackup: str,
    pcb_name: str,
    zen_text: str | None,
    sch_svg: str | None,
    net_svg: str,
    front_svg: str | None,
    back_svg: str | None,
    copper_svg: str | None,
    silk_svg: str | None,
    glb_b64: str | None,
    bom_rows: list[list[str]],
    notes: list[str],
) -> str:
    def panel_svg(svg: str | None, empty: str) -> str:
        if svg:
            return f'<div class="plot">{svg}</div>'
        return f'<p class="empty">{html.escape(empty)}</p>'

    zen_block = (
        f'<pre class="zen">{html.escape(zen_text)}</pre>'
        if zen_text
        else '<p class="empty">No .zen next to the place file.</p>'
    )
    sch_block = (
        f'<div class="plot sch">{sch_svg}</div>'
        if sch_svg
        else '<p class="hint">No plotted schematic. pcb apply schematic needs KiCad-10 .kicad_sym on each IC. Netlist + .zen below.</p>'
    )
    glb_block = (
        f"""<model-viewer src="data:model/gltf-binary;base64,{glb_b64}"
          camera-controls touch-action="pan-y" shadow-intensity="1"
          environment-image="neutral" exposure="0.9"
          style="width:100%;height:min(72vh,720px);background:#0b0e0c">
        </model-viewer>
        <p class="hint">Drag to orbit. Missing STEP models (USB-C / ESP32-C6-MINI land) show as empty pads.</p>"""
        if glb_b64
        else '<p class="empty">GLB export failed. 2D copper still reviews routing.</p>'
    )
    bom_html = ""
    if bom_rows:
        head, *body = bom_rows
        th = "".join(f"<th>{html.escape(c)}</th>" for c in head)
        trs = []
        for row in body:
            tds = "".join(f"<td>{html.escape(c)}</td>" for c in row)
            trs.append(f"<tr>{tds}</tr>")
        bom_html = f"<table><thead><tr>{th}</tr></thead><tbody>{''.join(trs)}</tbody></table>"
    else:
        bom_html = '<p class="empty">No fab/bom.csv yet. Run pcb-space fab first.</p>'
    notes_html = "".join(f"<li>{html.escape(n)}</li>" for n in notes) or "<li>No extra notes.</li>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{html.escape(title)} — pcb-space review</title>
<script type="module" src="https://ajax.googleapis.com/ajax/libs/model-viewer/4.0.0/model-viewer.min.js"></script>
<style>
  :root {{
    --bg: #10140f;
    --panel: #181e16;
    --ink: #e7eee2;
    --muted: #8ea382;
    --line: #2a3626;
    --accent: #d4893a;
    --ok: #6ee7a0;
  }}
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; background: var(--bg); color: var(--ink);
    font: 15px/1.45 ui-sans-serif, system-ui, sans-serif; }}
  header {{
    padding: 18px 22px 10px;
    border-bottom: 1px solid var(--line);
    display: flex; justify-content: space-between; gap: 16px; flex-wrap: wrap;
  }}
  header h1 {{ margin: 0; font-size: 20px; letter-spacing: .02em; }}
  header p {{ margin: 4px 0 0; color: var(--muted); }}
  .meta {{ color: var(--muted); font-family: ui-monospace, Menlo, monospace; font-size: 12px; }}
  nav {{
    display: flex; gap: 6px; padding: 10px 22px; position: sticky; top: 0;
    background: #10140fee; border-bottom: 1px solid var(--line); z-index: 2;
  }}
  nav button {{
    background: transparent; color: var(--muted); border: 1px solid var(--line);
    border-radius: 999px; padding: 6px 14px; cursor: pointer; font: inherit;
  }}
  nav button[aria-selected="true"] {{
    color: var(--bg); background: var(--accent); border-color: var(--accent);
  }}
  section {{ display: none; padding: 18px 22px 40px; }}
  section.active {{ display: block; }}
  .split {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
  @media (max-width: 980px) {{ .split {{ grid-template-columns: 1fr; }} }}
  .plot {{
    background: #0b0e0c; border: 1px solid var(--line); border-radius: 10px;
    overflow: auto; max-height: 78vh; padding: 8px;
  }}
  .plot svg {{ display: block; width: 100%; height: auto; }}
  .zen {{
    background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
    padding: 14px; overflow: auto; max-height: 78vh; font: 12px/1.4 ui-monospace, Menlo, monospace;
    white-space: pre; color: #d5e4cc;
  }}
  .hint, .empty {{ color: var(--muted); }}
  table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
  th, td {{ border-bottom: 1px solid var(--line); text-align: left; padding: 6px 8px;
    font-family: ui-monospace, Menlo, monospace; }}
  th {{ color: var(--accent); font-weight: 600; }}
  ul {{ color: var(--muted); }}
</style>
</head>
<body>
<header>
  <div>
    <h1>{html.escape(title)}</h1>
    <p>Schematic · copper · 3D — KiCad exports, one page. Do not upload from here.</p>
  </div>
  <div class="meta">
    {board_mm[0]:g}×{board_mm[1]:g} mm · {layers}L · {html.escape(stackup)}<br/>
    {html.escape(pcb_name)}
  </div>
</header>
<nav>
  <button data-tab="sch" aria-selected="true">Schematic</button>
  <button data-tab="front">Front copper</button>
  <button data-tab="silk">Silkscreen</button>
  <button data-tab="back">Back copper</button>
  <button data-tab="both">Both layers</button>
  <button data-tab="three">3D</button>
  <button data-tab="bom">BOM</button>
</nav>
<section id="sch" class="active">
  {sch_block}
  <div class="split" style="margin-top:16px">
    <div>{zen_block}</div>
    <div class="plot">{net_svg}</div>
  </div>
</section>
<section id="front">{panel_svg(front_svg, "Front SVG missing — kicad-cli pcb export svg failed.")}</section>
<section id="silk">{panel_svg(silk_svg, "Silk SVG missing.")}</section>
<section id="back">{panel_svg(back_svg, "Back SVG missing.")}</section>
<section id="both">{panel_svg(copper_svg, "Combined copper SVG missing.")}</section>
<section id="three">{glb_block}</section>
<section id="bom">
  {bom_html}
  <h3>Notes</h3>
  <ul>{notes_html}</ul>
</section>
<script>
  const tabs = document.querySelectorAll("nav button");
  const sections = document.querySelectorAll("section");
  tabs.forEach(btn => btn.addEventListener("click", () => {{
    tabs.forEach(b => b.setAttribute("aria-selected", b === btn));
    sections.forEach(s => s.classList.toggle("active", s.id === btn.dataset.tab));
  }}));
</script>
</body>
</html>
"""


def review_job(
    job: CompiledJob,
    pcb: Path,
    *,
    place: Path | None = None,
    out_dir: Path | None = None,
    open_html: bool = True,
) -> dict:
    pcb = Path(pcb)
    place = Path(place) if place else pcb
    out_dir = Path(out_dir) if out_dir else _default_review_dir(pcb)
    out_dir.mkdir(parents=True, exist_ok=True)
    steps: list[dict] = []
    result: dict = {
        "review": str(out_dir),
        "html": str(out_dir / "index.html"),
        "pcb": str(pcb),
        "steps": steps,
        "error": None,
    }

    zen_path = find_zen(place, pcb)
    net_path = find_netlist(pcb)
    sch_path = find_schematic(place, pcb)
    bom_path = find_bom(pcb)
    result["zen"] = str(zen_path) if zen_path else None
    result["net"] = str(net_path) if net_path else None

    zen_text = zen_path.read_text() if zen_path else None
    comps, nets = parse_netlist(net_path.read_text()) if net_path else ([], [])
    net_svg = schematic_svg(nets) if nets else "<p class='empty'>No default.net</p>"

    cli = kicad_cli()
    front = out_dir / "front.svg"
    back = out_dir / "back.svg"
    copper = out_dir / "copper.svg"
    glb = out_dir / "board.glb"
    sch_svg_text = None

    if not cli.exists() and shutil.which(str(cli)) is None:
        result["error"] = f"kicad-cli not found ({cli})"
    else:
        if zen_path:
            generated, zsteps = export_zener_schematic(zen_path, out_dir, cli)
            steps.extend(zsteps)
            if generated:
                sch_path = generated
        result["schematic"] = str(sch_path) if sch_path else None
        plot = out_dir / "silk.kicad_pcb"
        silk_rep = silk_job(job, pcb, out=plot, backup=False)
        result["silk"] = silk_rep.get("silk")
        plot_pcb = Path(silk_rep["pcb"])
        silk_svg_path = out_dir / "silk.svg"
        steps.append(_export_svg(cli, plot_pcb, front, "F.Cu,F.SilkS,Edge.Cuts"))
        steps.append(_export_svg(cli, plot_pcb, silk_svg_path, "F.SilkS,Edge.Cuts"))
        steps.append(_export_svg(cli, plot_pcb, back, "B.Cu,B.SilkS,Edge.Cuts", mirror=True))
        steps.append(_export_svg(cli, plot_pcb, copper, "F.Cu,B.Cu,Edge.Cuts"))
        steps.append(_export_glb(cli, pcb, glb))
        sch_dir = out_dir / "sch"
        if sch_path and not list(sch_dir.glob("*.svg")):
            sch_dir.mkdir(exist_ok=True)
            steps.append(_export_sch_svg(cli, sch_path, sch_dir))
        svgs = sorted(sch_dir.glob("*.svg")) if sch_dir.exists() else []
        if svgs:
            sch_svg_text = svgs[0].read_text(errors="replace")

    def _svg(p: Path) -> str | None:
        return p.read_text(errors="replace") if p.exists() and p.stat().st_size > 80 else None

    glb_b64 = None
    if glb.exists() and glb.stat().st_size > 100:
        glb_b64 = base64.b64encode(glb.read_bytes()).decode("ascii")
        result["glb_bytes"] = glb.stat().st_size

    bom_rows: list[list[str]] = []
    if bom_path:
        for line in bom_path.read_text().splitlines():
            if line.strip():
                bom_rows.append(line.split(","))

    notes = [
        f"{len(comps)} components, {len(nets)} nets" if comps else "Netlist not found",
        "3D uses kicad-cli pcb export glb (tracks, pads, zones, silk, mask).",
        "USB-C / ESP32-C6-MINI STEP may be missing from the KiCad 3D library.",
        "Schematic is pcb apply schematic → kicad-cli sch export svg/pdf.",
        "Silkscreen refs are legalized (size from courtyard, slots off the body) before plotting.",
        "Do not upload Gerbers from this page.",
    ]
    if any(s.get("returncode") not in (0, None) for s in steps):
        notes.append("One or more kicad-cli export steps returned non-zero — see report.json.")

    html_text = render_html(
        title=place.stem if place.suffix else pcb.stem,
        board_mm=job.board_size_mm,
        layers=job.layers,
        stackup=job.stackup,
        pcb_name=str(pcb),
        zen_text=zen_text,
        sch_svg=sch_svg_text,
        net_svg=net_svg,
        front_svg=_svg(front),
        back_svg=_svg(back),
        copper_svg=_svg(copper),
        silk_svg=_svg(out_dir / "silk.svg"),
        glb_b64=glb_b64,
        bom_rows=bom_rows,
        notes=notes,
    )
    html_path = out_dir / "index.html"
    html_path.write_text(html_text)
    (out_dir / "report.json").write_text(json.dumps(result, indent=2, default=str) + "\n")

    if open_html:
        webbrowser.open(html_path.as_uri())
        result["opened"] = True
    return result
