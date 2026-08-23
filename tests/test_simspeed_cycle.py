import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


SCAR_PATH = (
    Path(__file__).resolve().parents[1]
    / "assets"
    / "scar"
    / "winconditions"
    / "Macro Trainer.scar"
)
LOCDB_PATH = (
    Path(__file__).resolve().parents[1]
    / "build"
    / "templates"
    / "assets"
    / "locdb"
    / "Macro Trainer_en.csv"
)
RDO_PATH = (
    Path(__file__).resolve().parents[1]
    / "build"
    / "templates"
    / "assets"
    / "scar"
    / "winconditions"
    / "Macro Trainer.rdo"
)


def function_body(source: str, function_name: str) -> str:
    match = re.search(
        rf"function {re.escape(function_name)}\([^)]*\)(.*?)(?=^function |\Z)",
        source,
        re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing function {function_name}")
    return match.group(1)


class SimspeedCycleContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SCAR_PATH.read_text(encoding="utf-8")
        cls.locdb = LOCDB_PATH.read_text(encoding="utf-8-sig")
        cls.rdo_root = ET.parse(RDO_PATH).getroot()

    def assert_call_order(self, body: str, first: str, second: str) -> None:
        first_index = body.index(first)
        second_index = body.index(second)
        self.assertLess(first_index, second_index)

    def test_phase_rates_and_delays_use_lobby_settings(self) -> None:
        self.assertRegex(self.source, r"\bNORMAL_SIM_RATE\s*=\s*8\b")
        self.assertNotIn("setsimpause", self.source.lower())
        self.assertNotRegex(self.source, r"(?<![A-Za-z0-9_])setsimrate\s*\(")
        self.assertNotIn("TimerAddOnce", self.source)
        self.assertNotIn("TimerDel", self.source)

        start = function_body(self.source, "Mod_Start")
        self.assertIn(
            "_mod.normalPhaseDuration = math.ceil(_mod.normalDurationSeconds * NORMAL_SIM_RATE / NORMAL_SIM_RATE)",
            start,
        )
        self.assertIn(
            "_mod.slowPhaseDuration = math.ceil(_mod.slowDurationSeconds * _mod.slowSimRate / NORMAL_SIM_RATE)",
            start,
        )
        self.assertIn(
            "Mod_StartPhase(NORMAL_PHASE_OBJECTIVE_TITLE, _mod.normalPhaseDuration, NORMAL_SIM_RATE, Mod_EnterSlowSpeed)",
            start,
        )

        slow = function_body(self.source, "Mod_EnterSlowSpeed")
        self.assertIn(
            "Mod_StartPhase(SLOW_PHASE_OBJECTIVE_TITLE, _mod.slowPhaseDuration, _mod.slowSimRate, Mod_EnterNormalSpeed)",
            slow,
        )

        normal = function_body(self.source, "Mod_EnterNormalSpeed")
        self.assertIn(
            "Mod_StartPhase(NORMAL_PHASE_OBJECTIVE_TITLE, _mod.normalPhaseDuration, NORMAL_SIM_RATE, Mod_EnterSlowSpeed)",
            normal,
        )

        phase = function_body(self.source, "Mod_StartPhase")
        self.assertIn("_mod.phaseStartTime = World_GetGameTime()", phase)
        self.assertIn(
            "_mod.phaseDeadline = _mod.phaseStartTime + phaseDuration", phase
        )
        self.assertIn(
            "Objective_StartTimer(objective, COUNT_DOWN, phaseDuration, 0)",
            phase,
        )
        self.assertIn("Rule_AddOneShot(nextRule, phaseDuration)", phase)
        self.assert_call_order(
            phase, "Misc_SetSimRate(simRate)", "Rule_AddOneShot("
        )

    def test_lobby_options_define_integer_durations_and_slow_rate_enum(self) -> None:
        sections = self.rdo_root.findall(".//DataObject[@Type='WinCondition::OptionSectionUIDescriptor']")
        section = next(
            item
            for item in sections
            if item.find("./DataProperty[@Name='m_key']").get("Value")
            == "section_macro_trainer_settings"
        )
        options = {
            item.find("./DataProperty[@Name='m_key']").get("Value"): item
            for item in section.findall("./DataProperty[@Name='m_options']/DataObject")
        }

        for key, default in (
            ("option_normal_duration_seconds", "45"),
            ("option_slow_duration_seconds", "15"),
        ):
            option = options[key]
            self.assertEqual(
                option.get("Type"), "WinCondition::IntegerOptionUIDescriptor"
            )
            self.assertEqual(
                option.find("./DataProperty[@Name='m_defaultValue']").get("Value"),
                default,
            )

        slow_rate = options["option_slow_sim_rate"]
        self.assertEqual(
            slow_rate.get("Type"), "WinCondition::EnumerationOptionUIDescriptor"
        )
        enum_items = slow_rate.findall(
            "./DataProperty[@Name='m_enumItems']/DataObject"
        )
        self.assertEqual(
            [
                item.find("./DataProperty[@Name='m_key']").get("Value")
                for item in enum_items
            ],
            [f"slow_sim_rate_{value}" for value in range(1, 8)],
        )
        defaults = [
            item.find("./DataProperty[@Name='m_key']").get("Value")
            for item in enum_items
            if item.find("./DataProperty[@Name='m_isDefaultValue']").get("Value")
            == "true"
        ]
        self.assertEqual(defaults, ["slow_sim_rate_1"])

    def test_setup_settings_applies_safe_lobby_values(self) -> None:
        setup = function_body(self.source, "Mod_SetupSettings")
        self.assertIn("options.section_macro_trainer_settings", setup)
        self.assertIn("option_normal_duration_seconds", setup)
        self.assertIn("option_slow_duration_seconds", setup)
        self.assertIn("option_slow_sim_rate", setup)
        self.assertIn("math.max(1, math.min(300,", setup)
        self.assertIn("slow_sim_rate_1", self.source)
        self.assertIn("slow_sim_rate_7", self.source)

    def test_phase_titles_use_fully_qualified_mod_localization_keys(self) -> None:
        mod_namespace = "dfb5645698a84afb91cf7a2dfb0f4a4e"
        self.assertIn(
            f'NORMAL_PHASE_OBJECTIVE_TITLE = "${mod_namespace}:4"',
            self.source,
        )
        self.assertIn(
            f'SLOW_PHASE_OBJECTIVE_TITLE = "${mod_namespace}:5"',
            self.source,
        )
        self.assertNotRegex(self.source, r'Mod_StartPhase\("\$[45]"')

    def test_each_phase_replaces_the_standard_objective_silently(self) -> None:
        clear = function_body(self.source, "Mod_ClearPhaseObjective")
        self.assertIn("Objective_StopTimer(_mod.phaseObjective)", clear)
        self.assertIn("Objective_Expire(_mod.phaseObjective, false, false)", clear)
        self.assert_call_order(clear, "Objective_StopTimer", "Objective_Expire")

        phase = function_body(self.source, "Mod_StartPhase")
        self.assertIn("Mod_ClearPhaseObjective()", phase)
        self.assertIn("Title = title", phase)
        self.assertIn("Type = OT_Information", phase)
        self.assertIn("Objective_Register(objective)", phase)
        self.assertIn("Objective_Start(objective, false, false)", phase)
        self.assert_call_order(phase, "Objective_Register", "Objective_Start(")
        self.assert_call_order(phase, "Objective_Start(", "Objective_StartTimer")
        self.assertNotIn("UI_SetPropertyValue", self.source)

        self.assertRegex(self.locdb, r"(?m)^4,[^\r\n]*,NORMAL\r?$")
        self.assertRegex(self.locdb, r"(?m)^5,[^\r\n]*,SLOW\r?$")
        self.assertNotRegex(self.locdb, r"(?m)^5,[^\r\n]*,PAUSED\r?$")

    def test_game_over_stops_transitions_and_active_objective(self) -> None:

        game_over = function_body(self.source, "Mod_OnGameOver")
        self.assertIn("Rule_Remove(Mod_EnterSlowSpeed)", game_over)
        self.assertIn("Rule_Remove(Mod_EnterNormalSpeed)", game_over)
        self.assertIn("Mod_ClearPhaseObjective()", game_over)
        self.assertIn("Misc_SetSimRate(NORMAL_SIM_RATE)", game_over)


if __name__ == "__main__":
    unittest.main()
