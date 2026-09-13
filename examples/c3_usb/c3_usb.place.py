# USB-C on the east edge, ESP32 antenna on the west. 40×30 mm fits the
# 13.2×16.6 mm module body (RF keep-out is Keepout ANTENNA, not courtyard).
Board(
    width=40,
    height=30,
    layers=2,
    stackup="jlcpcb_2l_1oz",
    pcb="layout/c3_usb/layout.kicad_pcb",
)

Place(
    "J1",
    position="absolute",
    left=0,
    right=0,
    bottom=0,
    margin_left="auto",
    margin_right="auto",
    rotate=0,
    locked=True,
    reason="USB-C at south edge (rot 0 so KRT pad AABBs match the land)",
)

Place(
    "U1",
    position="absolute",
    left=1,
    top=1,
    rotate=90,
    locked=True,
    reason="ESP32-C3-MINI antenna at west, north of USB-C",
)

Keepout(
    "ANTENNA",
    position="absolute",
    left=0,
    top=0,
    width=1,
    height=16,
)

NetReq("USB_DP", "USB_DN", kind="usb_hs", z_diff_ohm=90, pair=True)
NetReq("VBUS", "3V3", "GND", kind="power", volts=3.3, amps=0.5)
NetReq("EN", "BOOT", "LED", "LED_A", "CC1", "CC2", kind="digital")
