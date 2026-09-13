"""Locate a pcb-space project and tell packed boards from the Zener seed.

Zener (`pcb`) owns the schematic and writes the seed with
``pcb layout --no-open``. pcb-space never treats ``placed/``, ``routed/``,
or ``fab/`` as that seed.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

PACKED_DIRS = frozenset({"placed", "routed", "fab"})
_PLACE_SUFFIX = ".place.py"
_TOML_NAME = re.compile(r'(?m)^name\s*=\s*"([^"]+)"')
_TOML_PATH = re.compile(r'(?m)^path\s*=\s*"([^"]+)"')
_ZEN_LAYOUT = re.compile(r'layout_path\s*=\s*"([^"]+)"')
_BOARD_NET = re.compile(r'\(net \d+ "([^"]*)"\)')
_PAD_NET = re.compile(r'\(net "([^"]+)"\)')


def pcb_cli() -> Path:
    found = shutil.which("pcb")
    if found:
        return Path(found)
    home = Path.home() / ".local" / "bin" / "pcb"
    return home if home.exists() else Path("pcb")


def zener_build(zen: Path, root: Path) -> dict:
    """Run ``pcb build`` on a .zen. ``ok`` is False if pcb is missing."""
    import subprocess

    cli = pcb_cli()
    if not Path(cli).exists() and shutil.which("pcb") is None:
        return {"ran": False, "ok": False, "detail": "pcb (Zener) not on PATH"}
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


def has_routed_copper(text: str) -> bool:
    if "\n\t(segment" in text or "\n  (segment" in text:
        return True
    return bool(re.search(r"\n\t\(via\b", text))


def packed_reason(pcb: Path, text: str | None = None) -> str | None:
    """Why this file must not be fed to ``pcb layout``. None = allowed seed."""
    pcb = Path(pcb)
    for parent in pcb.parents:
        if parent.name in PACKED_DIRS:
            return (
                f"{pcb.name} is under {parent.name}/. "
                "pcb layout is seed-only; never run it on placed/, routed/, or fab/."
            )
    if not pcb.exists():
        return None
    body = text if text is not None else pcb.read_text()
    if has_routed_copper(body):
        return (
            f"{pcb.name} has routed copper. "
            "pcb layout would duplicate footprints."
        )
    return None


def is_leftover_pad_net(name: str) -> bool:
    """Zener unconnected pads show up as ``J1.SBU1`` — not NetReq material."""
    return "." in name


def board_net_names(text: str) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for pat in (_BOARD_NET, _PAD_NET):
        for m in pat.finditer(text):
            n = m.group(1)
            if not n or n in seen or is_leftover_pad_net(n):
                continue
            seen.add(n)
            names.append(n)
    return names


@dataclass
class Project:
    root: Path
    name: str
    zen: Path | None = None
    place: Path | None = None
    pcb_toml: Path | None = None
    seed: Path | None = None
    placed: Path | None = None
    routed: Path | None = None
    fab: Path | None = None
    review: Path | None = None
    errors: list[str] = field(default_factory=list)

    def stage(self) -> str:
        if self._exists(self.fab) and (
            (self.fab.parent / "gerbers").exists()
            or (self.fab.parent / "bom.csv").exists()
        ):
            return "fab"
        if self._exists(self.fab):
            return "fab"
        if self._exists(self.routed):
            return "routed"
        if self._exists(self.placed):
            return "placed"
        if self._exists(self.seed):
            return "seeded"
        if self.zen and self.zen.exists():
            return "schematic"
        if self.place and self.place.exists():
            return "place"
        return "empty"

    @staticmethod
    def _exists(p: Path | None) -> bool:
        return bool(p and p.exists())


def _layout_dir(root: Path, name: str, zen: Path | None) -> Path:
    if zen and zen.exists():
        m = _ZEN_LAYOUT.search(zen.read_text())
        if m:
            return (root / m.group(1)).resolve()
    return (root / "layout" / name).resolve()


def _with_stages(proj: Project) -> Project:
    layout = None
    if proj.seed:
        layout = proj.seed.parent
    elif proj.zen or proj.name:
        layout = _layout_dir(proj.root, proj.name, proj.zen)
        seed = layout / "layout.kicad_pcb"
        proj.seed = seed
    if layout is None:
        return proj
    name = "layout.kicad_pcb"
    if proj.seed:
        name = proj.seed.name
        layout = proj.seed.parent
    proj.placed = layout / "placed" / name
    proj.routed = layout / "routed" / name
    proj.fab = layout / "fab" / name
    proj.review = layout / "review" / "index.html"
    return proj


def _from_place(place: Path) -> Project:
    from .language import load_place_file

    place = place.resolve()
    root = place.parent
    name = place.name.removesuffix(_PLACE_SUFFIX)
    zen = root / f"{name}.zen"
    toml = root / "pcb.toml"
    pcb_rel = None
    try:
        design = load_place_file(place)
        pcb_rel = design.board.pcb if design.board else None
    except Exception as exc:  # noqa: BLE001 — status must still load a broken place file
        proj = Project(root=root, name=name, zen=zen if zen.exists() else None, place=place)
        proj.errors.append(f"place file: {exc}")
        if toml.exists():
            proj.pcb_toml = toml
        return _with_stages(proj)
    seed = (root / pcb_rel).resolve() if pcb_rel else None
    proj = Project(
        root=root,
        name=name,
        zen=zen if zen.exists() else None,
        place=place,
        pcb_toml=toml if toml.exists() else None,
        seed=seed,
    )
    if proj.zen is None:
        sibling = find_zen(place, seed or place)
        if sibling:
            proj.zen = sibling
    return _with_stages(proj)


def _from_zen(zen: Path) -> Project:
    zen = zen.resolve()
    root = zen.parent
    name = zen.stem
    toml = root / "pcb.toml"
    if toml.exists():
        text = toml.read_text()
        m = _TOML_NAME.search(text)
        if m:
            name = m.group(1)
    place = root / f"{name}.place.py"
    if not place.exists():
        found = list(root.glob("*.place.py"))
        place_path = found[0] if len(found) == 1 else None
    else:
        place_path = place
    if place_path:
        return _from_place(place_path)
    proj = Project(
        root=root,
        name=name,
        zen=zen,
        pcb_toml=toml if toml.exists() else None,
    )
    return _with_stages(proj)


def _from_dir(root: Path) -> Project:
    root = root.resolve()
    toml = root / "pcb.toml"
    if toml.exists():
        text = toml.read_text()
        zen_rel = _TOML_PATH.search(text)
        name_m = _TOML_NAME.search(text)
        if zen_rel:
            zen = (root / zen_rel.group(1)).resolve()
            if zen.exists():
                return _from_zen(zen)
        if name_m:
            place = root / f"{name_m.group(1)}.place.py"
            if place.exists():
                return _from_place(place)
    places = sorted(root.glob("*.place.py"))
    if len(places) == 1:
        return _from_place(places[0])
    zens = sorted(p for p in root.glob("*.zen") if p.name != "part.zen")
    if len(zens) == 1:
        return _from_zen(zens[0])
    if len(places) > 1:
        raise ValueError(
            f"{root} has {len(places)} .place.py files; pass one explicitly"
        )
    raise ValueError(f"{root} has no .place.py or .zen (run pcb-space init)")


def resolve_project(path: str | Path) -> Project:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    if path.is_file():
        if path.name.endswith(_PLACE_SUFFIX):
            return _from_place(path)
        if path.suffix == ".zen":
            return _from_zen(path)
        if path.suffix == ".kicad_pcb":
            # Walk up to the board dir (layout/<name>/…) then the project root.
            for parent in path.parents:
                try:
                    return _from_dir(parent)
                except ValueError:
                    continue
            raise ValueError(f"no pcb-space project above {path}")
        raise ValueError(f"expected .place.py, .zen, or a project directory, got {path.name}")
    return _from_dir(path)


def find_zen(place: Path, pcb: Path | None = None) -> Path | None:
    cand = Path(place)
    if cand.name.endswith(_PLACE_SUFFIX):
        sibling = cand.with_name(cand.name.removesuffix(_PLACE_SUFFIX) + ".zen")
        if sibling.exists():
            return sibling
    if cand.suffix == ".zen" and cand.exists():
        return cand
    search = [cand.parent]
    if pcb:
        search.extend([Path(pcb).parent, *Path(pcb).parents])
    for parent in search:
        zens = sorted(
            p
            for p in parent.glob("*.zen")
            if p.name != "part.zen" and "components" not in p.parts
        )
        if zens:
            return zens[0]
    return None
