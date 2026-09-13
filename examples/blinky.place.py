Board(width=20, height=10, layers=2, stackup="jlcpcb_2l_1oz")

# CSS absolute: flush to the east end, vertically centered.
Place(
    "J1",
    position="absolute",
    right=0,
    top=0,
    bottom=0,
    margin_top="auto",
    margin_bottom="auto",
    rotate=90,
    locked=True,
    reason="USB at board end",
)
Keepout(
    "EDGE",
    position="absolute",
    right=0,
    top=0,
    bottom=0,
    width=3,
    no=("via",),
)

NetReq("USB_DP", "USB_DN", kind="usb_hs", z_diff_ohm=90, pair=True)
NetReq("VCC", kind="power", volts=5.0, amps=0.1)
NetReq("LED", kind="digital")
