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


def test_emit_one_hat_per_part_power_net():
    sch = emit_schematic(NET, title="t")
    # U1, R1, C1 each get one GND hat.
    assert sch.count('(lib_id "GND")') == 3
    assert sch.count('(lib_id "VCC")') == 2  # U1 and C1
