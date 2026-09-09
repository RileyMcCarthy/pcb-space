"""Place-file DSL. A .place.py is ordinary Python that calls these constructors."""

from __future__ import annotations

from pathlib import Path

from .model import BoardSpec, Design, KeepoutSpec, NetReqSpec, PlaceSpec

_current: Design | None = None


def _doc() -> Design:
    global _current
    if _current is None:
        _current = Design()
    return _current


def reset() -> None:
    global _current
    _current = Design()


def Board(
    size_mm: tuple[float, float],
    layers: int = 4,
    stackup: str = "jlcpcb_4l_1oz",
    pcb: str | None = None,
    planes: list[tuple[str, str]] | None = None,
) -> BoardSpec:
    spec = BoardSpec(
        size_mm=(float(size_mm[0]), float(size_mm[1])),
        layers=int(layers),
        stackup=stackup,
        pcb=pcb,
        planes=tuple((str(n), str(l)) for n, l in (planes or ())),
    )
    _doc().board = spec
    return spec


def Place(
    ref: str,
    at: tuple[float, float],
    rot: float = 0,
    side: str = "F",
    locked: bool = False,
    reason: str = "",
) -> PlaceSpec:
    spec = PlaceSpec(
        ref=str(ref),
        at=(float(at[0]), float(at[1])),
        rot=float(rot),
        side=side.upper()[:1],
        locked=bool(locked),
        reason=reason,
    )
    _doc().places.append(spec)
    return spec


def Keepout(
    name: str,
    box: tuple[float, float, float, float],
    no: list[str] | tuple[str, ...] = ("copper", "via"),
) -> KeepoutSpec:
    x0, y0, x1, y1 = (float(x) for x in box)
    spec = KeepoutSpec(
        name=str(name),
        box=(x0, y0, x1, y1),
        no=tuple(no),
    )
    _doc().keepouts.append(spec)
    return spec


def NetReq(*nets: str, kind: str, **kwargs) -> NetReqSpec:
    if not nets:
        raise ValueError("NetReq needs at least one net or glob")
    layers = kwargs.get("layers")
    spec = NetReqSpec(
        nets=tuple(str(n) for n in nets),
        kind=str(kind),
        z_diff_ohm=kwargs.get("z_diff_ohm"),
        z_se_ohm=kwargs.get("z_se_ohm"),
        volts=kwargs.get("volts"),
        amps=kwargs.get("amps"),
        temp_rise_c=float(kwargs.get("temp_rise_c", 10)),
        max_mm=kwargs.get("max_mm"),
        match_mm=kwargs.get("match_mm"),
        pair=bool(kwargs.get("pair", False)),
        vias=kwargs.get("vias"),
        layers=tuple(layers) if layers is not None else None,
        keep_clear_of=kwargs.get("keep_clear_of"),
        keep_clear_mm=kwargs.get("keep_clear_mm"),
        autoroute=kwargs.get("autoroute"),
        class_name=kwargs.get("class_name"),
    )
    _doc().netreqs.append(spec)
    return spec


def load_place_file(path: str | Path) -> Design:
    """Execute a .place.py and return the collected design."""
    path = Path(path).resolve()
    reset()
    ns = {
        "Board": Board,
        "Place": Place,
        "Keepout": Keepout,
        "NetReq": NetReq,
        "__file__": str(path),
        "__name__": "__pcb_space__",
    }
    code = path.read_text()
    exec(compile(code, str(path), "exec"), ns, ns)  # noqa: S102 — place files are the source language
    design = _doc()
    design.source = str(path)
    if design.board is None:
        raise ValueError(f"{path} did not call Board()")
    return design
