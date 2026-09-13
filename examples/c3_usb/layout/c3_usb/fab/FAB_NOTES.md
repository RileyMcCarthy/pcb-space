# Fab notes

Board 40×30 mm, 2 layer, stackup `jlcpcb_2l_1oz`.

## Fiducials

- FID1 at (36, 4) — 1 mm Cu, 2 mm mask, F.Cu
- FID2 at (36, 26) — 1 mm Cu, 2 mm mask, F.Cu
- FID3 at (4, 26) — 1 mm Cu, 2 mm mask, F.Cu
- JLCPCB Standard SMT wants 3–4 fiducials ≥ 3.35 mm from the edge. Rails (5 mm) can be added at order time.

## Via-in-pad

20 via(s) have copper fully inside an SMT pad. Order **filled + capped** vias (IPC-4761 Type VII). USB-C underpad (J1) is required; others wick solder if left open:
- J1.A4 @ (17.550, 21.800)
- J1.B8 @ (18.250, 21.800)
- J1.A5 @ (18.750, 21.800)
- J1.B7 @ (19.250, 21.800)
- J1.A6 @ (19.750, 21.800)
- J1.A7 @ (20.250, 21.800)
- J1.B6 @ (20.750, 21.800)
- J1.A8 @ (21.250, 21.800)
- J1.B5 @ (21.750, 21.800)
- J1.A9 @ (22.450, 21.800)
- U3.1 @ (22.850, 11.350)
- U1.27 @ (14.650, 1.950)
- U3.3 @ (20.950, 11.350)
- U1.26 @ (15.500, 2.000)
- U1.52 @ (17.150, 13.750)
- U1.14 @ (17.150, 11.050)
- C7.2 @ (20.300, 19.600)
- U2.5 @ (11.550, 21.200)
- U1.3 @ (9.850, 13.750)
- C1.1 @ (20.000, 7.500)

## BOM LCSC

Every BOM row has an LCSC code from SOURCE.json.

## Do not

- Upload this zip until via-in-pad and LCSC rows are accepted.
- Re-run `pcb layout` on `fab/`.
