from pathlib import Path

from pcb_space.sch_emit import emit_schematic

NET = """(export (version "E")
  (components
    (comp (ref "U1")
      (value "IC")
      (footprint "SOIC")
      (property (name "value") (value "DRV"))
    )
    (comp (ref "R1")
      (value "10k")
      (footprint "R_0603")
      (property (name "value") (value "10k"))
    )
    (comp (ref "C1")
      (value "100n")
      (footprint "C_0603")
      (property (name "description") (value "100nF 50V"))
    )
  )
  (nets
    (net (code "1") (name "SPI_CLK")
      (node (ref "U1") (pin "1"))
      (node (ref "R1") (pin "1"))
    )
    (net (code "2") (name "GND")
      (node (ref "U1") (pin "2"))
      (node (ref "R1") (pin "2"))
      (node (ref "C1") (pin "2"))
    )
    (net (code "3") (name "+3V3")
      (node (ref "U1") (pin "3"))
      (node (ref "C1") (pin "1"))
    )
  )
)
"""


def test_emit_has_parts_labels_and_power_hats():
    sch = emit_schematic(NET, title="t")
    assert sch.startswith("(kicad_sch")
    assert sch.count("(") == sch.count(")")
    assert '(lib_id "U1")' in sch or '(lib_id "IC")' in sch
    assert '(property "Reference" "U1"' in sch
    assert '(property "Reference" "R1"' in sch
    assert '(property "Reference" "C1"' in sch
    assert '(label "SPI_CLK"' in sch
    assert '(lib_id "GND")' in sch
    assert '(lib_id "VCC")' in sch
    assert '(property "Value" "+3V3"' in sch
    assert '(property "Value" "GND"' in sch
    assert "pcb apply" not in sch
    assert '(generator "pcb-space")' in sch


def test_emit_no_global_arrows():
    sch = emit_schematic(NET, title="t")
    assert "global_label" not in sch


def test_emit_uses_datasheet_pin_names_inside_the_box():
    sch = emit_schematic(
        NET,
        title="t",
        pin_maps=[("IC", {"1": "IN1", "2": "GND", "3": "VCC"})],
    )
    assert '(name "IN1"' in sch
    assert '(number "1"' in sch
    assert '(name "GND"' in sch
    assert '(pin_numbers (hide no))' in sch


def test_emit_renames_kicad_sym_from_zen(tmp_path: Path):
    pkg = tmp_path / "components" / "IC"
    pkg.mkdir(parents=True)
    (pkg / "IC.zen").write_text(
        'Component(name="IC", symbol=Symbol(name="IC", definition=[("IN1", ["1"]), ("GND", ["2"])]), '
        'footprint=File("x.kicad_mod"), pins={"IN1": IN1, "GND": GND})\n'
        "IN1 = io(Net())\nGND = io(Ground())\n"
    )
    (pkg / "IC.kicad_sym").write_text(
        '(kicad_symbol_lib (version 20211014) (generator t)\n'
        '  (symbol "IC"\n'
        '    (pin unspecified line (at -5 0 0) (length 2.54)\n'
        '      (name "RSVD") (number "1"))\n'
        '    (pin unspecified line (at 5 0 180) (length 2.54)\n'
        '      (name "GND") (number "2"))\n'
        '  )\n)\n'
    )
    sch = emit_schematic(NET, title="t", components=tmp_path / "components")
    assert '(name "IN1"' in sch
    assert '(name "RSVD"' not in sch
    assert '(lib_id "IC")' in sch


def test_emit_one_hat_per_part_power_net():
    sch = emit_schematic(NET, title="t")
    # U1, R1, C1 each get one GND hat.
    assert sch.count('(lib_id "GND")') == 3
    assert sch.count('(lib_id "VCC")') == 2  # U1 and C1
