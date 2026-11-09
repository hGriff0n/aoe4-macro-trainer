# aoe4-macro-trainer

App for training macro habits via overlays, gameplay mods, and puzzles/scenarios.

The app currently provides two feature sets that can be enabled and used independently

1.  **Sim Slowdown**: Periodically drops the game's simrate down. The intent is that this can help players to step away from the action and focus on other areas, thereby building up the "multi-tasking" toolset that the game relies on
2.  **Build Order Objectives**: Displays build orders using in-game objectives, tracking completion and progressing when sub-steps are completed. Requires manually editing the mod's datastore files due to lacking UI ability. The repo does provide an external compiler for automatically updating the datastore file from yaml or importing from aoe4guides/RTSOverlay files.

It is recommended that players make sure that "minimal objectives" is disabled as that interferes with the mod functionality.

NOTE: The mod currently doesn't register any win conditions so games will continue until the player decides to quit.

## Sim Slowdown

As described, this mode basically enables a timer that periodically switches the game's sim rate between "slow" and "normal" sections. Each transition is accompanied by an banner across the screen. The mod also uses the Objectives UI to display the remaining time left in each section, along with some hints for things to do during slow sections

Each transition between slow/fast

The in-game lobby basically provides four settings:
1.  An on/off toggle for diabling the full slow/normal loop
2.  A slider from 1-8 for controlling how slow the slow section is (8=normal gamespeed)
3.  Number of real-time seconds for the normal sections to last
4.  Number of real-time seconds for the slow sections to last

NOTE: The time spent in the "slow sections" is not guaranteed to match the configured values from the lobby due to the way the modding API handles time. All modding APIs use tick-based timing which is thus affected by changes to the simrate. The mod tries to account for that by adjusting the duration of the slow sections based on the configured simrate (so if slow rate is "4" and the slow duration is "14", the mod will wait for ~7 in-game seconds as the in-game seconds are now twice as long). This calculation always rounds-up as fractional ticks aren't a thing.

## Build Order Objectives

This mode provides players with an in-game Objective's overlay that automatically tracks completion of build order steps. Build orders can contain any number of individual steps which themselves consist of any number of "checks", or sub-objectives that describe a specific in-game behavior. All checks are required to be completed (unless marked as optional) before the step can be completed and the build automatically proceeds to the next step (assuming there is any).

### Check Types

The game supports the following kind of checks:

-   **Age Up:** Completes when starting an age up with the indicated options (or if already finished)
-   **Built:** Completes when the specified buildings are constructed
-   **Hints:** Just text that provides additional instructions. Always optional
-   **Produce:** Completes when the specified units are built
-   **Resources:** Completes while the player has the specified resources in bank
-   **Units:** Completes while the player has the specified kind and number of units alive
-   **Upgrades:** Completes when the player researches the indicated tech. Can optionally allow for also completing while the player has the tech queued
-   **Vils:** Completes while the player has the specified number of vilagers (or more) gathering for each indicated resource

The following checks are unimplemented/unregistered at the moment:

-   **Building:** Completes while the player has the specified kind and number of buildings alive
-   **Rallypoint:** Completes while the player has their tcs rallying to the indicated resource


### Compiler Tooling

Although it is possible for players to directly write the mod's text datastore file, this repo also provides some tools to help with the process - ie the `tools/compiler.py` script.

The tool supports the following commands:

-   **build**: Compiles the given yaml files and adds them to the datastore, overwritting any build orders with the same id. Prints out a list of datastore changes and supports a `dry_run` flag. Defaults to reading yaml input from `./build_orders/`
-   **list**: Prints out the compiled build orders currently from the mod's datastore.
-   **delete**: Removes the given build orders from the compiled datastore by id. Supports a `dry_run` flag.
-   **extract**: Extracts the compiled build orders into individual yaml files in the output directory (default=`.`). Can also extract individual ids but defaults to all if no `ids` are provided.
-   **import**: Import build orders from RTSOverlay/aoe4guides/etc. Supports importing from urls or from files matching the RTSOverlay schema. Supports a `dry_run` flag as well as allowing for saving the imported build orders as yaml in the output directory (default=`.`)

Each command also supports an optional `--profile` argument in case the compiler is unable to infer the correct user id from the filesystem. This is generally the case for almost all players unless they are signing in and out on the same machine.

## Building

Build the checked-in assets directly with the Age of Empires IV Content Editor.

From PowerShell:

```powershell
& 'F:\Program Files (x86)\Steam\steamapps\common\Age of Empires IV Content Editor\EssenceLauncher.exe' --build_mod '<absolute-path-to-Macro Trainer.aoe4mod>' --auto_close_burn_window
```

From Git Bash or another MSYS shell on Windows:

```bash
MSYS2_ARG_CONV_EXCL='*' '/f/Program Files (x86)/Steam/steamapps/common/Age of Empires IV Content Editor/EssenceLauncher.exe' --build_mod '<absolute-Windows-path-to-Macro Trainer.aoe4mod>' --auto_close_burn_window
```
