import json
import sqlite3
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

from tools.build_orders.identity_generator import (
    IdentityGenerationError,
    generate_identity_document,
    read_official_rows,
    write_identity_document,
)
from tools.build_orders.identities import (
    IdentityCatalog,
    IdentityCatalogError,
    normalize_identity_id,
)


FIXTURE = Path(__file__).parent / "fixtures" / "game_identities" / "minimal.json"


def row(
    category: str,
    base_id: str,
    attrib_name: str,
    civs: list[str],
    *,
    item_id: str | None = None,
    pbgid: int | None = None,
) -> dict[str, object]:
    return {
        "category": category,
        "base_id": base_id,
        "item_id": item_id if item_id is not None else f"{base_id}-1",
        "attrib_name": attrib_name,
        "pbgid": pbgid,
        "details_json": json.dumps(
            {
                "baseId": base_id,
                "attribName": attrib_name,
                "civs": civs,
            }
        ),
    }


class IdentityGeneratorTests(unittest.TestCase):
    def test_generator_normalizes_base_ids_and_sorts_output(self) -> None:
        document = generate_identity_document(
            [
                row("units", "scout", "unit_scout_1_eng", ["en"]),
                row("buildings", "town-center", "building_town_center_eng", ["en"]),
            ]
        )

        english = document["civilizations"]["english"]
        self.assertEqual(english["entity"]["town_center"], "building_town_center_eng")
        self.assertEqual(english["squad"]["scout"], "unit_scout_1_eng")

    def test_generator_rejects_conflicting_normalized_key(self) -> None:
        rows = [
            row("buildings", "town-center", "building_a", ["en"], item_id="town-center-1"),
            row("buildings", "town-center", "building_b", ["en"], item_id="town-center-1"),
        ]

        with self.assertRaisesRegex(IdentityGenerationError, "conflicting identity"):
            generate_identity_document(rows)

    def test_generator_uses_item_id_when_base_id_has_multiple_canonical_identities(self) -> None:
        document = generate_identity_document(
            [
                row("technologies", "blade-inlaying", "upgrade_damage_2", ["macedonian"], item_id="blade-inlaying-2"),
                row("technologies", "blade-inlaying", "upgrade_damage_4", ["macedonian"], item_id="blade-inlaying-4"),
            ]
        )

        upgrades = document["civilizations"]["macedonian_dynasty"]["upgrade"]
        self.assertNotIn("blade_inlaying", upgrades)
        self.assertEqual(upgrades["blade_inlaying_2"], "upgrade_damage_2")
        self.assertEqual(upgrades["blade_inlaying_4"], "upgrade_damage_4")

    def test_generator_rejects_normalized_output_collision_between_distinct_raw_base_ids(self) -> None:
        rows = [
            row("buildings", "town-center", "building_one", ["en"], item_id="town-center-a"),
            row("buildings", "town_center", "building_two", ["en"], item_id="town_center-b"),
        ]

        with self.assertRaisesRegex(IdentityGenerationError, "conflicting identity"):
            generate_identity_document(rows)

    def test_generator_rejects_unknown_source_civ(self) -> None:
        with self.assertRaisesRegex(IdentityGenerationError, "unknown source civilization 'new'"):
            generate_identity_document([row("units", "scout", "unit_scout_new", ["new"])])

    def test_generator_excludes_explicit_campaign_only_civilizations(self) -> None:
        document = generate_identity_document(
            [
                row("units", "scout", "unit_scout_campaign", ["aybCmp"]),
                row("units", "spearman", "unit_spearman_eng", ["en"]),
            ]
        )

        self.assertEqual(document["civilizations"], {"english": {"squad": {"spearman": "unit_spearman_eng"}}})

    def test_generator_rejects_malformed_relevant_records(self) -> None:
        malformed = row("units", "scout", "unit_scout_1_eng", ["en"])
        malformed["details_json"] = json.dumps({"baseId": "scout", "attribName": "unit_scout_1_eng"})

        with self.assertRaisesRegex(IdentityGenerationError, "non-empty civs"):
            generate_identity_document([malformed])

    def test_generator_skips_known_playable_translation_sentinel(self) -> None:
        document = generate_identity_document(
            [
                row(
                    "units",
                    "-translation-not-found-11266518",
                    "unit_unavailable",
                    ["horde"],
                    item_id="-translation-not-found-11266518-1",
                    pbgid=9004099,
                ),
                row("units", "scout", "unit_scout_1_eng", ["en"]),
            ]
        )

        self.assertEqual(document["civilizations"], {"english": {"squad": {"scout": "unit_scout_1_eng"}}})

    def test_generator_rejects_unknown_playable_translation_sentinel(self) -> None:
        sentinel = row(
            "units",
            "-translation-not-found-unknown",
            "unit_unknown",
            ["horde"],
            item_id="-translation-not-found-unknown-1",
            pbgid=9999999,
        )

        with self.assertRaisesRegex(IdentityGenerationError, "unknown translation-sentinel PBG ID 9999999"):
            generate_identity_document([sentinel])

    def test_generator_deduplicates_identical_records(self) -> None:
        duplicate = row("units", "scout", "unit_scout_1_eng", ["en"])

        document = generate_identity_document([duplicate, duplicate])

        self.assertEqual(document["civilizations"]["english"]["squad"], {"scout": "unit_scout_1_eng"})

    def test_generator_serialization_is_identical_for_different_input_order(self) -> None:
        rows = [
            row("units", "scout", "unit_scout_1_eng", ["en"]),
            row("buildings", "town-center", "building_town_center_eng", ["en"]),
        ]

        with tempfile.TemporaryDirectory() as temp:
            first = Path(temp) / "first.json"
            second = Path(temp) / "second.json"
            write_identity_document(generate_identity_document(rows), first)
            write_identity_document(generate_identity_document(list(reversed(rows))), second)
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_read_official_rows_uses_read_only_uri_and_filters_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / "identities.sqlite3"
            connection = sqlite3.connect(database)
            self.addCleanup(connection.close)
            connection.execute(
                "CREATE TABLE base_data_entries (category TEXT, item_id TEXT, base_id TEXT, attrib_name TEXT, pbgid INTEGER, details_json TEXT, source_set TEXT)"
            )
            connection.execute(
                "INSERT INTO base_data_entries VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("units", "scout-1", "scout", "unit_scout_1_eng", 1, row("units", "scout", "unit_scout_1_eng", ["en"])["details_json"], "official_base_data"),
            )
            connection.execute(
                "INSERT INTO base_data_entries VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("abilities", "ignored-1", "ignored", "ability_ignored", 2, "{}", "official_base_data"),
            )
            connection.execute(
                "INSERT INTO base_data_entries VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("units", "ignored-1", "ignored", "unit_ignored", 3, "{}", "community_data"),
            )
            connection.commit()
            connection.close()

            with patch("tools.build_orders.identity_generator.sqlite3.connect", wraps=sqlite3.connect) as connect:
                rows = read_official_rows(database)

            self.assertEqual([item["base_id"] for item in rows], ["scout"])
            self.assertEqual(rows[0]["item_id"], "scout-1")
            self.assertEqual(connect.call_args.args[0], f"file:{database.as_posix()}?mode=ro")
            self.assertTrue(connect.call_args.kwargs["uri"])


class IdentityCatalogTests(unittest.TestCase):
    def load_document(self, document: dict[str, object]) -> IdentityCatalog:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "identities.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            return IdentityCatalog.load(path)

    def test_resolves_squad_family_aliases_to_one_immutable_family(self) -> None:
        catalog = IdentityCatalog.load(FIXTURE)
        spearman = catalog.resolve_squad_family("english", "spearman")

        self.assertEqual(spearman.family_id, "spearman")
        self.assertEqual(spearman.canonical_ids, ("unit_spearman_2_eng", "unit_spearman_3_eng"))
        self.assertIsInstance(spearman.canonical_ids, tuple)
        self.assertIs(spearman, catalog.resolve_squad_family("english", "spearman_2"))
        self.assertIs(spearman, catalog.resolve_squad_family("english", "spearman_3"))
        with self.assertRaises(FrozenInstanceError):
            spearman.family_id = "changed"

    def test_resolves_one_member_squad_family(self) -> None:
        catalog = IdentityCatalog.load(FIXTURE)

        scout = catalog.resolve_squad_family("english", "scout")
        self.assertEqual(scout.family_id, "scout")
        self.assertEqual(scout.canonical_ids, ("unit_scout_1_eng",))

    def test_resolves_scalar_entity_and_upgrade_identities(self) -> None:
        catalog = IdentityCatalog.load(FIXTURE)

        self.assertEqual(catalog.resolve("english", "entity", "town_center"), "building_town_center_eng")
        self.assertEqual(catalog.resolve("english", "upgrade", "wheelbarrow"), "upgrade_wheelbarrow_eng")

    def test_rejects_scalar_squad_resolution(self) -> None:
        catalog = IdentityCatalog.load(FIXTURE)

        with self.assertRaisesRegex(IdentityCatalogError, "squad.*resolve_squad_family"):
            catalog.resolve("english", "squad", "spearman")

    def test_rejects_non_normalized_human_id(self) -> None:
        catalog = IdentityCatalog.load(FIXTURE)
        with self.assertRaisesRegex(IdentityCatalogError, "normalized official ID"):
            catalog.resolve("english", "entity", "town-center")

    def test_rejects_numeric_human_id(self) -> None:
        catalog = IdentityCatalog.load(FIXTURE)
        with self.assertRaisesRegex(IdentityCatalogError, "normalized official ID"):
            catalog.resolve("english", "entity", "12345")

    def test_rejects_unknown_civilization_category_and_id(self) -> None:
        catalog = IdentityCatalog.load(FIXTURE)
        for args, fragment in (
            (("unknown", "entity", "town_center"), "unknown civilization"),
            (("english", "ability", "scout"), "unknown category"),
            (("english", "entity", "not_real"), "unknown entity ID"),
        ):
            with self.subTest(args=args), self.assertRaisesRegex(IdentityCatalogError, fragment):
                catalog.resolve(*args)

    def test_normalizes_civilization_identity(self) -> None:
        catalog = IdentityCatalog.load(FIXTURE)
        self.assertEqual(catalog.resolve("English", "entity", "town_center"), "building_town_center_eng")
        self.assertEqual(normalize_identity_id("Town Center"), "town_center")

    def test_freezes_loaded_catalog(self) -> None:
        catalog = IdentityCatalog.load(FIXTURE)
        with self.assertRaises(TypeError):
            catalog.civilizations["english"]["entity"]["town_center"] = "changed"

    def test_rejects_catalog_keys_that_are_not_normalized_official_ids(self) -> None:
        for identifier in ("town-center", "12345"):
            document = {
                "schema_version": 2,
                "source": "official_base_data",
                "civilizations": {"english": {"entity": {identifier: "building_town_center_eng"}}},
            }
            with self.subTest(identifier=identifier), self.assertRaisesRegex(IdentityCatalogError, "normalized official ID"):
                self.load_document(document)

    def test_rejects_missing_or_wrong_catalog_source(self) -> None:
        for source in (None, "unofficial"):
            document: dict[str, object] = {"schema_version": 2, "civilizations": {}}
            if source is not None:
                document["source"] = source
            with self.subTest(source=source), self.assertRaisesRegex(IdentityCatalogError, "official_base_data"):
                self.load_document(document)

    def test_rejects_squad_alias_assigned_to_multiple_families(self) -> None:
        document = {
            "schema_version": 2,
            "source": "official_base_data",
            "civilizations": {
                "english": {
                    "squad": {
                        "spearman": {
                            "aliases": ["shared", "spearman"],
                            "canonical_ids": ["unit_spearman_eng"],
                        },
                        "archer": {
                            "aliases": ["archer", "shared"],
                            "canonical_ids": ["unit_archer_eng"],
                        },
                    }
                }
            },
        }

        with self.assertRaisesRegex(IdentityCatalogError, "shared.*multiple squad families"):
            self.load_document(document)

    def test_rejects_squad_family_without_base_alias(self) -> None:
        document = {
            "schema_version": 2,
            "source": "official_base_data",
            "civilizations": {
                "english": {
                    "squad": {
                        "spearman": {
                            "aliases": ["spearman_2"],
                            "canonical_ids": ["unit_spearman_eng"],
                        }
                    }
                }
            },
        }

        with self.assertRaisesRegex(IdentityCatalogError, "spearman.*aliases"):
            self.load_document(document)

    def test_rejects_squad_family_with_empty_canonical_ids(self) -> None:
        document = {
            "schema_version": 2,
            "source": "official_base_data",
            "civilizations": {
                "english": {
                    "squad": {"spearman": {"aliases": ["spearman"], "canonical_ids": []}}
                }
            },
        }

        with self.assertRaisesRegex(IdentityCatalogError, "canonical_ids.*non-empty"):
            self.load_document(document)

    def test_rejects_squad_family_with_duplicate_canonical_ids(self) -> None:
        document = {
            "schema_version": 2,
            "source": "official_base_data",
            "civilizations": {
                "english": {
                    "squad": {
                        "spearman": {
                            "aliases": ["spearman"],
                            "canonical_ids": ["unit_spearman_eng", "unit_spearman_eng"],
                        }
                    }
                }
            },
        }

        with self.assertRaisesRegex(IdentityCatalogError, "canonical_ids.*unique"):
            self.load_document(document)

    def test_rejects_squad_family_with_unsorted_lists(self) -> None:
        document = {
            "schema_version": 2,
            "source": "official_base_data",
            "civilizations": {
                "english": {
                    "squad": {
                        "spearman": {
                            "aliases": ["spearman_2", "spearman"],
                            "canonical_ids": ["unit_spearman_3_eng", "unit_spearman_2_eng"],
                        }
                    }
                }
            },
        }

        with self.assertRaisesRegex(IdentityCatalogError, "aliases.*sorted"):
            self.load_document(document)


if __name__ == "__main__":
    unittest.main()
