import pytest

from pcb_space.compile import compile_design
from pcb_space.css import Rect, origin_from_border, resolve_rect, rotate_local_bounds
from pcb_space.language import Board, Keepout, Place, Region, load_place_file, reset
from pcb_space.layout import resolve_keepout, resolve_place, resolve_regions
from pcb_space.model import BoardSpec


def test_margin_auto_centers_horizontally():
    reset()
    Board(width=52, height=30)
    ko = Keepout(
        "ANTENNA",
        bottom=0,
        left=0,
        right=0,
        width=16,
        height=2.8,
        margin_left="auto",
        margin_right="auto",
    )
    board = BoardSpec(size_mm=(52, 30))
    box = resolve_keepout(ko, board)
    assert box == pytest.approx((18.0, 27.2, 34.0, 30.0))


def test_ppg_window_css_matches_old_box():
    reset()
    Board(width=52, height=30)
    ko = Keepout(
        "PPG_WINDOW",
        top=9,
        left=0,
        right=0,
        width=5,
        height=5,
        margin_left="auto",
        margin_right="auto",
    )
    box = resolve_keepout(ko, BoardSpec(size_mm=(52, 30)))
    assert box == pytest.approx((23.5, 9.0, 28.5, 14.0))


def test_right_zero_flush_to_east_edge():
    from pcb_space.css import BoxStyle

    cb = Rect(0, 0, 20, 10)
    st = BoxStyle(position="absolute", right=0, top=0, bottom=0, margin_top="auto", margin_bottom="auto")
    border = resolve_rect(cb, st, intrinsic_w=2, intrinsic_h=2, who="J1")
    assert border.x1 == pytest.approx(20.0)
    assert border.x0 == pytest.approx(18.0)
    assert border.y0 == pytest.approx(4.0)
    assert border.y1 == pytest.approx(6.0)


def test_translate_y_centers_like_web_css():
    from pcb_space.css import BoxStyle

    cb = Rect(0, 0, 52, 30)
    st = BoxStyle(
        position="absolute",
        right=0,
        top="50%",
        translate_y="-50%",
    )
    border = resolve_rect(cb, st, intrinsic_w=10, intrinsic_h=8, who="U26")
    assert border.x1 == pytest.approx(52.0)
    # top 50% of 30 = 15, then translateY(-50% of 8) = -4 → top at 11, height 8 → 11–19
    assert border.y0 == pytest.approx(11.0)
    assert border.y1 == pytest.approx(19.0)


def test_style_string_is_css():
    reset()
    Board(width=20, height=10)
    p = Place(
        "J1",
        style="position:absolute; right:0; top:50%; transform: translateY(-50%) rotate(90deg)",
        locked=True,
        reason="usb",
    )
    assert p.position == "absolute"
    assert p.right == "0" or p.right == 0 or str(p.right) == "0"
    assert p.rot == 90
    assert p.translate_y in ("-50%", "-50 %") or str(p.translate_y).startswith("-50")


def test_z_index_is_rejected():
    reset()
    Board(width=10, height=10)
    with pytest.raises(ValueError, match="side="):
        Place("U1", z_index=1, left=0, top=0, locked=True)


def test_flex_is_rejected():
    reset()
    Board(width=10, height=10)
    with pytest.raises(ValueError, match="not a placer"):
        Place("U1", display="flex", left=0, top=0, locked=True)


def test_px_is_rejected():
    reset()
    Board(width=10, height=10)
    with pytest.raises(ValueError, match="millimetres"):
        Place("U1", left="10px", top=0, locked=True)


def test_at_and_css_conflict():
    reset()
    Board(width=10, height=10)
    with pytest.raises(ValueError, match="not both"):
        Place("U1", at=(1, 1), right=0, locked=True)


def test_kicad_90deg_origin_from_courtyard():
    # USB-C-like courtyard, KiCad rot 90 (negated-angle convention).
    local = (-5.32, -5.27, 5.32, 4.15)
    ox0, oy0, ox1, oy1 = rotate_local_bounds(*local, 90)
    border = Rect(52 - (ox1 - ox0), 10, 52, 10 + (oy1 - oy0))
    origin = origin_from_border(border, local, 90)
    # Courtyard right edge on x=52.
    assert origin[0] + ox1 == pytest.approx(52.0)


def test_forma_pod_keepouts_compile_to_old_boxes():
    from pathlib import Path

    job = compile_design(load_place_file(Path(__file__).resolve().parents[1] / "examples" / "forma_pod.place.py"))
    by = {k.name: k.box for k in job.keepouts}
    assert by["ANTENNA"] == pytest.approx((18.0, 27.2, 34.0, 30.0))
    assert by["PPG_WINDOW"] == pytest.approx((23.5, 9.0, 28.5, 14.0))


def test_region_padding_is_containing_block():
    reset()
    Board(width=52, height=30)
    r = Region("header", top=0, left=0, right=0, height=8, padding=0.5)
    board = BoardSpec(size_mm=(52, 30))
    rects = resolve_regions(board, [r])
    # content box after 0.5 mm padding
    cb = rects["header"]
    assert cb.x0 == pytest.approx(0.5)
    assert cb.y0 == pytest.approx(0.5)
    assert cb.x1 == pytest.approx(51.5)
    assert cb.y1 == pytest.approx(7.5)


def test_board_padding_shrinks_part_cb():
    reset()
    Board(width=20, height=10, padding=1)
    p = Place("J1", position="absolute", left=0, top=0, locked=True, box="origin")
    got = resolve_place(p, BoardSpec(size_mm=(20, 10), padding=(1, 1, 1, 1)), None, {})
    assert got.at[0] == pytest.approx(1.0)
    assert got.at[1] == pytest.approx(1.0)
