---
name: aoe4mod-build
description: Use when Codex needs to build or export the Macro Trainer `.aoe4mod` package with user-authored YAML build orders bundled into the generated mod assets.
---

# AoE4 Mod Build

Build exactly one Macro Trainer package through the repository build wrapper. The wrapper resets generated outputs to baseline, validates and emits the authoritative YAML build orders, and invokes the installed Content Editor launcher only after generation succeeds.

## Procedure

1. Require an absolute path to the existing `Macro Trainer.aoe4mod` file and an absolute path to the directory containing the YAML build orders. Resolve relative paths against the current workspace and show the results. Reject a missing mod file, another extension or filename, a missing/non-directory build-order path, or a project whose `tools/build_mod.py` wrapper is absent.
2. Construct only this command, deriving the wrapper path from the `.aoe4mod` file's parent directory:

   ```powershell
   python '<absolute-project-path>\tools\build_mod.py' --build-orders '<absolute-path-to-build-orders>'
   ```

3. Display the exact command and ask the user to confirm before executing it. The wrapper generates local assets and launches an external build that writes build output.
4. On confirmation, execute the command in PowerShell from the project directory. Preserve and report the exit code plus any relevant output. A nonzero exit means the mod was not successfully built. If the wrapper or configured launcher is absent, report the expected path and do not substitute another tool.

## Boundaries

This skill is intentionally limited to the Macro Trainer build workflow. Do not call Essence directly, omit `--build-orders`, use `--generate-only` for a requested mod build, or add unrelated build settings. Do not use it for general Content Editor CLI operations, imports, localization, or source control.
