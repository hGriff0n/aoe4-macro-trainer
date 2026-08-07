# AoE4 Mod Build Skill Design

## Goal

Provide a project-local Codex skill that launches the AoE4 Content Editor CLI to build a supplied `.aoe4mod` file.

## Scope

- Trigger for requests to **build** or **export** an AoE4 mod.
- Accept one existing `.aoe4mod` file path.
- Invoke `F:\Program Files (x86)\Steam\steamapps\common\Age of Empires IV Content Editor\EssenceLauncher.exe` with `--build_mod <absolute-path>` and `--auto_close_burn_window`.
- Show the exact invocation and request confirmation before launching it.

## Out of Scope

- Other Content Editor CLI options.
- Helper scripts, UI metadata, and source-control integration.

## Structure

Create `.agents/skills/aoe4mod-build/SKILL.md` only. The document will contain the trigger description, path validation, fixed command construction, confirmation requirement, and basic failure handling.

## Validation

Run the skill creator's validator against the new skill directory. Do not run the editor build as part of skill validation.
