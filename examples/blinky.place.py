Board(size_mm=(20, 10), layers=2, stackup="jlcpcb_2l_1oz")

Place("J1", at=(18.0, 5.0), rot=90, locked=True, reason="USB at board end")
Keepout("EDGE", box=(17.0, 0.0, 20.0, 10.0), no=("via",))

NetReq("USB_DP", "USB_DN", kind="usb_hs", z_diff_ohm=90, pair=True)
NetReq("VCC", kind="power", volts=5.0, amps=0.1)
NetReq("LED", kind="digital")
