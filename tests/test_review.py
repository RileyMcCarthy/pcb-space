from pathlib import Path

from pcb_space.review import (
    crop_svg_to_content,
    kicad10_box_symbol,
    parse_netlist,
    parse_symbol_ports,
    render_html,
    rewrite_definition_symbols,
    schematic_svg,
    svg_cmd,
)


ROOT = Path(__file__).resolve().parents[1]
NET = ROOT / "examples" / "c3_usb" / "layout" / "c3_usb" / "default.net"


def test_parse_c3_usb_netlist():
    comps, nets = parse_netlist(NET.read_text())
    refs = {c["ref"] for c in comps}
    assert "J1" in refs
    assert "U1" in refs
    names = {n["name"] for n in nets}
    assert "USB_DP" in names
    assert "VBUS" in names
    usb = next(n for n in nets if n["name"] == "USB_DP")
    usb_refs = {x["ref"] for x in usb["nodes"]}
    assert usb_refs >= {"J1", "U1", "U3"}


def test_schematic_svg_lists_usb_pins():
    _comps, nets = parse_netlist(NET.read_text())
    svg = schematic_svg(nets)
    assert "USB_DP" in svg
    assert "J1." in svg
    assert svg.strip().startswith("<svg")


def test_rewrite_definition_symbols_points_at_kicad_sym(tmp_path: Path):
    pkg = tmp_path / "HRO" / "USB"
    pkg.mkdir(parents=True)
    zen = pkg / "part.zen"
    zen.write_text(
        'Component(\n'
        '    name = "USB",\n'
        '    symbol = Symbol(\n'
        '        name = "USB",\n'
        '        definition = [\n'
        '            ("GND", ["A1", "A12"]),\n'
        '            ("VBUS", ["A4"]),\n'
        '        ],\n'
        '    ),\n'
        '    prefix = "J",\n'
        ')\n'
    )
    changed = rewrite_definition_symbols(tmp_path)
    assert changed
    text = zen.read_text()
    assert 'Symbol("./pcbspace.kicad_sym")' in text
    assert "definition" not in text
    sym = (pkg / "pcbspace.kicad_sym").read_text()
    assert "(version 20251024)" in sym
    assert '(name "GND"' in sym
    assert '(name "VBUS"' in sym


def test_box_symbol_uses_port_names():
    name, ports = parse_symbol_ports(
        '(name = "IC", definition = [("P3V3", ["3"]), ("GND", ["1", "2"])])'
    )
    assert name == "IC"
    assert ("P3V3", "3") in ports
    svg = kicad10_box_symbol(name, ports)
    assert "P3V3" in svg


def test_mirror_flag_is_not_the_output_path():
    cmd = svg_cmd(Path("kicad-cli"), Path("a.kicad_pcb"), Path("back.svg"), "B.Cu", mirror=True)
    assert cmd[cmd.index("-o") + 1] == "back.svg"
    assert "--mirror" in cmd
    assert cmd.index("--mirror") < cmd.index("-o")


def test_crop_svg_sets_pixel_size_and_viewbox():
    svg = (
        '<svg width="840mm" height="594mm" viewBox="0 0 840 594">'
        '<path d="M 100 80 L 200 80 L 200 180 L 100 180 Z"/>'
        '<text x="120.0" y="90.0">SPI_CLK</text>'
        "</svg>"
    )
    out = crop_svg_to_content(svg, pad_mm=10, px_per_mm=10)
    assert 'viewBox="90.000 70.000' in out
    assert "px" in out
    assert "840mm" not in out.split("viewBox")[0]


def test_html_schematic_plot_does_not_shrink_svg():
    page = render_html(
        title="c3_usb",
        board_mm=(40.0, 30.0),
        layers=2,
        stackup="jlcpcb_2l_1oz",
        pcb_name="layout.kicad_pcb",
        zen_text=None,
        sch_svg="<svg></svg>",
        net_svg="<svg></svg>",
        front_svg=None,
        back_svg=None,
        copper_svg=None,
        silk_svg=None,
        glb_b64=None,
        bom_rows=[],
        notes=[],
    )
    assert ".plot.sch svg" in page
    assert "max-width: none" in page


def test_html_has_review_tabs():
    page = render_html(
        title="c3_usb",
        board_mm=(40.0, 30.0),
        layers=2,
        stackup="jlcpcb_2l_1oz",
        pcb_name="layout.kicad_pcb",
        zen_text="Board(name = \"c3_usb\")",
        sch_svg=None,
        net_svg="<svg></svg>",
        front_svg="<svg id='front'></svg>",
        back_svg=None,
        copper_svg=None,
        silk_svg=None,
        glb_b64=None,
        bom_rows=[["Comment", "Designator"], ["x", "J1"]],
        notes=["test"],
    )
    assert 'data-tab="sch"' in page
    assert 'data-tab="front"' in page
    assert 'data-tab="three"' in page
    assert "c3_usb" in page
    assert "J1" in page
