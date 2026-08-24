# aoe4-macro-trainer
App for training macro habits via overlays, gameplay mods, and puzzles/scenarios

## Build orders

Build-order YAML files in `build_orders/` are authoritative. Build outputs under
`assets/` are generated local files and are intentionally ignored by Git. Every
build first resets those files to the checked-in baseline templates, then parses
and validates all YAML before emitting a new catalog.

Use `python tools/build_mod.py --build-orders build_orders --generate-only` to
validate and generate assets without launching the editor (useful for tests).
Normal builds require the Age of Empires IV Content Editor launcher at
`F:\Program Files (x86)\Steam\steamapps\common\Age of Empires IV Content Editor\EssenceLauncher.exe`
and must name the authoritative YAML directory so those orders are bundled:

```powershell
python tools/build_mod.py --build-orders '<absolute-path-to-build-orders>'
```
