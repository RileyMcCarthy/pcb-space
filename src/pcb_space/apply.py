"""Write compiled geometry into a KiCad board: locked poses, net classes, keepouts, dru."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from .compile import CompiledJob
from .sexp import board_footprint_spans, footprint_reference, matching_paren, new_uuid


def apply_job(job: CompiledJob, pcb_path: Path, backup: bool = True) -> dict:
    pcb_path = Path(pcb_path)
    if not pcb_path.exists():
        raise FileNotFoundError(pcb_path)
    if backup:
        bak = pcb_path.with_suffix(pcb_path.suffix + ".bak-pcbspace")
        shutil.copy2(pcb_path, bak)

    text = pcb_path.read_text()
    placed, missing = _apply_places(text, job)
    text = placed
    text = _apply_outline(text, job)
    text = _apply_keepouts(text, job)
    pcb_path.write_text(text)

    pro_path = pcb_path.with_suffix(".kicad_pro")
    if pro_path.exists():
        _apply_pro(pro_path, job)
    dru_path = pcb_path.with_suffix(".kicad_dru")
    dru_path.write_text(_render_dru(job))

    return {
        "pcb": str(pcb_path),
        "placed": [p.ref for p in job.places if p.ref not in missing],
        "missing": missing,
        "classes": [c.name for c in job.classes],
        "dru": str(dru_path),
    }


def _apply_places(text: str, job: CompiledJob) -> tuple[str, list[str]]:
    by_ref = {p.ref: p for p in job.places}
    found: set[str] = set()
    spans = board_footprint_spans(text)
    pieces = []
    last = 0
    for start, end in spans:
        block = text[start:end]
        ref = footprint_reference(block)
        if ref and ref in by_ref:
            found.add(ref)
            block = _rewrite_footprint(block, by_ref[ref])
        pieces.append(text[last:start])
        pieces.append(block)
        last = end
    pieces.append(text[last:])
    missing = [p.ref for p in job.places if p.ref not in found]
    return "".join(pieces), missing


def _rewrite_footprint(block: str, place) -> str:
    layer = "F.Cu" if place.side == "F" else "B.Cu"
    at = f"(at {place.at[0]:.4f} {place.at[1]:.4f} {place.rot:g})"
    block, n = re.subn(
        r"\n\t\t\(at [0-9.+-]+ [0-9.+-]+(?: [0-9.+-]+)?\)",
        f"\n\t\t{at}",
        block,
        count=1,
    )
    if n == 0:
        block = re.sub(r"\(at [0-9.+-]+ [0-9.+-]+(?: [0-9.+-]+)?\)", at, block, count=1)
    block = re.sub(
        r'\(layer "(F|B)\.Cu"\)',
        f'(layer "{layer}")',
        block,
        count=1,
    )
    if place.locked:
        if re.search(r"\(locked\s+", block) is None:
            block = re.sub(
                r"(\n\t\t\(at [^\n]+\n)",
                r"\1\t\t(locked yes)\n",
                block,
                count=1,
            )
        else:
            block = re.sub(r"\(locked\s+(yes|no)\)", "(locked yes)", block, count=1)
        # KiCad 8+ also encodes lock on attr.
        block = re.sub(r"\(attr smd\)", "(attr smd locked)", block, count=1)
        block = re.sub(r"\(attr through_hole\)", "(attr through_hole locked)", block, count=1)
    return block


def _apply_outline(text: str, job: CompiledJob) -> str:
    w, h = job.board_size_mm
    # Replace the first Edge.Cuts gr_rect if present.
    def repl(m):
        return (
            f"{m.group(1)}(start 0 0)\n"
            f"\t\t(end {w:g} {h:g})\n"
            f"\t\t(stroke (width 0.05) (type default))\n"
            f"\t\t(fill none)\n"
            f'\t\t(layer "Edge.Cuts")'
        )

    new, n = re.subn(
        r'(\(gr_rect\n\t\t)\(start [^\n]+\)\n\t\t\(end [^\n]+\)\n\t\t\(stroke [^\n]+\n\t\t\(fill [^\n]+\n\t\t\(layer "Edge.Cuts"\)',
        repl,
        text,
        count=1,
    )
    return new if n else text


def _apply_keepouts(text: str, job: CompiledJob) -> str:
    for ko in job.keepouts:
        text = _drop_named_zone(text, ko.name)
        x0, y0, x1, y1 = ko.box
        tracks = "not_allowed" if "copper" in ko.no or "track" in ko.no else "allowed"
        vias = "not_allowed" if "via" in ko.no else "allowed"
        pour = "not_allowed" if "copper" in ko.no else "allowed"
        zone = f'''	(zone
		(net 0)
		(net_name "")
		(layers "F&B.Cu" "In1.Cu" "In2.Cu")
		(uuid "{new_uuid()}")
		(name "{ko.name}")
		(hatch edge 0.5)
		(keepout
			(tracks {tracks})
			(vias {vias})
			(pads allowed)
			(copperpour {pour})
			(footprints allowed)
		)
		(polygon
			(pts
				(xy {x0:.2f} {y0:.2f})
				(xy {x1:.2f} {y0:.2f})
				(xy {x1:.2f} {y1:.2f})
				(xy {x0:.2f} {y1:.2f})
			)
		)
	)
'''
        if not text.rstrip().endswith(")"):
            raise ValueError("board file does not end with )")
        stripped = text.rstrip()
        text = stripped[:-1] + zone + ")\n"
    return text


def _drop_named_zone(text: str, name: str) -> str:
    start = 0
    while True:
        j = text.find("\n\t(zone", start)
        if j < 0:
            return text
        open_at = text.find("(", j)
        end = matching_paren(text, open_at)
        block = text[open_at : end + 1]
        if f'(name "{name}")' in block:
            return text[:j] + text[end + 1 :]
        start = end + 1


def _apply_pro(pro_path: Path, job: CompiledJob) -> None:
    pro = json.loads(pro_path.read_text())
    ns = pro.setdefault("net_settings", {})
    existing = {c.get("name"): c for c in ns.get("classes", []) if c.get("name")}
    for cls in job.classes:
        row = existing.get(
            cls.name,
            {
                "name": cls.name,
                "pcb_color": "rgba(0, 0, 0, 0.000)",
                "schematic_color": "rgba(0, 0, 0, 0.000)",
                "priority": 8,
                "bus_width": 12,
                "wire_width": 6,
                "line_style": 0,
                "tuning_profile": "",
            },
        )
        row["clearance"] = cls.clearance_mm
        row["track_width"] = cls.track_width_mm
        row["via_diameter"] = cls.via_diameter_mm
        row["via_drill"] = cls.via_drill_mm
        if cls.diff_pair_gap_mm is not None:
            row["diff_pair_gap"] = cls.diff_pair_gap_mm
            row["diff_pair_width"] = cls.diff_pair_width_mm
        existing[cls.name] = row
    order = ["Default", "Analog", "Clock", "Power", "USB", "SwitchNode"]
    classes = [existing[n] for n in order if n in existing]
    for name, row in existing.items():
        if name not in order:
            classes.append(row)
    ns["classes"] = classes
    ns["netclass_patterns"] = [
        {"netclass": c.name, "pattern": p}
        for c in job.classes
        for p in c.patterns
    ]
    pro_path.write_text(json.dumps(pro, indent=2) + "\n")


def _render_dru(job: CompiledJob) -> str:
    lines = [
        "(version 1)\n",
        "# Generated by pcb-space. Do not hand-edit.\n",
    ]
    for rule in job.dru:
        lines.append(
            f'\n(rule "{rule.name}"\n'
            f"\t{rule.constraint}\n"
            f'\t(condition "{rule.condition}"))\n'
        )
    return "".join(lines)
