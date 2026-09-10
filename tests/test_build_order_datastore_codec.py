import tempfile
import unittest
from pathlib import Path

from tools.build_orders.datastore import (
    DatastoreError,
    load_datastore,
    parse_datastore,
    render_datastore,
    write_datastore,
)
from tools.build_orders.model import BuildOrder, Catalog, CheckDescriptor, Step


ORDER = BuildOrder(
    "english-opening",
    "english",
    "Opening",
    (
        Step(
            "Economy",
            (CheckDescriptor("vils", False, {"food": 7}),),
        ),
        Step(None, (CheckDescriptor("hints", True, {"text": "Scout"}),)),
    ),
)

ZULU = BuildOrder(
    "zulu-opening",
    "zulu",
    "Zulu Opening",
    (
        Step(
            "Step 1",
            (
                CheckDescriptor(
                    "hints",
                    True,
                    {"text": 'Say "hello"\nline two'},
                ),
            ),
        ),
    ),
    "https://example.com/opening",
)

AGE_UP_ORDER = BuildOrder(
    "english-age-up",
    "english",
    "Age Up",
    (
        Step(
            "Advance",
            (
                CheckDescriptor(
                    "age_up",
                    False,
                    {
                        "id": "building_landmark_age1_westminster_hall_eng",
                        "trigger": "construction",
                    },
                ),
            ),
        ),
    ),
)


class BuildOrderDatastoreCodecTests(unittest.TestCase):
    def test_render_nests_versioned_catalog_under_datastore_id(self) -> None:
        text = render_datastore(Catalog((ZULU, ORDER)))

        self.assertTrue(
            text.startswith(
                "LuaDataStore = {\n"
                "    macroTrainerBuildOrders = {\n"
                "        schema_version = 2,"
            )
        )
        self.assertLess(
            text.index('["english-opening"]'), text.index('["zulu-opening"]')
        )
        self.assertIn('source = "https://example.com/opening"', text)
        self.assertIn('text = "Say \\"hello\\"\\nline two"', text)
        self.assertIn('title = "Economy"', text)
        self.assertEqual(text.count('title = "Economy"'), 1)
        self.assertNotIn('title = "Step 2"', text)
        self.assertNotRegex(text, r'kind = "(?:vils|hints)",\s*title =')

    def test_parse_round_trips_the_compiled_model(self) -> None:
        text = render_datastore(Catalog((ORDER, ZULU)))

        self.assertEqual(parse_datastore(text), Catalog((ORDER, ZULU)))

    def test_parser_uses_none_for_an_omitted_step_title(self) -> None:
        parsed = parse_datastore(render_datastore(Catalog((ORDER,))))

        self.assertIsNone(parsed.build_orders[0].steps[1].title)

    def test_parser_rejects_schema_version_one(self) -> None:
        text = render_datastore(Catalog((ORDER,))).replace(
            "schema_version = 2", "schema_version = 1", 1
        )

        with self.assertRaisesRegex(DatastoreError, "schema version 1"):
            parse_datastore(text)

    def test_parser_rejects_check_title_as_an_unknown_key(self) -> None:
        text = render_datastore(Catalog((ORDER,))).replace(
            'kind = "vils",',
            'kind = "vils",\n                        title = "Assign",',
            1,
        )

        with self.assertRaisesRegex(DatastoreError, "unknown key 'title'"):
            parse_datastore(text)

    def test_parser_rejects_empty_authored_step_title(self) -> None:
        text = render_datastore(Catalog((ORDER,))).replace(
            'title = "Economy"', 'title = ""', 1
        )

        with self.assertRaisesRegex(
            DatastoreError, "title must be a non-empty string"
        ):
            parse_datastore(text)

    def test_age_up_payload_accepts_runtime_trigger(self) -> None:
        text = render_datastore(Catalog((AGE_UP_ORDER,)))

        self.assertEqual(parse_datastore(text), Catalog((AGE_UP_ORDER,)))

    def test_age_up_payload_rejects_unknown_trigger(self) -> None:
        text = render_datastore(Catalog((AGE_UP_ORDER,))).replace(
            'trigger = "construction"', 'trigger = "other"'
        )

        with self.assertRaisesRegex(DatastoreError, "trigger is unsupported"):
            parse_datastore(text)

    def test_load_absent_datastore_returns_empty_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "macroTrainerBuildOrders.rlt"
            self.assertEqual(load_datastore(path), Catalog(()))

    def test_parser_rejects_unsupported_or_executable_lua(self) -> None:
        invalid = {
            "wrong assignment": "Other = {}",
            "missing datastore wrapper": (
                "LuaDataStore = { schema_version = 2, build_orders = {} }"
            ),
            "unsupported version": (
                "LuaDataStore = { macroTrainerBuildOrders = { "
                "schema_version = 1, build_orders = {} } }"
            ),
            "duplicate key": (
                "LuaDataStore = { macroTrainerBuildOrders = { "
                "schema_version = 2, schema_version = 2, build_orders = {} } }"
            ),
            "trailing code": (
                "LuaDataStore = { macroTrainerBuildOrders = { "
                "schema_version = 2, build_orders = {} } }\nprint('x')"
            ),
            "function": (
                "LuaDataStore = { macroTrainerBuildOrders = { "
                "schema_version = 2, build_orders = function() end } }"
            ),
        }
        for label, text in invalid.items():
            with self.subTest(label=label):
                with self.assertRaises(DatastoreError):
                    parse_datastore(text)

    def test_parser_rejects_mismatched_record_id_and_invalid_check_shape(self) -> None:
        valid = render_datastore(Catalog((ORDER,)))
        with self.assertRaisesRegex(DatastoreError, "record id"):
            parse_datastore(valid.replace('id = "english-opening"', 'id = "other"', 1))
        with self.assertRaisesRegex(DatastoreError, "optional"):
            parse_datastore(valid.replace("optional = false", 'optional = "false"', 1))

    def test_parser_rejects_invalid_kind_specific_payload(self) -> None:
        text = render_datastore(Catalog((ORDER,))).replace(
            "food = 7", 'food = "seven"'
        )

        with self.assertRaisesRegex(DatastoreError, "positive integer"):
            parse_datastore(text)

    def test_invalid_catalog_never_replaces_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "macroTrainerBuildOrders.rlt"
            original = "LuaDataStore = { schema_version = 2, build_orders = {} }\n"
            path.write_text(original, encoding="utf-8")
            invalid = BuildOrder(
                ORDER.id,
                ORDER.civ,
                ORDER.title,
                (Step("Bad", (CheckDescriptor("bad", False, {"value": 1.5}),)),),
            )

            with self.assertRaises(DatastoreError):
                write_datastore(path, Catalog((invalid,)))

            self.assertEqual(path.read_text(encoding="utf-8"), original)
            self.assertFalse(path.with_name(path.name + ".tmp").exists())

    def test_write_creates_parent_and_leaves_no_temporary_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "new" / "datastore" / "macroTrainerBuildOrders.rlt"
            write_datastore(path, Catalog((ORDER,)))

            self.assertEqual(load_datastore(path), Catalog((ORDER,)))
            self.assertFalse(path.with_name(path.name + ".tmp").exists())


if __name__ == "__main__":
    unittest.main()
