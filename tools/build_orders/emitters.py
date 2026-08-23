import csv
import io
import shutil
from pathlib import Path

from .model import Catalog

NAMESPACE = "dfb5645698a84afb91cf7a2dfb0f4a4e"


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8", newline="")
    temporary.replace(path)


def _lua(value: object) -> str:
    if isinstance(value, bool): return "true" if value else "false"
    if isinstance(value, int): return str(value)
    if isinstance(value, str):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\r", "\\r").replace("\n", "\\n").replace("\t", "\\t") + '"'
    if isinstance(value, list): return "{" + ", ".join(_lua(item) for item in value) + "}"
    if isinstance(value, dict): return "{" + ", ".join(f"{key} = {_lua(item)}" for key, item in value.items()) + "}"
    raise TypeError(f"unsupported SCAR value: {value!r}")


def _render_scar(catalog: Catalog, localization: dict[tuple[str, int], int]) -> str:
    lines = ["BUILD_ORDER_CATALOG = {}"]
    for order in catalog.build_orders:
        title_id = localization[(order.id, -1)]
        lines.append(f'BUILD_ORDER_CATALOG["{order.id}"] = {{ civ = {_lua(order.civ)}, title = "${NAMESPACE}:{title_id}", steps = {{')
        for step_index, step in enumerate(order.steps):
            step_id = localization[(order.id, step_index)]
            lines.append(f'{{ title = "${NAMESPACE}:{step_id}", checks = {{')
            for check in step.checks:
                lines.append(f'{{ kind = {_lua(check.kind)}, title = {_lua(check.title)}, optional = {_lua(check.optional)}, payload = {_lua(check.payload)} }},')
            lines.append("}},")
        lines.append("} }")
    return "\n".join(lines) + "\n"


def _render_locdb(template: Path, catalog: Catalog) -> tuple[str, dict[tuple[str, int], int]]:
    baseline = template.read_text(encoding="utf-8-sig")
    if baseline and not baseline.endswith(("\n", "\r")): baseline += "\n"
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    localization: dict[tuple[str, int], int] = {}
    identifier = 1000
    for order in catalog.build_orders:
        localization[(order.id, -1)] = identifier
        writer.writerow([identifier, "", "", "Generated build-order title.", "", "", order.title])
        identifier += 1
        for step_index, step in enumerate(order.steps):
            localization[(order.id, step_index)] = identifier
            writer.writerow([identifier, "", "", "Generated step title.", "", "", step.title or f"Step {step_index + 1}"])
            identifier += 1
    return baseline + output.getvalue(), localization


def reset_outputs(paths) -> None:
    paths.rdo_output.parent.mkdir(parents=True, exist_ok=True)
    paths.locdb_output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(paths.rdo_template, paths.rdo_output)
    shutil.copyfile(paths.locdb_template, paths.locdb_output)
    _atomic_write(paths.scar_output, "BUILD_ORDER_CATALOG = {}\n")


def emit_outputs(catalog: Catalog, paths) -> None:
    locdb, localization = _render_locdb(paths.locdb_template, catalog)
    scar = _render_scar(catalog, localization)
    rdo = paths.rdo_template.read_text(encoding="utf-8")
    staged = [(paths.rdo_output, rdo), (paths.locdb_output, locdb), (paths.scar_output, scar)]
    temporaries: list[tuple[Path, Path]] = []
    try:
        for target, content in staged:
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(f"{target.name}.tmp")
            temporary.write_text(content, encoding="utf-8", newline="")
            temporaries.append((target, temporary))
        for target, temporary in temporaries:
            temporary.replace(target)
    finally:
        for _, temporary in temporaries:
            if temporary.exists(): temporary.unlink()
