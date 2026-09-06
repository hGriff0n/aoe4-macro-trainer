---
name: aoe4mod-build
description: Use when Codex needs to build or export the Macro Trainer `.aoe4mod` package through the Age of Empires IV Content Editor.
---

# AoE4 Mod Build

Build exactly one Macro Trainer package by invoking the installed Content Editor launcher directly.

## Procedure

1. Resolve the requested `.aoe4mod` path against the current workspace. Require an existing file named `Macro Trainer.aoe4mod`. Also require the launcher at `F:\Program Files (x86)\Steam\steamapps\common\Age of Empires IV Content Editor\EssenceLauncher.exe`. Show both resolved paths and stop if either is missing.
2. Construct the command for the active shell, substituting the resolved Windows path for the mod file.

   PowerShell:

   ```powershell
   & 'F:\Program Files (x86)\Steam\steamapps\common\Age of Empires IV Content Editor\EssenceLauncher.exe' --build_mod '<absolute-Windows-path-to-Macro Trainer.aoe4mod>' --auto_close_burn_window
   ```

   Git Bash or another MSYS shell:

   ```bash
   MSYS2_ARG_CONV_EXCL='*' '/f/Program Files (x86)/Steam/steamapps/common/Age of Empires IV Content Editor/EssenceLauncher.exe' --build_mod '<absolute-Windows-path-to-Macro Trainer.aoe4mod>' --auto_close_burn_window
   ```

   In WSL, use the launcher path below with the same absolute Windows mod-file argument:

   ```bash
   '/mnt/f/Program Files (x86)/Steam/steamapps/common/Age of Empires IV Content Editor/EssenceLauncher.exe' --build_mod '<absolute-Windows-path-to-Macro Trainer.aoe4mod>' --auto_close_burn_window
   ```

3. Display the exact command and ask the user to confirm before executing it. The launcher performs an external build and writes build output.
4. On confirmation, execute the command from the `.aoe4mod` file's parent directory and wait for it to exit. Preserve and report the exit code and relevant output. A nonzero exit means the mod was not successfully built.

## Boundaries

This skill is limited to the `--build_mod` workflow. Do not invoke a Python wrapper, request a YAML build-order directory, add generation flags, or add unrelated Content Editor arguments.

## Quick Reference

| Check | Required result |
|---|---|
| Mod target | Existing file named `Macro Trainer.aoe4mod` |
| Launcher | Existing `EssenceLauncher.exe` at the documented path |
| Arguments | `--build_mod <mod> --auto_close_burn_window` |
| Completion | Process exited with code `0` |

## Common Mistakes

- Treating `.aoe4mod` as a directory instead of an XML descriptor file.
- Running more than one shell variant instead of selecting the active shell.
- Reintroducing the removed Python generation wrapper or YAML directory argument.
- Reporting success before the launcher process exits.
