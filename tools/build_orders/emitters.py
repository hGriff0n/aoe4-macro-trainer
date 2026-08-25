import csv
import io
import shutil
from pathlib import Path

from .model import Catalog

NAMESPACE = "dfb5645698a84afb91cf7a2dfb0f4a4e"
GENERATED_RDO_ID_START = 9100000000000000000
GENERATED_ENUM_MARKER = "<!-- GENERATED_BUILD_ORDER_ENUM_ITEMS -->"
LocalizationKey = tuple[str, int] | tuple[str, int, int]
LocalizationMap = dict[LocalizationKey, int]


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


def _render_scar(catalog: Catalog, localization: LocalizationMap) -> str:
    lines = ["BUILD_ORDER_CATALOG = {}"]
    for order in catalog.build_orders:
        title_id = localization[(order.id, -1)]
        lines.append(f'BUILD_ORDER_CATALOG["{order.id}"] = {{ civ = {_lua(order.civ)}, title = "${NAMESPACE}:{title_id}", steps = {{')
        for step_index, step in enumerate(order.steps):
            step_id = localization[(order.id, step_index)]
            lines.append(f'{{ title = "${NAMESPACE}:{step_id}", checks = {{')
            for check_index, check in enumerate(step.checks):
                check_id = f"{order.id}:{step_index + 1}:{check_index + 1}"
                check_title_id = localization[(order.id, step_index, check_index)]
                lines.append(
                    f'{{ id = {_lua(check_id)}, kind = {_lua(check.kind)}, '
                    f'title = "${NAMESPACE}:{check_title_id}", '
                    f'optional = {_lua(check.optional)}, payload = {_lua(check.payload)} }},'
                )
            lines.append("}},")
        lines.append("} }")
    return "\n".join(lines) + "\n"


def _render_locdb(template: Path, catalog: Catalog) -> tuple[str, LocalizationMap]:
    baseline = template.read_text(encoding="utf-8-sig")
    if baseline and not baseline.endswith(("\n", "\r")): baseline += "\n"
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    localization: LocalizationMap = {}
    identifier = 1000
    for order in sorted(catalog.build_orders, key=lambda item: (item.civ.casefold(), item.title.casefold())):
        localization[(order.id, -2)] = identifier
        writer.writerow([identifier, "", "", "Generated build-order option.", "", "", f"[{order.civ.title()}] {order.title}"])
        identifier += 1
    for order in catalog.build_orders:
        localization[(order.id, -1)] = identifier
        writer.writerow([identifier, "", "", "Generated build-order title.", "", "", order.title])
        identifier += 1
        for step_index, step in enumerate(order.steps):
            localization[(order.id, step_index)] = identifier
            writer.writerow([identifier, "", "", "Generated step title.", "", "", step.title or f"Step {step_index + 1}"])
            identifier += 1
            for check_index, check in enumerate(step.checks):
                localization[(order.id, step_index, check_index)] = identifier
                writer.writerow(
                    [identifier, "", "", "Generated check title.", "", "", check.title]
                )
                identifier += 1
    return baseline + output.getvalue(), localization


def _reflect_loc_string(identifier: int, owner_id: int, localization_id: int, indent: str) -> str:
    return "\n".join([
        f'{indent}<DataValue Name="util::ReflectLocString">{identifier}</DataValue>',
        f'{indent}<DataObject Name="" Type="util::ReflectLocString" Id="{identifier}" OwnerId="{owner_id}">',
        f'{indent}\t<DataProperty Name="m_modPart2" Type="UInt32" Value="763023249"/>',
        f'{indent}\t<DataProperty Name="m_modPart3" Type="UInt32" Value="1313476603"/>',
        f'{indent}\t<DataProperty Name="m_modPart0" Type="UInt32" Value="3753206870"/>',
        f'{indent}\t<DataProperty Name="m_modPart1" Type="UInt32" Value="1258002600"/>',
        f'{indent}\t<DataProperty Name="m_locStringKey" Type="Int32" Value="{localization_id}"/>',
        f'{indent}</DataObject>',
    ])


def _render_rdo(template: str, catalog: Catalog, localization: LocalizationMap) -> str:
    if template.count(GENERATED_ENUM_MARKER) != 1:
        raise ValueError("RDO template must contain exactly one generated build-order enum marker")
    indent = "\t" * 9
    fragments: list[str] = []
    for offset, order in enumerate(sorted(catalog.build_orders, key=lambda item: (item.civ.casefold(), item.title.casefold()))):
        item_id = GENERATED_RDO_ID_START + offset * 3
        label_id = localization[(order.id, -2)]
        fragments.extend([
            f'{indent}<DataValue Name="WinCondition::OptionEnumItemUIDescriptor">{item_id}</DataValue>',
            f'{indent}<DataObject Name="" Type="WinCondition::OptionEnumItemUIDescriptor" Id="{item_id}" OwnerId="9000000000000000035">',
            f'{indent}\t<DataProperty Name="m_key" Type="String" Value="build_order_{order.id}"/>',
            f'{indent}\t<DataProperty Name="m_feSummaryName" Type="Object">',
            _reflect_loc_string(item_id + 1, item_id, label_id, indent + "\t\t"),
            f'{indent}\t</DataProperty>',
            f'{indent}\t<DataProperty Name="m_feName" Type="Object">',
            _reflect_loc_string(item_id + 2, item_id, label_id, indent + "\t\t"),
            f'{indent}\t</DataProperty>',
            f'{indent}\t<DataProperty Name="m_isDefaultValue" Type="Bool" Value="false"/>',
            f'{indent}\t<DataProperty Name="m_devOnly" Type="Bool" Value="false"/>',
            f'{indent}</DataObject>',
        ])
    return template.replace(GENERATED_ENUM_MARKER, "\n".join(fragments))


def reset_outputs(paths) -> None:
    paths.rdo_output.parent.mkdir(parents=True, exist_ok=True)
    paths.locdb_output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(paths.rdo_template, paths.rdo_output)
    shutil.copyfile(paths.locdb_template, paths.locdb_output)
    _atomic_write(paths.scar_output, "BUILD_ORDER_CATALOG = {}\n")


def emit_outputs(catalog: Catalog, paths) -> None:
    locdb, localization = _render_locdb(paths.locdb_template, catalog)
    scar = _render_scar(catalog, localization)
    rdo = _render_rdo(paths.rdo_template.read_text(encoding="utf-8"), catalog, localization)
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
