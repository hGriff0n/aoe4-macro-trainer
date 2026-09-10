import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from tests.scar_runtime import LuaResults, ScarRuntime


ROOT = Path(__file__).resolve().parents[1]
UI_SCAR = ROOT / "assets" / "scar" / "build_orders" / "selector_ui.scar"
XAML_NS = "http://schemas.microsoft.com/winfx/2006/xaml"


def strip_xaml(source: str) -> str:
    return re.sub(
        r"BUILD_ORDER_SELECTOR_UI_XAML\s*=\s*\[\[.*?\]\]",
        'BUILD_ORDER_SELECTOR_UI_XAML = ""',
        source,
        flags=re.DOTALL,
    )


def extract_xaml(source: str) -> str:
    match = re.search(
        r"BUILD_ORDER_SELECTOR_UI_XAML\s*=\s*\[\[(.*?)\]\]",
        source,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError("missing selector XAML")
    return match.group(1)


def named(root: ET.Element, name: str) -> ET.Element:
    key = f"{{{XAML_NS}}}Name"
    for element in root.iter():
        if element.get(key) == name:
            return element
    raise AssertionError(f"missing x:Name={name}")


class BuildOrderSelectorUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = UI_SCAR.read_text(encoding="utf-8")

    def runtime(self) -> ScarRuntime:
        runtime = ScarRuntime(strip_xaml(self.source))
        runtime.globals["pcall"] = lambda function: LuaResults((True, function()))
        return runtime

    def test_xaml_contains_only_selector_controls(self) -> None:
        xaml = extract_xaml(self.source)
        root = ET.fromstring(xaml)

        named(root, "BuildOrderSelectorList")
        named(root, "BuildOrderSelectorStartGame")
        named(root, "BuildOrderSelectorContinueWithout")
        self.assertNotIn("Editor", xaml)
        self.assertNotIn("Save", xaml)
        self.assertNotIn("Create", xaml)

    def test_show_projects_orders_and_creates_one_presenter(self) -> None:
        runtime = self.runtime()
        additions = []
        updates = []
        runtime.globals["UI_CreateCommand"] = lambda name: f"command:{name}"
        runtime.globals["UI_CreateDataContext"] = lambda value: value
        runtime.globals["UI_AddChild"] = lambda *args: additions.append(args)
        runtime.globals["UI_SetDataContext"] = lambda *args: updates.append(args)

        shown = runtime.call(
            "BuildOrderSelectorUI_Show",
            {"orders": [{"id": "english-opening", "label": "English Opening"}]},
        )

        self.assertTrue(shown)
        self.assertEqual(len(additions), 1)
        self.assertEqual(additions[0][2], "BuildOrderSelectorUI")
        view = updates[-1][1]
        self.assertEqual(view["selector_options"][1]["id"], "english-opening")
        self.assertEqual(view["empty_message"], "")

    def test_commands_dispatch_without_editor_mutation_callbacks(self) -> None:
        runtime = self.runtime()
        calls = []
        globals_table = runtime.table({})
        globals_table["Start"] = lambda value=None: calls.append(("start", value))
        globals_table["Continue"] = lambda value=None: calls.append(("continue", value))
        runtime.globals["_G"] = globals_table
        runtime.call(
            "BuildOrderSelectorUI_SetCallbacks",
            {"start_game": "Start", "continue_without": "Continue"},
        )

        self.assertTrue(
            runtime.call("BuildOrderSelectorUI_DispatchStartGame", "english-opening")
        )
        self.assertTrue(runtime.call("BuildOrderSelectorUI_DispatchContinueWithout"))
        self.assertEqual(calls, [("start", "english-opening"), ("continue", None)])

    def test_stop_removes_presenter_and_clears_callbacks(self) -> None:
        runtime = self.runtime()
        removals = []
        runtime.globals["UI_Remove"] = removals.append
        state = runtime.globals["BUILD_ORDER_SELECTOR_UI_STATE"]
        state["created"] = True
        state["callbacks"] = runtime.table({"start_game": "Start"})

        runtime.call("BuildOrderSelectorUI_Stop")

        self.assertEqual(removals, ["BuildOrderSelectorUI"])
        self.assertEqual(state["callbacks"].data, {})


if __name__ == "__main__":
    unittest.main()
