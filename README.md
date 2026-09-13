# pcb-space

**Zener (`pcb`) is the schematic language. pcb-space is the spatial compiler and fab packager in front of KiCad.**

This is not a Zener fork. You write a `.zen` board and a `.place.py`. **`pcb-space build` is the compiler:** schematic (`pcb build` + lint) → seed (`pcb layout --no-open`) → place → route → fab. The agent never has to click Pcbnew.

```
pcb-space source   MPN / LCSC → Zener package + SOURCE.json
      ↓
.zen + .place.py   intent (Zener nets, CSS locks, NetReq)
      ↓
pcb-space build    schematic → seed → place → route → fab
```

Already-committed `placed/` / `routed/` / `fab/` are left alone. `--force` or `--from place` is an opt-in rebuild (a new PCBA). `pcb layout` on those directories duplicates footprints; `seed` / `place` / `build` refuse them.

## Getting started

You need four tools on `PATH`:

| Tool | Role |
|---|---|
| [`pcb`](https://github.com/diodeinc/pcb) (Zener) | Schematic, `pcb build`, `pcb layout --no-open` |
| `pcb-space` | Place, route, silk, fab, source, status |
| KiCad 10 `kicad-cli` | DRC, Gerbers, review SVGs |
| KiCadRoutingTools (`KRT_HOME`, default `~/Downloads/KiCadRoutingTools`) | Place legalize + route engine |

```bash
pip install -e ".[dev]"          # this repo
# pcb: https://github.com/diodeinc/pcb  → ~/.local/bin/pcb
# KiCad 10: macOS app, or Ubuntu ppa:kicad/kicad-10.0-releases
export KRT_HOME=~/Downloads/KiCadRoutingTools

pcb-space init blinky -C ./blinky
# source parts, write the .zen and Place() locks, then:
pcb-space build blinky.place.py
pcb-space status blinky.place.py
```

`--upto schematic|seed|place|route|fab` stops early. `--dry-run` prints the plan. `--force` rebuilds from schematic (new copper).

Worked PCBA (already fabbed in git — `build` is a no-op until `--force`):

```bash
pcb-space build   examples/c3_usb --dry-run
pcb-space status  examples/c3_usb
pcb-space lint    examples/c3_usb/c3_usb.zen
```

## Why this exists

KiCad 10 already *uses* 0.20 mm traces and *checks* clearance. It will not:

- derive 0.20/0.15 mm from “USB 2.0, 90 Ω” plus a JLCPCB 4-layer stackup
- keep “USB-C at this end, this offset, for the enclosure” in git
- autoroute from a CLI an agent can call

Zener (`Net`, `Module`, `pcb build`) is required for the netlist. pcb-space **sources** parts (LCSC first; DigiKey/Mouser when API keys exist), gates the land against the datasheet body, and compiles placement/routing. `pcb-space lint` checks USB-C both-orientations / CC Rd / ESP32 D+/D− on the `.zen`.

Analog EMG and switching nodes stay `autoroute=False` until you say otherwise. A maze that “meets 0.2 mm width” can still ruin a boost SW loop.

## Install

```bash
pip install -e ".[dev]"
```

Python 3.11+. Compile / apply / check need no extra Python packages. Zener (`pcb`), KiCad 10, and KRT are required for seed / place / route / fab — see Getting started.

## Place file

Placement uses **CSS names**. Unitless numbers are millimetres. The board is the containing block. Locked parts are `position: absolute`. Footprints have intrinsic size (the courtyard), like an `<img>`. `margin: auto` centers on the free axis. `padding` lives on `Board` / `Region`, not on a part.

```python
Board(width=52, height=30, layers=4, stackup="jlcpcb_4l_1oz")

# Flush to the east end, vertically centered. rotate is pre-layout (PCB, not CSS transform).
Place(
    "U26",
    position="absolute",
    right=0,
    top=0,
    bottom=0,
    margin_top="auto",
    margin_bottom="auto",
    rotate=90,
    locked=True,
    reason="USB-C at pod end",
)

# Same thing as a style string (AIs dump CSS this way).
Place(
    "U28",
    style="position:absolute; top:0; left:0; right:0; margin-left:auto; margin-right:auto",
    locked=True,
    reason="FFC to garment",
)

# Enclosure CAD still wins: at= is the KiCad footprint origin.
Place("U32", at=(26.0, 11.5), side="B", locked=True, reason="PPG optical window")

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

Region("header", top=0, left=0, right=0, height=8, padding=0.5)

NetReq("USB_DP", "USB_DN", kind="usb_hs", z_diff_ohm=90, pair=True)
NetReq("3V3", kind="power", volts=3.3, amps=0.25)
NetReq("CH[1-9]*", kind="analog", max_mm=18, vias=False,
       keep_clear_of="BOOST.BOOST_SW", keep_clear_mm=0.5)
```

`Place` accepts the **Zener instance name** (`J1`) or the KiCad reference (`U3`). pcb-space maps them through the footprint `Path` property (`J1.TYPE_C_…` → `U3`).

The web mapping:

| CSS | pcb-space | Notes |
|---|---|---|
| `position: absolute` | locked mechanical part | Engine must not move it |
| `position: static` | unlocked | Engine packs it later |
| `top` / `right` / `bottom` / `left` / `inset` | same | mm or `%` of the containing block |
| `margin` / `margin-top` / … / `auto` | same | Courtyard-to-edge. `auto` + both edges = center |
| `padding` | `Board` / `Region` only | Shrinks the containing block |
| `width` / `height` | `Keepout` / `Region` | Footprints: courtyard is intrinsic |
| `transform: translateY(-50%)` | same, **layout-affecting** | So the web centering trick actually moves copper |
| `rotate` / `transform: rotate(90deg)` | **before** layout | Unlike CSS, rotation changes the used box |
| `at=(x, y)` | KiCad origin | CAD apertures. Do not mix with left/top/right/bottom |
| `side='B'` | back copper | **Not** `z-index` |

Rejected on purpose (clear error, not a silent no-op): `z-index`, `flex` / `grid` / `display:flex`, `px` / `em` / `rem`, `position: sticky|fixed`. Unlocked packing is the engine, not flexbox.

### `NetReq` kinds

| kind | Compiles to | Autoroute |
|---|---|---|
| `usb_hs` | 90 Ω (or `z_diff_ohm`) pair geometry from the stackup | diff pair |
| `power` | IPC-2221 width from `amps` | yes |
| `analog` | F.Cu, no via, length cap | **no** |
| `clock` | length-match group | yes |
| `switch_node` | F.Cu, no via | **no** |
| `digital` | default class | yes |

## Source (parts)

Distributors are not CAD libraries. `source search` hits LCSC/JLC. `source check` fails a land whose Fab body is not the datasheet size (the SHT40 1.5 mm die on a 1.0 mm UDFN). Passives stay stdlib generics — do not download a unique 0402 symbol.

```bash
pcb-space source search TPS61023DRLR --fab jlcpcb
pcb-space source import  "100nF 0402" --kind generic -o components
pcb-space source import  SHT40-AD1B --footprint path/to.kicad_mod --body 1.5x1.5
pcb-space source check   components/Sensirion/SHT40-AD1B --body 1.5x1.5
```

Worked example: `examples/c3_usb/` (USB-C ESP32-C3 node). EasyEDA’s ESP32 land failed the 16.6×13.2 mm body gate; the KiCad MINI-1 land passed.

`pcb-source` is the same commands without the `source` prefix. DigiKey/Mouser rows appear once `DIGIKEY_CLIENT_ID` / `MOUSER_API_KEY` are set; without keys they are listed as skipped, not invented.

## Commands

```bash
pcb-space init    blinky -C ./blinky
pcb-space build   examples/c3_usb --dry-run
pcb-space build   blinky.place.py --upto place
pcb-space lint    examples/c3_usb/c3_usb.zen
pcb-space seed    examples/c3_usb/c3_usb.place.py   # pcb layout --no-open; seed only
pcb-space status  examples/c3_usb
pcb-space refs    examples/c3_usb/c3_usb.place.py
pcb-space nets    examples/c3_usb/c3_usb.place.py --stub
pcb-space compile examples/blinky.place.py
pcb-space apply   examples/blinky.place.py --pcb path/to/layout.kicad_pcb
pcb-space place   examples/c3_usb/c3_usb.place.py
pcb-space check   examples/c3_usb/c3_usb.place.py --pcb path/to/layout_placed.kicad_pcb
pcb-space route   examples/blinky.place.py --pcb path/to/layout.kicad_pcb
pcb-space silk    examples/c3_usb/c3_usb.place.py
pcb-space fab     examples/c3_usb/c3_usb.place.py
pcb-space review  examples/c3_usb/c3_usb.place.py
pcb-space source  search "100nF 0402"
```

Worked PCBA: `examples/c3_usb/` (USB-C → AP2112 → ESP32-C3-MINI-1). CI runs the unit tests, then `pcb-space fab` on the committed routed board so Gerbers / JLC BOM / CPL are produced without clicking Pcbnew. The fab job installs KiCad 10 from the KiCad PPA (Ubuntu’s `kicad` package is 7.x and cannot load these boards). Full re-place / re-route needs `KRT_HOME` and is not run on GitHub Actions.

`apply` locks `Place(..., locked=True)` footprints, writes the `Edge.Cuts` outline from `Board` size when the seed has none, writes net classes into the sibling `.kicad_pro`, writes `.kicad_dru`, and inserts keepout zones. It copies the board to `*.kicad_pcb.bak-pcbspace` first.

`build` is the unified compiler. It skips stages that already have artifacts so a committed `routed/` board is what you order. `--force` / `--from` rebuilds on purpose and writes `layout/<name>/pcbspace.lock.json` (pcb-space, `pcb`, kicad-cli, KRT).

`seed` runs `pcb layout --no-open` on the sibling `.zen` and refuses if the target is under `placed/`, `routed/`, or `fab/`, or already has copper.

`place` copies the **seed**, runs `apply` on the copy, compiles a KRT floorplan-intent (locks, edge bands, keepouts), and legalizes unlocked parts with `place_seed --force --anchors-first`. Locked CSS poses are file-locks; the engine must not move them. Output is `placed/layout.kicad_pcb` next to the seed (a second `.kicad_pro` in the seed directory would make `pcb layout` refuse the project). `pcb layout` is seed-only — never a placer. `pcb-space place` on a packed board is an error.

`status` reports the stage (schematic / seeded / placed / routed / fab), whether `pcb build` is green, `lint` failures, missing `Place()` names, and nets with no `NetReq`.

`refs` maps Zener instance names (`R_CC1`) to KiCad references (`R2`) via footprint `Path`.

`check` fails if a locked part moved or a named keepout disappeared.

`route` picks the `placed/` board when it exists, refreshes net classes, routes USB pairs (`route_diff`), then signals, then on 2-layer pours GND last and finalizes. Analog / switch-node nets stay in `skip_autoroute`. Output is `routed/layout.kicad_pcb`. `--script-only` writes the plan without running it. Set `KRT_HOME` if the router is not in `~/Downloads/KiCadRoutingTools`. True 90 Ω USB needs 4-layer; 1.6 mm 2-layer is a tightly-coupled fab-floor pair, not 90 Ω.

`fab` picks `routed/` when it exists, inserts three F.Cu fiducials, writes JLCPCB `bom.csv` / `cpl.csv` (LCSC from `SOURCE.json`; CPL from footprint positions, Y negated like KiCad POS), Gerbers, drill, and `FAB_NOTES.md` (via-in-pad). It does not upload. Copper `kicad-cli` DRC errors fail the command. KiCad 10 is required for DRC/Gerbers.

## What this is not

- Not a fork of [Zener / pcb](https://github.com/diodeinc/pcb) and not a replacement for it. The schematic is Zener. This tool consumes the KiCad board Zener seeded.
- Not Pcbnew. Interactive routing stays in KiCad for leftover analog you want by hand.
- Not an LLM dumping `(segment …)` into the s-expression.
- Not a CSS layout engine. No flex, no grid, no `px`. Locked parts get a CSS **containing block**. Unlocked parts get a placer.

## Status

v0.4: `pcb-space build` is the compiler (schematic → seed → place → route → fab). Zener is required for the netlist. `init`, `status`, `seed`, `refs`, `lint`, `nets`. CSS locks; `place` / `route` / `silk` / `fab` / `review`. CI fabs the committed routed board (does not re-place).

## License

MIT
