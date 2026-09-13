# Forma Pod — mechanical locks + electrical intent.
# CSS names for edges and keepouts. at=(x, y) is the CAD aperture (KiCad origin).

Board(
    width=52,
    height=30,
    layers=4,
    stackup="jlcpcb_4l_1oz",
    pcb="layout/forma_pod/layout.kicad_pcb",
    planes=[("AGND", "In1.Cu"), ("DGND", "In2.Cu")],
)

# Enclosure CAD numbered these origins. Auto-place must not move them.
Place("U26", at=(47.2, 10.0), rotate=90, locked=True, reason="USB-C at pod end")
Place("U27", at=(5.0, 4.8), locked=True, reason="JST battery")
Place("U28", at=(26.0, 3.4), locked=True, reason="FFC to garment")
Place("U32", at=(26.0, 11.5), side="B", locked=True, reason="PPG optical window")
Place("NT1", at=(26.0, 14.8), locked=True, reason="AGND/DGND star")

# Same boxes as before, written as CSS.
Keepout(
    "ANTENNA",
    position="absolute",
    bottom=0,
    left=0,
    right=0,
    width=16,
    height=2.8,
    margin_left="auto",
    margin_right="auto",
)
Keepout(
    "PPG_WINDOW",
    position="absolute",
    top=9,
    left=0,
    right=0,
    width=5,
    height=5,
    margin_left="auto",
    margin_right="auto",
)

NetReq("USB_DP", "USB_DN", kind="usb_hs", z_diff_ohm=90, pair=True)
NetReq("VBAT", "VBUS", "3V3", "5V_A", "1V8", "DGND", "AGND", kind="power", volts=3.3, amps=0.25)
NetReq(
    "CH[1-9]*",
    "SRB",
    "BIAS*",
    "U1.VCAP*",
    "U2.VCAP*",
    "U1.VREFP",
    "U2.VREFP",
    kind="analog",
    max_mm=18,
    vias=False,
    keep_clear_of="BOOST.BOOST_SW",
    keep_clear_mm=0.5,
)
NetReq("ADS_CLK", "ADS_START", "ADS_SPI_CLK", kind="clock", match_mm=2.0)
NetReq("BOOST.BOOST_SW", kind="switch_node", vias=False)
NetReq("BOOST.BOOST_FB", kind="analog", vias=False)
