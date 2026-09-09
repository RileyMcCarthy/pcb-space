from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BoardSpec:
    size_mm: tuple[float, float]
    layers: int = 4
    stackup: str = "jlcpcb_4l_1oz"
    pcb: str | None = None
    planes: tuple[tuple[str, str], ...] = ()


@dataclass
class PlaceSpec:
    ref: str
    at: tuple[float, float]
    rot: float = 0.0
    side: str = "F"
    locked: bool = False
    reason: str = ""


@dataclass
class KeepoutSpec:
    name: str
    box: tuple[float, float, float, float]
    no: tuple[str, ...] = ("copper", "via")


@dataclass
class NetReqSpec:
    nets: tuple[str, ...]
    kind: str
    z_diff_ohm: float | None = None
    z_se_ohm: float | None = None
    volts: float | None = None
    amps: float | None = None
    temp_rise_c: float = 10.0
    max_mm: float | None = None
    match_mm: float | None = None
    pair: bool = False
    vias: bool | None = None
    layers: tuple[str, ...] | None = None
    keep_clear_of: str | None = None
    keep_clear_mm: float | None = None
    autoroute: bool | str | None = None
    class_name: str | None = None


@dataclass
class Design:
    board: BoardSpec | None = None
    places: list[PlaceSpec] = field(default_factory=list)
    keepouts: list[KeepoutSpec] = field(default_factory=list)
    netreqs: list[NetReqSpec] = field(default_factory=list)
    source: str | None = None
