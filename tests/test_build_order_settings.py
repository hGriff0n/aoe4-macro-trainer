import csv
import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RDO = ROOT / "assets" / "scar" / "winconditions" / "Macro Trainer.rdo"
LOCDB = ROOT / "assets" / "locdb" / "Macro Trainer_en.csv"
SCAR = ROOT / "assets" / "scar" / "winconditions" / "Macro Trainer.scar"


def option_by_key(root: ET.Element, key: str) -> ET.Element:
    for option in root.findall(".//DataObject"):
        property_ = option.find("./DataProperty[@Name='m_key']")
        if property_ is not None and property_.get("Value") == key:
            return option
    raise AssertionError(f"missing option {key}")


def csv_rows(path: Path) -> dict[int, list[str]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        return {
            int(row[0]): row
            for row in csv.reader(source)
            if row and row[0].isdigit()
        }


class BuildOrderSettingTests(unittest.TestCase):
    def test_assets_define_simspeed_settings_without_a_build_order_option(self) -> None:
        root = ET.parse(RDO).getroot()
        simspeed = option_by_key(root, "option_enable_simspeed_cycle")
        self.assertEqual(
            simspeed.get("Type"), "WinCondition::BooleanOptionUIDescriptor"
        )
        self.assertEqual(
            simspeed.find("./DataProperty[@Name='m_defaultValue']").get("Value"),
            "true",
        )

        option_keys = {
            property_.get("Value")
            for property_ in root.findall(".//DataProperty[@Name='m_key']")
        }
        self.assertNotIn("option_build_order", option_keys)

        rows = csv_rows(LOCDB)
        self.assertNotIn(20, rows)
        self.assertNotIn(21, rows)
        self.assertNotIn(22, rows)
        self.assertEqual(rows[23][-1], "Enable Slow/Normal Cycle")
        self.assertEqual(
            rows[24][-1],
            "Alternate between configured normal-speed and slowed planning phases.",
        )

    def test_settings_only_decode_the_remaining_slow_rate_enum(self) -> None:
        source = SCAR.read_text(encoding="utf-8")
        helper = re.search(
            r"function Mod_GetOptionEnumKey\(option\)(.*?)(?=^function |\Z)",
            source,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(helper)
        body = helper.group(1)
        self.assertIn('type(option) ~= "table"', body)
        self.assertRegex(
            body,
            r"for enumKey, enumValue in pairs\(option\.enum_items\) do\s*"
            r"if enumValue == option\.enum_value then\s*return enumKey",
        )

        self.assertNotIn("function Mod_ReadSelectedBuildOrder", source)
        setup = re.search(
            r"function Mod_SetupSettings\([^)]*\)(.*?)(?=^function |\Z)",
            source,
            re.MULTILINE | re.DOTALL,
        ).group(1)
        self.assertIn("Mod_GetOptionEnumKey(settings.option_slow_sim_rate)", setup)
        self.assertNotIn("option_build_order", setup)
        self.assertNotIn("selectedBuildOrderID", setup)


if __name__ == "__main__":
    unittest.main()
