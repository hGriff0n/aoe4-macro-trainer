import csv
import re
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from tools.build_mod import BuildPaths
from tools.build_orders.compiler import compile_directory
from tools.build_orders.emitters import emit_outputs, reset_outputs


ROOT = Path(__file__).resolve().parents[1]
RDO_TEMPLATE = ROOT / "build" / "templates" / "assets" / "scar" / "winconditions" / "Macro Trainer.rdo"
LOCDB_TEMPLATE = ROOT / "build" / "templates" / "assets" / "locdb" / "Macro Trainer_en.csv"
SCAR = ROOT / "assets" / "scar" / "winconditions" / "Macro Trainer.scar"
GENERATED_ID_START = 9100000000000000000


def option_by_key(root: ET.Element, key: str) -> ET.Element:
    for option in root.findall(".//DataObject"):
        property_ = option.find("./DataProperty[@Name='m_key']")
        if property_ is not None and property_.get("Value") == key:
            return option
    raise AssertionError(f"missing option {key}")


def csv_rows(path: Path) -> dict[int, list[str]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        return {int(row[0]): row for row in csv.reader(source) if row and row[0].isdigit()}


class BuildOrderSettingTests(unittest.TestCase):
    def test_template_defines_enabled_simspeed_cycle_option(self) -> None:
        root = ET.parse(RDO_TEMPLATE).getroot()
        option = option_by_key(root, "option_enable_simspeed_cycle")
        self.assertEqual(option.get("Type"), "WinCondition::BooleanOptionUIDescriptor")
        self.assertEqual(
            option.find("./DataProperty[@Name='m_defaultValue']").get("Value"),
            "true",
        )

        slow_rate = option_by_key(root, "option_slow_sim_rate")
        build_order = option_by_key(root, "option_build_order")
        option_ids = [
            item.get("Id")
            for item in root.findall(
                ".//DataObject[@Type='WinCondition::OptionSectionUIDescriptor']"
                "/DataProperty[@Name='m_options']/DataObject"
            )
        ]
        self.assertLess(option_ids.index(slow_rate.get("Id")), option_ids.index(option.get("Id")))
        self.assertLess(option_ids.index(option.get("Id")), option_ids.index(build_order.get("Id")))

        rows = csv_rows(LOCDB_TEMPLATE)
        name_key = int(
            option.find(
                "./DataProperty[@Name='m_feName']//DataProperty[@Name='m_locStringKey']"
            ).get("Value")
        )
        tooltip_key = int(
            option.find(
                "./DataProperty[@Name='m_feDescriptionTooltip']"
                "//DataProperty[@Name='m_locStringKey']"
            ).get("Value")
        )
        self.assertEqual(rows[name_key][-1], "Enable Slow/Normal Cycle")
        self.assertEqual(
            rows[tooltip_key][-1],
            "Alternate between configured normal-speed and slowed planning phases.",
        )

    def test_template_defines_default_none_build_order_option(self) -> None:
        root = ET.parse(RDO_TEMPLATE).getroot()
        option = option_by_key(root, "option_build_order")
        self.assertEqual(option.get("Type"), "WinCondition::EnumerationOptionUIDescriptor")
        items = option.findall("./DataProperty[@Name='m_enumItems']/DataObject")
        self.assertEqual(len(items), 1)
        none = items[0]
        self.assertEqual(none.find("./DataProperty[@Name='m_key']").get("Value"), "build_order_none")
        self.assertEqual(none.find("./DataProperty[@Name='m_isDefaultValue']").get("Value"), "true")
        self.assertEqual(none.find("./DataProperty[@Name='m_devOnly']").get("Value"), "false")
        self.assertEqual(RDO_TEMPLATE.read_text(encoding="utf-8").count("<!-- GENERATED_BUILD_ORDER_ENUM_ITEMS -->"), 1)

        rows = csv_rows(LOCDB_TEMPLATE)
        self.assertEqual(rows[20][-1], "Build Order")
        self.assertEqual(rows[21][-1], "Choose a generated build order to practice.")
        self.assertEqual(rows[22][-1], "None")
        self.assertEqual(set(range(1, 20)), set(rows).intersection(range(1, 20)))

    def test_emitter_enumerates_sorted_build_orders_with_localized_labels(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            templates = root / "templates"
            rdo_template = templates / "Macro Trainer.rdo"
            locdb_template = templates / "Macro Trainer_en.csv"
            templates.mkdir()
            shutil.copyfile(RDO_TEMPLATE, rdo_template)
            shutil.copyfile(LOCDB_TEMPLATE, locdb_template)
            orders = root / "orders"
            orders.mkdir()
            (orders / "zulu.yaml").write_text(
                "civ: zulu\ntitle: Z Plan\nsteps:\n  - hints:\n      - Keep scouting\n",
                encoding="utf-8",
            )
            (orders / "english.yaml").write_text(
                "civ: english\ntitle: 2 TC\nsteps:\n  - hints:\n      - Make villagers\n",
                encoding="utf-8",
            )
            paths = BuildPaths(root, rdo_template, locdb_template, root / "assets" / "Macro Trainer.rdo", root / "assets" / "Macro Trainer_en.csv", root / "assets" / "generated" / "build_orders.scar")
            reset_outputs(paths)
            emit_outputs(compile_directory(orders), paths)

            option = option_by_key(ET.parse(paths.rdo_output).getroot(), "option_build_order")
            items = option.findall("./DataProperty[@Name='m_enumItems']/DataObject")
            self.assertEqual(
                [item.find("./DataProperty[@Name='m_key']").get("Value") for item in items],
                ["build_order_none", "build_order_english-2-tc", "build_order_zulu-z-plan"],
            )
            self.assertEqual(
                [item.find("./DataProperty[@Name='m_isDefaultValue']").get("Value") for item in items],
                ["true", "false", "false"],
            )
            self.assertTrue(all(item.find("./DataProperty[@Name='m_devOnly']").get("Value") == "false" for item in items))

            generated_ids = [
                int(item.get("Id"))
                for item in ET.parse(paths.rdo_output).getroot().findall(".//DataObject")
                if item.get("Id", "").startswith("910")
            ]
            self.assertEqual(generated_ids, list(range(GENERATED_ID_START, GENERATED_ID_START + 6)))
            self.assertEqual(len(generated_ids), len(set(generated_ids)))

            rows = csv_rows(paths.locdb_output)
            labels = []
            for item in items[1:]:
                labels.append(rows[int(item.find("./DataProperty[@Name='m_feName']//DataProperty[@Name='m_locStringKey']").get("Value"))][-1])
            self.assertEqual(labels, ["[English] 2 TC", "[Zulu] Z Plan"])
            self.assertEqual([rows[number][-1] for number in range(1, 20)], [csv_rows(LOCDB_TEMPLATE)[number][-1] for number in range(1, 20)])

    def test_settings_records_selected_generated_id_without_starting_objectives(self) -> None:
        source = SCAR.read_text(encoding="utf-8")
        self.assertIn("selectedBuildOrderID = nil", source)
        function = re.search(r"function Mod_ReadSelectedBuildOrder\(settings\)(.*?)(?=^function |\Z)", source, re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(function)
        body = function.group(1)
        self.assertIn('option.enum_value', body)
        self.assertIn('enumKey == "build_order_none"', body)
        self.assertIn('string.gsub(enumKey, "^build_order_", "")', body)
        setup = re.search(r"function Mod_SetupSettings\([^)]*\)(.*?)(?=^function |\Z)", source, re.MULTILINE | re.DOTALL).group(1)
        self.assertIn("_mod.selectedBuildOrderID = Mod_ReadSelectedBuildOrder(settings)", setup)
        self.assertNotIn("Objective_", setup)
        self.assertNotIn("Mod_StartSimspeedCycle", setup)


if __name__ == "__main__":
    unittest.main()
