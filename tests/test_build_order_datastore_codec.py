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
            (
                CheckDescriptor(
                    "vils",
                    "Assign 7 food",
                    False,
                    {"food": 7, "ids": ["unit_a", "unit_b"]},
                ),
                CheckDescriptor(
                    "hints",
                    'Say "hello"',
                    True,
                    {"text": "line one\nline two", "enabled": True},
                ),
            ),
        ),
    ),
    "https://example.com/opening",
)

ZULU = BuildOrder(
    "zulu-opening",
    "zulu",
    "Zulu Opening",
    (Step("Step 1", (CheckDescriptor("hints", "Scout", True, {"text": "Scout"}),)),),
)


class BuildOrderDatastoreCodecTests(unittest.TestCase):
    def test_render_uses_versioned_lua_root_and_sorted_ids(self) -> None:
        text = render_datastore(Catalog((ZULU, ORDER)))

        self.assertTrue(text.startswith("LuaDataStore = {\n    schema_version = 1,"))
        self.assertLess(
            text.index('["english-opening"]'), text.index('["zulu-opening"]')
        )
        self.assertIn('source = "https://example.com/opening"', text)
        self.assertIn('title = "Say \\"hello\\""', text)
        self.assertIn('text = "line one\\nline two"', text)

    def test_parse_round_trips_the_compiled_model(self) -> None:
        text = render_datastore(Catalog((ORDER, ZULU)))

        self.assertEqual(parse_datastore(text), Catalog((ORDER, ZULU)))

    def test_load_absent_datastore_returns_empty_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "macroTrainerBuildOrders.rlt"
            self.assertEqual(load_datastore(path), Catalog(()))

    def test_parser_rejects_unsupported_or_executable_lua(self) -> None:
        invalid = {
            "wrong assignment": "Other = {}",
            "unsupported version": "LuaDataStore = { schema_version = 2, build_orders = {} }",
            "duplicate key": "LuaDataStore = { schema_version = 1, schema_version = 1, build_orders = {} }",
            "trailing code": "LuaDataStore = { schema_version = 1, build_orders = {} }\nprint('x')",
            "function": "LuaDataStore = { schema_version = 1, build_orders = function() end }",
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

    def test_invalid_catalog_never_replaces_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "macroTrainerBuildOrders.rlt"
            original = "LuaDataStore = { schema_version = 1, build_orders = {} }\n"
            path.write_text(original, encoding="utf-8")
            invalid = BuildOrder(
                ORDER.id,
                ORDER.civ,
                ORDER.title,
                (Step("Bad", (CheckDescriptor("bad", "Bad", False, {"value": 1.5}),)),),
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
