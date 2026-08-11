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


def function_body(source: str, function_name: str) -> str:
    match = re.search(
        rf"function {re.escape(function_name)}\(\)(.*?)(?=^function |\Z)",
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

    def assert_call_order(self, body: str, first: str, second: str) -> None:
        first_index = body.index(first)
        second_index = body.index(second)
        self.assertLess(first_index, second_index)

    def test_simspeed_cycle_contract(self) -> None:
        self.assertRegex(self.source, r"\bNORMAL_SIM_RATE\s*=\s*8\.0\b")
        self.assertRegex(self.source, r"\bSLOW_SIM_RATE\s*=\s*0\.0\b")
        self.assertRegex(
            self.source, r"\bNORMAL_SPEED_DURATION_SECONDS\s*=\s*45\b"
        )
        self.assertRegex(
            self.source, r"\bSLOW_SPEED_DURATION_SECONDS\s*=\s*15\b"
        )
        self.assertNotIn("setsimpause", self.source.lower())

        start = function_body(self.source, "Mod_Start")
        self.assertIn("setsimrate(NORMAL_SIM_RATE)", start)
        self.assertIn(
            'TimerAddOnce("Mod_EnterSlowSpeed", NORMAL_SPEED_DURATION_SECONDS)',
            start,
        )

        slow = function_body(self.source, "Mod_EnterSlowSpeed")
        self.assertIn("setsimrate(SLOW_SIM_RATE)", slow)
        self.assert_call_order(
            slow,
            'TimerDel("Mod_EnterNormalSpeed")',
            'TimerAddOnce("Mod_EnterNormalSpeed", SLOW_SPEED_DURATION_SECONDS)',
        )

        normal = function_body(self.source, "Mod_EnterNormalSpeed")
        self.assertIn("setsimrate(NORMAL_SIM_RATE)", normal)
        self.assert_call_order(
            normal,
            'TimerDel("Mod_EnterSlowSpeed")',
            'TimerAddOnce("Mod_EnterSlowSpeed", NORMAL_SPEED_DURATION_SECONDS)',
        )

        game_over = function_body(self.source, "Mod_OnGameOver")
        self.assertIn('TimerDel("Mod_EnterSlowSpeed")', game_over)
        self.assertIn('TimerDel("Mod_EnterNormalSpeed")', game_over)
        self.assertIn("setsimrate(NORMAL_SIM_RATE)", game_over)


if __name__ == "__main__":
    unittest.main()
