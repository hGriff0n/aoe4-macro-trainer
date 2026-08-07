# AoE4 Mod Build Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a project-local skill for building an `.aoe4mod` file through the AoE4 Content Editor CLI.

**Architecture:** A single `SKILL.md` provides all procedural guidance. It validates one mod file path and constructs a fixed invocation of the configured launcher.

**Tech Stack:** Markdown skill instructions; Python validation script bundled with `skill-creator`.

## Global Constraints

- Create the skill at `.agents/skills/aoe4mod-build`.
- Do not create UI metadata or helper scripts.
- Invoke only `EssenceLauncher.exe --build_mod <absolute-path> --auto_close_burn_window`.
- Obtain confirmation before running the external launcher.

---

### Task 1: Create and validate the project-local skill

**Files:**
- Create: `.agents/skills/aoe4mod-build/SKILL.md`

**Interfaces:**
- Consumes: one existing filepath ending in `.aoe4mod`.
- Produces: a confirmed external command invoking the fixed Content Editor launcher.

- [ ] **Step 1: Initialize the skill directory**

Run:

```powershell
python 'C:\Users\ghoop\.codex\skills\.system\skill-creator\scripts\init_skill.py' aoe4mod-build --path '.agents\skills'
```

- [ ] **Step 2: Replace the generated `SKILL.md` with the fixed build workflow**

Include YAML frontmatter with this exact trigger description:

```yaml
name: aoe4mod-build
description: Build or export an Age of Empires IV `.aoe4mod` file through the AoE4 Content Editor CLI. Use when Codex needs to build or export a mod package from a supplied `.aoe4mod` filepath.
```

Require the absolute input path, verify the `.aoe4mod` extension and file existence, display the command, request confirmation, then run:

```powershell
& 'F:\Program Files (x86)\Steam\steamapps\common\Age of Empires IV Content Editor\EssenceLauncher.exe' --build_mod '<absolute-path>' --auto_close_burn_window
```

- [ ] **Step 3: Validate the skill**

Run:

```powershell
python 'C:\Users\ghoop\.codex\skills\.system\skill-creator\scripts\quick_validate.py' '.agents\skills\aoe4mod-build'
```

Expected: validation succeeds with no missing required metadata or invalid naming errors.
