# c3_usb

USB-C device → 3.3 V LDO → ESP32-C3-MINI-1-N4. LED on IO10, BOOT on IO9, RST on EN. USB ESD on D+/D−.

## Schematic checks

| Check | Result |
|---|---|
| `pcb build` | **19 components, pass** |
| ESP32 USB | IO19 = D+, IO18 = D− (Espressif Table 3-1) |
| USB-C both orientations | A6/B6 → D+, A7/B7 → D−; CC Rd 5.1 kΩ |
| AP2112 pin map | 1 VIN … 5 VOUT, EN defaults to VIN |
| Body gates | ESP32 13.2×16.6, SOT-23-5, B3U 3.0×2.5, USBLC6 — **pass**. EasyEDA ESP32 land was rejected. |
| BOM MPNs | pinned on every generic (not auto-substituted) |

`pcb dfm` is a **layout** check. It fails until there is copper. Placement is step 2; routing is step 3.

## BOM (LCSC, `--fab jlcpcb`)

| Ref | MPN | LCSC | Role |
|---|---|---|---|
| J1 | TYPE-C-31-M-12 | C165948 | USB-C 16P |
| U2 | AP2112K-3.3TRG1 | C51118 | 3.3 V LDO |
| U1 | ESP32-C3-MINI-1-N4 | C2838502 | MCU |
| U3 | USBLC6-2SC6 | C2687116 | USB ESD |
| SW_* | B3U-1000P | C231329 | BOOT/RST |
| 100n 0402 | CL05B104KO5NNNC | C1525 | decoupling, JLC Basic |
| 1u 0402 | CL05A105KA5NQNC | C52923 | EN RC, JLC Basic |
| 10u 10V 0603 | CL10A106KP8NNNC | C19702 | 3V3 bulk, JLC Basic |
| 10u 16V 0603 | CL10A106KO8NQNC | C962136 | VBUS bulk |
| 1k 0402 | 0402WGF1001TCE | C11702 | LED, JLC Basic |
| 5.1k 0402 | 0402WGF5101TCE | C25905 | CC Rd, JLC Basic |
| 10k 0402 | 0402WGF1002TCE | C25744 | EN/BOOT, JLC Basic |
| D1 | KT-0603R | C2286 | LED, JLC Basic |

Zener `pcb bom` still leaves LCSC blank on some house MPNs (UniOhm / HRO / ST names). Use `SOURCE.json` `lcsc` for the JLCPCB CPL/BOM.

## Placement checks (step 2)

40×30 mm. USB-C (`J1`) locked on the **south** edge at (20.0, 25.85) r0 — rot 0 so KRT’s pad AABBs match the land (a 90° receptacle looked overlapped to the router). ESP32 (`U1`) locked at (12.25, 7.85) r90, antenna west, north of the receptacle. KiCad’s MINI-1 courtyard used to include the RF keep-out (43×32 mm, larger than the board); the land’s CrtYd is now the 13.2×16.6 mm body + 0.25 mm.

```bash
pcb-space seed c3_usb.place.py           # wraps pcb layout --no-open; seed only
pcb-space place c3_usb.place.py          # outline + CSS locks + KRT legalize
pcb-space check c3_usb.place.py --pcb layout/c3_usb/placed/layout.kicad_pcb
```

Do **not** re-run `pcb layout` (or `pcb-space seed`) on `placed/`. That is a packed board; `pcb layout` is seed-only.

| Check | Result |
|---|---|
| Unique footprints | **19** (ESD is KiCad `U3`; USB-C is `J1` via `prefix="J"`) |
| Copper | **0** segments |
| Outline | `Edge.Cuts` 0,0–40,30 from `Board` |
| Locked poses | J1 and U1 unmoved (`pcb-space check` **ok**) |
| KRT `place_seed` | 19 seated, 0 unseated, intent grade **0 errors** |
| Copper-free `check_drc` | **0** (pad-pad 0) |
| `check_assembly` | blocking **0**, courtyard_blocking **0**, pad copper off-board **0** — **buildable** |
| `check_floorplan --intent` | **PASS** (USB-C courtyard flush is the 1 budgeted oob) |

Placed board: `layout/c3_usb/placed/layout.kicad_pcb`.

## Routing checks (step 3)

```bash
pcb-space route c3_usb.place.py
```

EasyEDA’s TYPE-C-31-M-12 land had 17 overlapping pad pairs; the KiCad official `USB_C_Receptacle_HRO_TYPE-C-31-M-12` land passed body gate (8.94×7.3 vs 8.94×7.35) and `check_pads`. 2-layer 1.6 mm cannot do loosely-coupled 90 Ω USB; the compiler uses a tightly-coupled **0.10/0.10 mm** pair. USB-C 0.5 mm pitch is fanned with `qfn_fanout --escape-method underpad --allow-via-in-pad` (10 via-in-pad — fab needs filled+capped vias). Then signals, then GND pour F+B.

| Check | Result |
|---|---|
| `pcb-space check` | **ok** (J1/U1 unmoved) |
| Copper | 405 segments, 37 vias, GND zone F+B (52/52 pads) |
| `check_connected` | **ALL NETS FULLY CONNECTED** |
| `check_drc` | **0** at 0.10 mm floor |

Routed board: `layout/c3_usb/routed/layout.kicad_pcb`.

## Not yet (step 4+)

- Fiducials, silk, JLCPCB assembly CSV, via-in-pad note on the fab drawing
- Gerbers — not until the board is fab-ready
