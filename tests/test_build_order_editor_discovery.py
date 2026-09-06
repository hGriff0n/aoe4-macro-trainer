import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DISCOVERY_SCAR = ROOT / "assets" / "scar" / "build_orders" / "editor_discovery.scar"


def function_body(source: str, name: str) -> str:
    match = re.search(
        rf"^function {re.escape(name)}\([^\n]*\)\n(.*?)(?=^function |\Z)",
        source,
        flags=re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing function {name}")
    return match.group(1)


class BuildOrderEditorDiscoveryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not DISCOVERY_SCAR.exists():
            raise AssertionError(f"missing discovery module: {DISCOVERY_SCAR}")
        cls.source = DISCOVERY_SCAR.read_text(encoding="utf-8")

    def test_exports_the_discovery_contract(self) -> None:
        for name in (
            "BuildOrderDiscovery_GetAge",
            "BuildOrderDiscovery_GetPresentation",
            "BuildOrderDiscovery_BelongsToRace",
            "BuildOrderDiscovery_CollectFamilies",
            "BuildOrderDiscovery_Sort",
            "BuildOrderDiscovery_Collect",
            "BuildOrderDiscovery_Filter",
            "BuildOrderDiscovery_Clear",
        ):
            with self.subTest(name=name):
                function_body(self.source, name)

    def test_collect_derives_civilization_from_the_supplied_player(self) -> None:
        body = function_body(self.source, "BuildOrderDiscovery_Collect")
        self.assertIn("local race = Player_GetRace(player)", body)
        self.assertIn("civ = race", body)
        self.assertIn("civ_name = Player_GetRaceName(player)", body)

    def test_collect_enumerates_all_three_property_bag_groups(self) -> None:
        body = function_body(self.source, "BuildOrderDiscovery_Collect")
        for pbg_type in (
            "PBG_EntityProperties",
            "PBG_SquadProperties",
            "PBG_UpgradeProperties",
        ):
            with self.subTest(pbg_type=pbg_type):
                self.assertIn(f"BP_GetPropertyBagGroupCount({pbg_type})", body)
                self.assertIn(f"BP_GetPropertyBagGroupPathName({pbg_type}, index)", body)

    def test_collection_builds_the_complete_snapshot_shape(self) -> None:
        body = function_body(self.source, "BuildOrderDiscovery_Collect")
        for field in ("entities = {}", "squads = {}", "upgrades = {}", "families = {}"):
            with self.subTest(field=field):
                self.assertIn(field, body)
        self.assertIn("snapshot.families = BuildOrderDiscovery_CollectFamilies", body)

    def test_entity_and_squad_membership_use_race_extensions(self) -> None:
        body = function_body(self.source, "BuildOrderDiscovery_BelongsToRace")
        for call in (
            "BP_GetEntityTypeExtRaceCount(pathName)",
            "BP_GetEntityTypeExtRaceBlueprintAtIndex(pathName, index)",
            "BP_GetSquadTypeExtRaceCount(pathName)",
            "BP_GetSquadTypeExtRaceBlueprintAtIndex(pathName, index)",
        ):
            with self.subTest(call=call):
                self.assertIn(call, body)
        self.assertIn("== race", body)

    def test_collection_filters_entities_and_squads_by_race(self) -> None:
        body = function_body(self.source, "BuildOrderDiscovery_Collect")
        self.assertIn('BuildOrderDiscovery_BelongsToRace("entity", pathName, race)', body)
        self.assertIn('BuildOrderDiscovery_BelongsToRace("squad", pathName, race)', body)

    def test_age_uses_official_blueprint_type_predicates(self) -> None:
        body = function_body(self.source, "BuildOrderDiscovery_GetAge")
        self.assertIn("for age = 2, 4 do", body)
        self.assertIn("Entity_IsEBPOfType(pbg, ageType)", body)
        self.assertIn("Squad_IsSBPOfType(pbg, ageType)", body)
        self.assertIn("BP_IsUpgradeOfType(pbg, ageType)", body)
        self.assertNotIn("Player_CanConstruct", body)

    def test_collection_resolves_each_property_bag_blueprint(self) -> None:
        body = function_body(self.source, "BuildOrderDiscovery_Collect")
        self.assertIn("BP_GetEntityBlueprint(pathName)", body)
        self.assertIn("BP_GetSquadBlueprint(pathName)", body)
        self.assertIn("BP_GetUpgradeBlueprint(pathName)", body)

    def test_presentation_uses_kind_specific_ui_info(self) -> None:
        body = function_body(self.source, "BuildOrderDiscovery_GetPresentation")
        self.assertIn("BP_GetEntityUIInfo(pbg)", body)
        self.assertIn("BP_GetSquadUIInfo(pbg, race)", body)
        self.assertIn("BP_GetUpgradeUIInfo(pbg)", body)
        self.assertIn("Loc_ToAnsi(uiInfo.screenName)", body)
        self.assertIn("uiInfo.iconName", body)

    def test_normalization_keeps_explicit_age_label_and_icon_fallbacks(self) -> None:
        self.assertIn("local age = discoveredAge or 1", self.source)
        self.assertIn("local label = discoveredLabel or pathName", self.source)
        self.assertIn(
            "local icon = discoveredIcon or BUILD_ORDER_DISCOVERY_DEFAULT_ICONS[kind]",
            self.source,
        )

    def test_scalar_options_use_id_and_not_ids(self) -> None:
        body = function_body(self.source, "BuildOrderDiscovery_CreateOption")
        self.assertIn("id = pathName", body)
        self.assertIn("ids = nil", body)
        self.assertIn("kind = kind", body)
        self.assertIn("age = age", body)
        self.assertIn("label = label", body)
        self.assertIn("icon = icon", body)

    def test_families_use_official_archetypes_and_keep_all_compatible_ids(self) -> None:
        body = function_body(self.source, "BuildOrderDiscovery_CollectFamilies")
        self.assertIn("AI_CombatFitnessGetSquadArchetypeNames()", body)
        self.assertIn("AI_CombatFitnessGetSquadArchetypePBGs(archetypeName)", body)
        self.assertIn("BP_GetName(pbg)", body)
        self.assertIn('BuildOrderDiscovery_BelongsToRace("squad", pathName, race)', body)
        self.assertIn("table.insert(members", body)
        self.assertIn("ids = ids", body)
        self.assertIn('kind = "family"', body)

    def test_family_ids_are_ordered_by_age_then_internal_id(self) -> None:
        body = function_body(self.source, "BuildOrderDiscovery_CollectFamilies")
        sort_call = body.index("table.sort(members")
        age_comparison = body.index("left.age ~= right.age", sort_call)
        id_comparison = body.index("left.id < right.id", age_comparison)
        ids_projection = body.index("table.insert(ids, member.id)", id_comparison)
        self.assertLess(sort_call, age_comparison)
        self.assertLess(age_comparison, id_comparison)
        self.assertLess(id_comparison, ids_projection)

    def test_sort_orders_case_insensitive_labels_then_id(self) -> None:
        body = function_body(self.source, "BuildOrderDiscovery_Sort")
        self.assertIn("string.lower(left.label)", body)
        self.assertIn("string.lower(right.label)", body)
        self.assertIn("BuildOrderDiscovery_GetSortID(left)", body)
        self.assertIn("BuildOrderDiscovery_GetSortID(right)", body)

    def test_collect_sorts_every_option_list(self) -> None:
        body = function_body(self.source, "BuildOrderDiscovery_Collect")
        for field in ("entities", "squads", "upgrades", "families"):
            with self.subTest(field=field):
                self.assertIn(f"BuildOrderDiscovery_Sort(snapshot.{field})", body)

    def test_filter_retains_only_kind_records_at_or_below_maximum_age(self) -> None:
        body = function_body(self.source, "BuildOrderDiscovery_Filter")
        self.assertIn("local listName = BUILD_ORDER_DISCOVERY_LISTS[kind]", body)
        self.assertIn("local options = snapshot[listName] or {}", body)
        self.assertIn("if option.age <= maximumAge then", body)
        self.assertIn("table.insert(filtered, option)", body)

    def test_each_collect_replaces_transient_state_and_clear_only_releases_it(self) -> None:
        collect = function_body(self.source, "BuildOrderDiscovery_Collect")
        clear = function_body(self.source, "BuildOrderDiscovery_Clear")
        self.assertIn("BUILD_ORDER_DISCOVERY_CURRENT = snapshot", collect)
        self.assertIn("BUILD_ORDER_DISCOVERY_CURRENT = nil", clear)
        self.assertNotIn("return BUILD_ORDER_DISCOVERY_CURRENT", collect)
        self.assertNotIn("entities = nil", clear)
        self.assertNotIn("squads = nil", clear)
        self.assertNotIn("upgrades = nil", clear)
        self.assertNotIn("families = nil", clear)


if __name__ == "__main__":
    unittest.main()
