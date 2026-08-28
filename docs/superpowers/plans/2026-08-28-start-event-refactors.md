# Start-event objective refactors plan

1. Extend the dedicated event-probe worktree with synchronous and next-tick queue snapshots for entity commands and production/upgrade terminal events. Add static contracts, review, then build only the probe mod for a controlled cancellation session.
2. In the GRI-57 worktree, merge the new documentation base and replace completion listeners with `GE_ConstructionStart` / `GE_UpgradeStart`. Use `context.upgrade` for upgrade identity, preserve human filtering and completed-state activation reconciliation, add tests, review, and queue validation without building.
3. After the focused probe log is available, update its findings report with command ordering, queue visibility, and genuine cancellation behavior.
4. In the GRI-59 worktree, fix all upgrade event identity access to `context.upgrade` and replace continuous queued polling only if the probe proves event-triggered reconciliation covers insertion and cancellation. Defer successful cancellation handling so the paired completion wins. Test, review, and queue validation without building.
5. In the GRI-60 worktree, replace queued polling only if the probe proves human-owned command/completion/cancellation events cover every queue mutation. Reconcile full queue PBG tuples after the proven callback boundary. Test, review, and queue validation without building.
6. Rerun cross-branch static verification and present the revised validation queue. No check worktree is built until the user selects it.
