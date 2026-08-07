---
name: aoe4mod-build
description: Build or export an Age of Empires IV `.aoe4mod` file through the AoE4 Content Editor CLI. Use when Codex needs to build or export a mod package from a supplied `.aoe4mod` filepath.
---

# AoE4 Mod Build

Build exactly one AoE4 mod package through the installed Content Editor launcher.

## Procedure

1. Require one absolute path to an existing `.aoe4mod` file. If the user supplies a relative path, resolve it against the current workspace and show the resulting absolute path. Reject missing files and files with another extension.
2. Construct only this command; do not add other Content Editor arguments:

   ```powershell
   & 'F:\Program Files (x86)\Steam\steamapps\common\Age of Empires IV Content Editor\EssenceLauncher.exe' --build_mod '<absolute-path-to-aoe4mod>' --auto_close_burn_window
   ```

3. Display the exact command and ask the user to confirm before executing it. The launcher performs an external build and can write build output.
4. On confirmation, execute the command in PowerShell. Preserve and report the exit code plus any relevant output. If the launcher executable is absent, report its expected path and do not substitute another tool.

## Boundaries

This skill is intentionally limited to the `--build_mod` workflow. Do not use it for general Content Editor CLI operations, imports, localization, source control, or custom build settings.