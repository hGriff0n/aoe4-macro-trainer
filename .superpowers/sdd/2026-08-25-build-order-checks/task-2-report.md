# GRI-55 `vils` check report

## Result

The `vils` YAML mapping emits one reversible descriptor with deterministic
resource ordering and a readable title, such as `1 food | 1 wood`. The handler
is imported from the root wincondition, registers the `vils` lifecycle handler,
and evaluates only the human player's gathering squads.

All active descriptors share the named `Vils_PollAll` rule. It is registered
when the first descriptor activates and removed after the last descriptor
deactivates. Each poll reports both complete and incomplete states. Missing or
non-numeric gathering counts normalize to zero, leaving the objective
incomplete instead of allowing the poll rule to fail.

## Regression coverage

`tests/test_build_order_vils.py` verifies the root import, handler registration,
human-player binding, resource threshold evaluation, reversible completion,
nil-safe normalization, first-active/last-inactive polling-rule lifecycle, and
the absence of diagnostic poll logging. Compiler and build tests cover the
generated descriptor title and packaged script import.

## Scope

This work is statically tested only. No Content Editor build was run for this
cleanup.
