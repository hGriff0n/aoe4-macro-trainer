import unittest
from pathlib import Path

from tools.build_orders.identities import (
    IdentityCatalog,
    IdentityCatalogError,
    normalize_identity_id,
)


FIXTURE = Path(__file__).parent / "fixtures" / "game_identities" / "minimal.json"


class IdentityCatalogTests(unittest.TestCase):
    def test_resolves_shared_id_by_civilization(self) -> None:
        catalog = IdentityCatalog.load(FIXTURE)
        self.assertEqual(
            catalog.resolve("english", "squad", "scout"),
            "unit_scout_1_eng",
        )
        self.assertEqual(
            catalog.resolve("abbasid", "squad", "scout"),
            "unit_scout_1_abb",
        )

    def test_rejects_non_normalized_human_id(self) -> None:
        catalog = IdentityCatalog.load(FIXTURE)
        with self.assertRaisesRegex(IdentityCatalogError, "normalized official ID"):
            catalog.resolve("english", "entity", "town-center")

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


if __name__ == "__main__":
    unittest.main()
