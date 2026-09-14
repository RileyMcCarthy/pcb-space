from pcb_space.sch_nets import (
    annotate_sch_nets,
    is_power_net,
    parse_lib_pins,
    pin_to_net,
)

SCH = """(kicad_sch
	(version 20260306)
	(lib_symbols
		(symbol "IC"
			(property "Reference" "U"
				(at 0 0 0)
				(effects (font (size 1.27 1.27)))
			)
			(symbol "IC_0_1"
				(rectangle
					(start -2.54 2.54)
					(end 2.54 -2.54)
					(stroke (width 0.254) (type default))
					(fill (type background))
				)
			)
			(symbol "IC_1_1"
				(pin unspecified line
					(at -3.81 0 0)
					(length 2.54)
					(name "1"
						(effects (font (size 1.27 1.27)))
					)
					(number "1"
						(effects (font (size 1.27 1.27)))
					)
				)
				(pin unspecified line
					(at 3.81 0 180)
					(length 2.54)
					(name "2"
						(effects (font (size 1.27 1.27)))
					)
					(number "2"
						(effects (font (size 1.27 1.27)))
					)
				)
			)
		)
		(symbol "GND"
			(power global)
			(property "Value" "GND"
				(at 0 0 0)
				(effects (font (size 1.27 1.27)))
			)
			(symbol "GND_1_1"
				(pin power_in line
					(at 0 0 270)
					(length 0)
					(name ""
						(effects (font (size 1.27 1.27)))
					)
					(number "1"
						(effects (font (size 1.27 1.27)))
					)
				)
			)
		)
	)
	(symbol
		(lib_id "IC")
		(at 50 50 0)
		(uuid "11111111-1111-1111-1111-111111111111")
		(property "Reference" "U1"
			(at 50 50 0)
			(effects (font (size 1.27 1.27)))
		)
		(pin "1"
			(uuid "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
		)
		(pin "2"
			(uuid "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
		)
	)
	(label "SPI_CLK"
		(at 46.19 50 180)
		(effects
			(font
				(size 1.27 1.27)
			)
			(justify right)
		)
		(uuid "cccccccccccccccccccccccccccccccccccc")
	)
)
"""

NET = """(export (version "E")
  (components
    (comp (ref "U1") (value "IC") (footprint "SOIC"))
  )
  (nets
    (net (code "1") (name "SPI_CLK")
      (node (ref "U1") (pin "1"))
      (node (ref "U2") (pin "5"))
    )
    (net (code "2") (name "GND")
      (node (ref "U1") (pin "2"))
    )
  )
)
"""


def test_is_power_net():
    assert is_power_net("GND")
    assert is_power_net("+12V")
    assert is_power_net("+3V3")
    assert not is_power_net("SPI_CLK")
    assert not is_power_net("Temp1")


def test_pin_to_net_maps_ref_pin():
    from pcb_space.sch_nets import parse_netlist

    _c, nets = parse_netlist(NET)
    lookup = pin_to_net(nets)
    assert lookup[("U1", "1")] == "SPI_CLK"
    assert lookup[("U1", "2")] == "GND"


def test_annotate_replaces_on_pin_label_with_stub_and_local_label():
    out = annotate_sch_nets(SCH, NET)
    assert '(global_label "SPI_CLK"' not in out
    assert '(label "SPI_CLK"' in out
    assert "(wire" in out
    assert out.count("(wire") >= 1
    assert '(lib_id "GND")' in out
    assert '(property "Value" "GND"' in out


def test_annotate_skips_power_when_wire_already_there():
    sch = SCH.replace(
        "\t(label",
        "\t(wire\n\t\t(pts\n\t\t\t(xy 53.81 50) (xy 53.81 55)\n\t\t)\n"
        '\t\t(uuid "dddddddd-dddd-dddd-dddd-dddddddddddd")\n'
        "\t)\n"
        "\t(label",
    )
    out = annotate_sch_nets(sch, NET)
    # Pin 2 already has a wire at the connection point — do not add a GND symbol.
    assert '(lib_id "GND")' not in out
    assert '(label "SPI_CLK"' in out
    assert '(global_label' not in out


def test_one_pin_nets_are_not_labeled():
    net = """(export (version "E")
  (components
    (comp (ref "U1") (value "IC") (footprint "SOIC"))
  )
  (nets
    (net (code "1") (name "A1.D0")
      (node (ref "U1") (pin "1"))
    )
    (net (code "2") (name "GND")
      (node (ref "U1") (pin "2"))
    )
  )
)
"""
    out = annotate_sch_nets(SCH, net)
    assert '(label "A1.D0"' not in out


def test_stagger_adjacent_stubs():
    sch = SCH.replace(
        '\t\t\t\t(pin unspecified line\n'
        '\t\t\t\t\t(at 3.81 0 180)\n',
        '\t\t\t\t(pin unspecified line\n'
        '\t\t\t\t\t(at -3.81 -2.54 0)\n'
        '\t\t\t\t\t(length 2.54)\n'
        '\t\t\t\t\t(name "2"\n'
        '\t\t\t\t\t\t(effects (font (size 1.27 1.27)))\n'
        '\t\t\t\t\t)\n'
        '\t\t\t\t\t(number "2"\n'
        '\t\t\t\t\t\t(effects (font (size 1.27 1.27)))\n'
        '\t\t\t\t\t)\n'
        '\t\t\t\t)\n'
        '\t\t\t\t(pin unspecified line\n'
        '\t\t\t\t\t(at 3.81 0 180)\n',
    )
    # Both signal pins on the left: 1 at y=50, 2 at y=47.46
    net = NET.replace(
        '(node (ref "U1") (pin "2"))',
        '(node (ref "U1") (pin "2"))\n      (node (ref "U3") (pin "1"))',
    ).replace(
        '(name "GND")',
        '(name "SPI_CS")',
    )
    out = annotate_sch_nets(sch, net)
    xs = __import__("re").findall(r'\(label "SPI_[A-Z]+"\n\t\t\(at ([0-9.+-]+)', out)
    assert len(xs) == 2
    assert xs[0] != xs[1]


def test_parse_lib_pins_reads_connection_point():
    pins = parse_lib_pins(
        '(symbol "R_Small"\n'
        '\t\t\t(symbol "R_Small_1_1"\n'
        "\t\t\t\t(pin unspecified line\n"
        "\t\t\t\t\t(at -3.81 0 0)\n"
        "\t\t\t\t\t(length 2.54)\n"
        '\t\t\t\t\t(number "1"\n'
        "\t\t\t\t\t\t(effects (font (size 1.27 1.27)))\n"
        "\t\t\t\t\t)\n"
        "\t\t\t\t)\n"
        "\t\t\t)\n"
        "\t\t)\n"
    )
    assert "1" in pins
    assert pins["1"][0] == -3.81


def test_passives_are_not_labeled():
    from pcb_space.sch_nets import _is_passive

    assert _is_passive("R1")
    assert _is_passive("C12")
    assert _is_passive("L9")
    assert not _is_passive("U1")
    assert not _is_passive("A1")
    assert not _is_passive("J9")
