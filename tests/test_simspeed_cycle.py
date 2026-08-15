import re
import unittest
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
    / "assets"
    / "locdb"
    / "Macro Trainer_en.csv"
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

    def assert_call_order(self, body: str, first: str, second: str) -> None:
        first_index = body.index(first)
        second_index = body.index(second)
        self.assertLess(first_index, second_index)

    def test_phase_rates_and_rule_delays_preserve_real_time(self) -> None:
        self.assertRegex(self.source, r"\bNORMAL_SIM_RATE\s*=\s*8\b")
        self.assertRegex(self.source, r"\bSLOW_SIM_RATE\s*=\s*1\b")
        self.assertRegex(
            self.source, r"\bNORMAL_SPEED_DURATION_SECONDS\s*=\s*45\b"
        )
        self.assertRegex(
            self.source, r"\bSLOW_SPEED_DURATION_SECONDS\s*=\s*15\b"
        )
        self.assertNotIn("setsimpause", self.source.lower())
        self.assertNotRegex(self.source, r"(?<![A-Za-z0-9_])setsimrate\s*\(")
        self.assertNotIn("TimerAddOnce", self.source)
        self.assertNotIn("TimerDel", self.source)

        compensation = function_body(
            self.source, "Mod_GetCompensatedRuleDelay"
        )
        self.assertIn(
            "return realDuration * simRate / NORMAL_SIM_RATE", compensation
        )

        phase = function_body(self.source, "Mod_StartPhase")
        self.assertIn(
            "Mod_GetCompensatedRuleDelay(realDuration, simRate)", phase
        )
        self.assertIn("_mod.phaseStartTime = World_GetGameTime()", phase)
        self.assertIn(
            "_mod.phaseDeadline = _mod.phaseStartTime + ruleDelay", phase
        )
        self.assertIn("Objective_StartTimer(objective, COUNT_DOWN, realDuration, 0)", phase)
        self.assert_call_order(phase, "Misc_SetSimRate(simRate)", "Rule_AddOneShot(")

        start = function_body(self.source, "Mod_Start")
        self.assertIn(
            'Mod_StartPhase("$4", NORMAL_SPEED_DURATION_SECONDS, NORMAL_SIM_RATE, Mod_EnterSlowSpeed)',
            start,
        )

        slow = function_body(self.source, "Mod_EnterSlowSpeed")
        self.assertIn(
            'Mod_StartPhase("$5", SLOW_SPEED_DURATION_SECONDS, SLOW_SIM_RATE, Mod_EnterNormalSpeed)',
            slow,
        )

        normal = function_body(self.source, "Mod_EnterNormalSpeed")
        self.assertIn(
            'Mod_StartPhase("$4", NORMAL_SPEED_DURATION_SECONDS, NORMAL_SIM_RATE, Mod_EnterSlowSpeed)',
            normal,
        )

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
        self.assertRegex(self.locdb, r"(?m)^5,[^\r\n]*,PAUSED\r?$")

    def test_game_over_stops_transitions_and_active_objective(self) -> None:

        game_over = function_body(self.source, "Mod_OnGameOver")
        self.assertIn("Rule_Remove(Mod_EnterSlowSpeed)", game_over)
        self.assertIn("Rule_Remove(Mod_EnterNormalSpeed)", game_over)
        self.assertIn("Mod_ClearPhaseObjective()", game_over)
        self.assertIn("Misc_SetSimRate(NORMAL_SIM_RATE)", game_over)


if __name__ == "__main__":
    unittest.main()
