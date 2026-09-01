# aoe4-macro-trainer
App for training macro habits via overlays, gameplay mods, and puzzles/scenarios

## Build orders

Build-order YAML files in `build_orders/` are authoritative. Build outputs under
`assets/` are generated local files and are intentionally ignored by Git. Every
build first resets those files to the checked-in baseline templates, then parses
and validates all YAML before emitting a new catalog.

Use `python tools/build_mod.py --build-orders build_orders --generate-only` to
validate and generate assets without launching the editor (useful for tests).
Ordinary builds validate author-facing IDs against the committed game identity
catalog and do not access an external game database.

### Importing RTS Overlay and aoe4guides build orders

The build-order compiler can translate an RTS Overlay `.bo` JSON file or an
aoe4guides build URL into authoritative Macro Trainer YAML. File and URL input
are mutually exclusive and require an explicit output path:

```powershell
python -m tools.build_orders.compiler `
  --import-file 'E:/path/to/2 TC.bo' `
  --output 'build_orders/templar_2tc.yaml'

python -m tools.build_orders.compiler `
  --import-url 'https://aoe4guides.com/builds/nlxHE4i1PhNNXqD2XTAP' `
  --output 'build_orders/templar_2tc.yaml'
```

URL import accepts HTTPS build-page and build-API URLs on `aoe4guides.com`.
It extracts the build ID and requests the fixed overlay endpoint; it never
fetches an arbitrary host supplied by the URL. The resulting YAML retains the
canonical source link for attribution. Ordinary builds remain offline because
only the explicit import command accesses aoe4guides.

The baseline translation preserves source-step ordering. A step's timestamp is
used as its title, positive food/gold/wood/stone allocations become a `vils`
check, and non-empty notes become ordered hints after HTML entity decoding.
Zero allocations do not create checks. Age, population, total-villager, and
builder fields are validated but are not converted into inferred actions.
Likewise, icon markup and arbitrary-language prose remain hints; later,
reviewable translation passes may derive additional checks from them.

Catalog regeneration is a developer-only operation:

```powershell
python tools/generate_game_identities.py --database E:/path/to/index.sanitized.sqlite3
```

The generated JSON is committed so authors and ordinary builds do not need the
source database.

Normal builds require the Age of Empires IV Content Editor launcher at
`F:\Program Files (x86)\Steam\steamapps\common\Age of Empires IV Content Editor\EssenceLauncher.exe`
and must name the authoritative YAML directory so those orders are bundled:

```powershell
python tools/build_mod.py --build-orders '<absolute-path-to-build-orders>'
```
