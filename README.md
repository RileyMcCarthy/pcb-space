# pcb-space

Zener-style **compiler in front of KiCad** for placement and routing.

You write requirements and a few locked connector poses. The compiler turns ohms / amps / hertz into track geometry. A free engine (KiCadRoutingTools, later DeepPCB/Quilter) places unlocked parts and routes. KiCad DRC’s and writes Gerbers. The agent never has to click Pcbnew.

```
.place.py          Place() + NetReq()     (git, AI-writable)
      ↓ compile
geometry           width / gap / clearance / layers / skip-autoroute
      ↓ apply
.kicad_pcb         locked footprints, keepouts, net classes, .kicad_dru
      ↓ route
engine             KRT / DeepPCB / Quilter
      ↓ check
intent tests       “USB-C still at 47.2,10” · “USB still a pair”
```

## Why this exists

KiCad 10 already *uses* 0.20 mm traces and *checks* clearance. It will not:

- derive 0.20/0.15 mm from “USB 2.0, 90 Ω” plus a JLCPCB 4-layer stackup
- keep “USB-C at this end, this offset, for the enclosure” in git
- autoroute from a CLI an agent can call

Zener already does the schematic half (`Net`, `Module`, `pcb build`). pcb-space is the spatial half: **requirements as input, hardcoded CAD poses, autorouter meets specs.**

Analog EMG and switching nodes stay `autoroute=False` until you say otherwise. A maze that “meets 0.2 mm width” can still ruin a boost SW loop.

## Install

```bash
pip install -e ".[dev]"
```

Python 3.11+. No extra dependencies for compile / apply / check.

## Place file

```python
Board(size_mm=(52, 30), layers=4, stackup="jlcpcb_4l_1oz")

# Mechanical facts — the engine must not move these
Place("U26", at=(47.2, 10.0), rot=90, locked=True, reason="USB-C at pod end")
Place("U28", at=(26.0, 3.4), rot=0, locked=True, reason="FFC to garment")
Keepout("ANTENNA", box=(18, 27.2, 34, 30))

# Electrical intent — compiler fills in millimetres
NetReq("USB_DP", "USB_DN", kind="usb_hs", z_diff_ohm=90, pair=True)
NetReq("3V3", kind="power", volts=3.3, amps=0.25)
NetReq("CH[1-9]*", kind="analog", max_mm=18, vias=False,
       keep_clear_of="BOOST.BOOST_SW", keep_clear_mm=0.5)
NetReq("ADS_CLK", "ADS_START", "ADS_SPI_CLK", kind="clock", match_mm=2.0)
NetReq("BOOST.BOOST_SW", kind="switch_node", vias=False)
```

`Place` uses the **KiCad reference** (`U26`), not the Zener instance path.

### `NetReq` kinds

| kind | Compiles to | Autoroute |
|---|---|---|
| `usb_hs` | 90 Ω (or `z_diff_ohm`) pair geometry from the stackup | diff pair |
| `power` | IPC-2221 width from `amps` | yes |
| `analog` | F.Cu, no via, length cap | **no** |
| `clock` | length-match group | yes |
| `switch_node` | F.Cu, no via | **no** |
| `digital` | default class | yes |

## Commands

```bash
pcb-space compile examples/blinky.place.py
pcb-space apply   examples/blinky.place.py --pcb path/to/layout.kicad_pcb
pcb-space check   examples/blinky.place.py --pcb path/to/layout.kicad_pcb
pcb-space route   examples/blinky.place.py --pcb path/to/layout.kicad_pcb
```

`apply` locks `Place(..., locked=True)` footprints, writes net classes into the sibling `.kicad_pro`, writes `.kicad_dru`, and inserts keepout zones. It copies the board to `*.kicad_pcb.bak-pcbspace` first.

`check` fails if a locked part moved or a named keepout disappeared.

`route` writes a KiCadRoutingTools plan (`pcbspace_route.sh`). It does not invent analog copper. Set `KRT_HOME` if the router is not in `~/Downloads/KiCadRoutingTools`. Pass `--run` to execute the script.

## What this is not

- Not a fork of [Zener / pcb](https://github.com/diodeinc/pcb). Use `pcb build` for the netlist; this tool consumes the KiCad board.
- Not Pcbnew. Interactive routing stays in KiCad for leftover analog you want by hand.
- Not an LLM dumping `(segment …)` into the s-expression.

## Status

v0.1: language, compile, apply, check, KRT plan emission. Auto-place of *unlocked* parts is still “engine’s job” (KRT optimize / DeepPCB / Quilter), not a built-in placer.

## License

MIT
