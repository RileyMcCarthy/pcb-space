from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BoardSpec:
    size_mm: tuple[float, float]
    layers: int = 4
    stackup: str = "jlcpcb_4l_1oz"
    pcb: str | None = None
    planes: tuple[tuple[str, str], ...] = ()
    # CSS padding shorthand resolved to (top, right, bottom, left) mm.
    padding: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)


@dataclass
class PlaceSpec:
    ref: str
    at: tuple[float, float] | None = None
    rot: float = 0.0
    side: str = "F"
    locked: bool = False
    reason: str = ""
    position: str = "static"
    top: object | None = None
    right: object | None = None
    bottom: object | None = None
    left: object | None = None
    width: object | None = None
    height: object | None = None
    margin_top: object = 0
    margin_right: object = 0
    margin_bottom: object = 0
    margin_left: object = 0
    translate_x: object | None = None
    translate_y: object | None = None
    from_box: str = "courtyard"
    parent: str | None = None

    def has_css(self) -> bool:
        return any(
            getattr(self, k) is not None
            for k in ("top", "right", "bottom", "left", "width", "height")
        ) or self.position == "absolute"


@dataclass
class KeepoutSpec:
    name: str
    box: tuple[float, float, float, float] | None = None
    no: tuple[str, ...] = ("copper", "via")
    position: str = "absolute"
    top: object | None = None
    right: object | None = None
    bottom: object | None = None
    left: object | None = None
    width: object | None = None
    height: object | None = None
    margin_top: object = 0
    margin_right: object = 0
    margin_bottom: object = 0
    margin_left: object = 0
    parent: str | None = None

    def has_css(self) -> bool:
        return self.box is None or any(
            getattr(self, k) is not None
            for k in ("top", "right", "bottom", "left", "width", "height")
        )


@dataclass
class RegionSpec:
    """Named containing block (a div). Unlocked parts pack inside later."""

    name: str
    position: str = "absolute"
    top: object | None = None
    right: object | None = None
    bottom: object | None = None
    left: object | None = None
    width: object | None = None
    height: object | None = None
    margin_top: object = 0
    margin_right: object = 0
    margin_bottom: object = 0
    margin_left: object = 0
    padding_top: object = 0
    padding_right: object = 0
    padding_bottom: object = 0
    padding_left: object = 0
    parent: str | None = None


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
    regions: list[RegionSpec] = field(default_factory=list)
    netreqs: list[NetReqSpec] = field(default_factory=list)
    source: str | None = None
