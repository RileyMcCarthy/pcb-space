# Tiny 4-layer buck: locked IC, unlocked inductor on SW.
# CI: pcb-space place + route + fab with KRT_HOME set.

Board(
    width=40,
    height=25,
    layers=4,
    stackup="jlcpcb_4l_1oz",
    planes=[("GND", "In1.Cu"), ("+5V", "In2.Cu")],
    pcb="layout/buck_sw/layout.kicad_pcb",
)

Place(
    "U1",
    position="absolute",
    left=8,
    top=8,
    locked=True,
    reason="buck IC",
)

NetReq("SW", kind="switch_node", max_mm=6)
NetReq("+5V", kind="power", volts=5, amps=2)
NetReq("GND", kind="power", volts=0, amps=2)
NetReq("VIN", kind="power", volts=12, amps=0.5)
