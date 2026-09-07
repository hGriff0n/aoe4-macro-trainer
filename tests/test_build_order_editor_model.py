import re
import unittest
from pathlib import Path

from tests.scar_runtime import ScarRuntime


ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "assets" / "scar" / "build_orders" / "editor_model.scar"
SCHEMA_PATH = ROOT / "assets" / "scar" / "build_orders" / "editor_schema.scar"


def function_body(source: str, name: str) -> str:
    match = re.search(
        rf"(?:local\s+)?function {re.escape(name)}\([^)]*\)(.*?)(?=^(?:local\s+)?function |\Z)",
        source,
        re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing function {name}")
    return match.group(1)


class BuildOrderEditorModelContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        missing = [path for path in (MODEL_PATH, SCHEMA_PATH) if not path.exists()]
        if missing:
            names = ", ".join(path.name for path in missing)
            raise FileNotFoundError(f"missing editor module(s): {names}")
        cls.model = MODEL_PATH.read_text(encoding="utf-8")
        cls.schema = SCHEMA_PATH.read_text(encoding="utf-8")

    def test_schema_is_recursive_and_adapters_describe_semantic_shapes(self) -> None:
        for constructor in ("Primitive", "Enum", "Object", "Optional", "List"):
            self.assertIn(
                f"function BuildOrderEditorSchema_{constructor}", self.schema
            )

        required_adapters = {
            'alternatives = { min_items = 1 }',
            'resources = { keys = { "food", "wood", "gold", "stone" } }',
            'no_collect = { values = { "food", "wood", "gold", "stone" } }',
            'live_entity = { discovery_kind = "entity" }',
            'live_upgrade = { discovery_kind = "upgrade" }',
            'live_family = { discovery_kind = "family" }',
        }
        for adapter in required_adapters:
            self.assertIn(adapter, self.schema)

    def test_schema_gives_every_runtime_check_kind_an_explicit_field_list(self) -> None:
        for kind in (
            "vils",
            "rallypoint",
            "built",
            "age_up",
            "upgrades",
            "produce",
            "resources",
            "buildings",
            "units",
            "hints",
        ):
            self.assertRegex(
                self.schema,
                rf"(?s)\n\s*{kind}\s*=\s*\{{.*?fields\s*=\s*\{{",
                msg=f"{kind} must declare its own field list",
            )

        self.assertIn('BuildOrderEditorSchema_List("alternatives"', self.schema)
        self.assertIn(', 1, "alternatives")', self.schema)
        self.assertIn('BuildOrderEditorSchema_Primitive("family"', self.schema)
        self.assertIn('"live_family", true, "live_family")', self.schema)

    def test_new_draft_is_blank_and_edit_draft_is_an_isolated_deep_copy(self) -> None:
        new_draft = function_body(self.model, "BuildOrderEditor_NewDraft")
        self.assertIn("original_id = nil", new_draft)
        self.assertIn("civ = civ or \"\"", new_draft)
        self.assertIn('title = ""', new_draft)
        self.assertIn("steps = {}", new_draft)
        self.assertIn("BuildOrderEditor_InferAges(draft)", new_draft)

        edit_draft = function_body(self.model, "BuildOrderEditor_EditDraft")
        self.assertIn("BuildOrderEditor_DeepCopy(order)", edit_draft)
        self.assertIn("draft.original_id = order.id", edit_draft)
        self.assertIn("BuildOrderEditor_FromRuntimeSteps", edit_draft)
        self.assertIn("BuildOrderEditor_InferAges(draft)", edit_draft)

        deep_copy = function_body(self.model, "BuildOrderEditor_DeepCopy")
        self.assertIn("BuildOrderEditor_DeepCopy(key", deep_copy)
        self.assertIn("BuildOrderEditor_DeepCopy(item", deep_copy)

    def test_copy_clears_identity_and_finds_the_first_collision_free_suffix(self) -> None:
        copy_draft = function_body(self.model, "BuildOrderEditor_CopyDraft")
        self.assertIn("draft.original_id = nil", copy_draft)
        self.assertIn('local suffix = " (copy)"', copy_draft)
        self.assertIn('suffix = " (copy " .. copyNumber .. ")"', copy_draft)
        self.assertIn("BuildOrderEditor_MakeID(draft.civ, candidate)", copy_draft)
        self.assertIn("catalog[candidateID] == nil", copy_draft)
        self.assertIn("draft.title = candidate", copy_draft)

    def test_ids_and_check_ids_are_derived_deterministically_from_current_fields(self) -> None:
        make_id = function_body(self.model, "BuildOrderEditor_MakeID")
        self.assertIn("BuildOrderEditor_NormalizeID(civ .. \"-\" .. title)", make_id)

        normalize = function_body(self.model, "BuildOrderEditor_NormalizeID")
        self.assertIn("string.lower(value or \"\")", normalize)
        self.assertIn('string.gsub(normalized, "[^a-z0-9]+", "-")', normalize)
        self.assertIn('string.gsub(normalized, "^-+", "")', normalize)
        self.assertIn('string.gsub(normalized, "-+$", "")', normalize)

        convert = function_body(self.model, "BuildOrderEditor_ToRuntime")
        self.assertIn("BuildOrderEditor_MakeID(draft.civ, draft.title)", convert)
        self.assertIn("kindOccurrences[draftCheck.kind]", convert)
        self.assertIn(
            'orderID .. ":" .. stepIndex .. ":" .. runtimeCheck.kind .. ":" .. occurrence',
            convert,
        )

    def test_move_preserves_relative_order_and_rejects_invalid_indices(self) -> None:
        move = function_body(self.model, "BuildOrderEditor_Move")
        self.assertIn('type(list) ~= "table"', move)
        self.assertIn("fromIndex < 1 or fromIndex > #list", move)
        self.assertIn("toIndex < 1 or toIndex > #list", move)
        self.assertIn("local item = table.remove(list, fromIndex)", move)
        self.assertIn("table.insert(list, toIndex, item)", move)
        self.assertIn('type(list._draft) == "table"', move)
        self.assertIn("BuildOrderEditor_InferAges(list._draft)", move)
        self.assertIn("return true", move)

        from_runtime = function_body(self.model, "BuildOrderEditor_FromRuntimeSteps")
        self.assertIn("for _, runtimeStep in ipairs(runtimeSteps or {}) do", from_runtime)
        self.assertIn("for _, runtimeCheck in ipairs(runtimeStep.checks or {}) do", from_runtime)
        self.assertIn("table.insert(steps, draftStep)", from_runtime)

        infer = function_body(self.model, "BuildOrderEditor_InferAges")
        self.assertIn("draft.steps._draft = draft", infer)
        self.assertIn("step.checks._draft = draft", infer)

    def test_alternatives_adapter_uses_id_for_one_and_ordered_oneof_for_many(self) -> None:
        alternatives = function_body(self.model, "BuildOrderEditor_SetAlternatives")
        self.assertIn("field.id = nil", alternatives)
        self.assertIn("field.oneof = nil", alternatives)
        self.assertIn("if #ids == 1 then", alternatives)
        self.assertIn("field.id = ids[1]", alternatives)
        self.assertIn("elseif #ids > 1 then", alternatives)
        self.assertIn("for _, id in ipairs(ids) do", alternatives)
        self.assertIn("table.insert(field.oneof, id)", alternatives)

        check = function_body(self.model, "BuildOrderEditor_CheckToRuntime")
        self.assertIn('draftCheck.kind == "built"', check)
        self.assertIn('draftCheck.kind == "age_up"', check)
        self.assertIn(
            "BuildOrderEditor_SetAlternatives(payload, draftCheck.payload.alternatives)",
            check,
        )

    def test_unit_cards_emit_the_selected_family_canonical_ids(self) -> None:
        check = function_body(self.model, "BuildOrderEditor_CheckToRuntime")
        self.assertIn('draftCheck.kind == "produce"', check)
        self.assertIn('draftCheck.kind == "units"', check)
        self.assertIn(
            "payload.ids = BuildOrderEditor_GetFamilyIDs(draftCheck.payload.family)",
            check,
        )
        self.assertNotIn("payload.id = draftCheck.payload.family", check)

        family_ids = function_body(self.model, "BuildOrderEditor_GetFamilyIDs")
        self.assertIn("family.ids", family_ids)
        self.assertIn("BuildOrderEditor_DeepCopy", family_ids)

    def test_vils_and_resources_cards_expand_to_runtime_descriptor_shapes(self) -> None:
        check = function_body(self.model, "BuildOrderEditor_CheckToRuntime")
        self.assertIn("BuildOrderEditor_VilsToRuntime", check)
        self.assertIn("BuildOrderEditor_ResourcesToRuntime", check)

        vils = function_body(self.model, "BuildOrderEditor_VilsToRuntime")
        self.assertIn("local thresholds = {}", vils)
        self.assertIn("if next(thresholds) ~= nil then", vils)
        self.assertIn("table.insert(checks,", vils)
        self.assertIn("if noCollect == nil then", vils)
        self.assertIn("for _, resource in ipairs(noCollect) do", vils)
        self.assertIn("no_collect = true", vils)

        resources = function_body(self.model, "BuildOrderEditor_ResourcesToRuntime")
        self.assertIn("for _, resource in ipairs(BUILD_ORDER_EDITOR_RESOURCES) do", resources)
        self.assertIn("resource = resource", resources)
        self.assertIn("count = count", resources)

    def test_inferred_age_is_entering_age_and_only_age_up_advances_next_step(self) -> None:
        infer = function_body(self.model, "BuildOrderEditor_InferAges")
        self.assertIn("local age = 1", infer)
        self.assertIn("step.inferred_age = age", infer)
        self.assertIn('if check.kind == "age_up" then', infer)
        self.assertIn("age = age + 1", infer)
        self.assertIn("if age > BUILD_ORDER_EDITOR_MAX_AGE then", infer)
        self.assertIn("age = BUILD_ORDER_EDITOR_MAX_AGE", infer)
        self.assertIn("break", infer)
        self.assertNotIn('check.kind == "built"', infer)

    def test_age_up_discovery_uses_the_four_upgrade_civs_case_insensitively(self) -> None:
        for civ in ("abbasid", "ayyubids", "templar", "golden_horde"):
            self.assertIn(f"\t{civ} = true,", self.model)

        kind = function_body(self.model, "BuildOrderEditor_GetAgeUpDiscoveryKind")
        self.assertIn('if type(civ) ~= "string" then', kind)
        self.assertIn("string.lower(civ or \"\")", kind)
        self.assertIn('return "upgrade"', kind)
        self.assertIn('return "entity"', kind)

        self.assertIn(
            'live_age_up = { discovery_kinds = { "entity", "upgrade" } }',
            self.schema,
        )
        self.assertRegex(
            self.schema,
            r'BuildOrderEditorSchema_List\("alternatives", "Choices",.*?"live_age_up"\)',
        )

    def test_validation_reports_stable_ordered_dotted_paths(self) -> None:
        validate = function_body(self.model, "BuildOrderEditor_Validate")
        self.assertIn('BuildOrderEditor_AddError(errors, "title"', validate)
        self.assertIn('BuildOrderEditor_AddError(errors, "civ"', validate)
        self.assertIn('BuildOrderEditor_AddError(errors, "steps"', validate)
        self.assertIn('local stepPath = "steps." .. stepIndex', validate)
        self.assertIn('local checkPath = stepPath .. ".checks." .. checkIndex', validate)
        self.assertIn("BuildOrderEditor_ValidateCheck(errors, checkPath", validate)
        self.assertIn("return errors", validate)

        add_error = function_body(self.model, "BuildOrderEditor_AddError")
        self.assertIn("table.insert(errors", add_error)
        self.assertIn("path = path", add_error)
        self.assertIn("message = message", add_error)

    def test_validation_accepts_only_positive_integers_or_unselected_resources(self) -> None:
        positive = function_body(self.model, "BuildOrderEditor_ValidateOptionalPositiveInteger")
        self.assertIn("if value == nil then", positive)
        self.assertIn('type(value) ~= "number"', positive)
        self.assertIn("value <= 0", positive)
        self.assertIn("value ~= math.floor(value)", positive)

        resources = function_body(self.model, "BuildOrderEditor_ValidateResourceFields")
        self.assertIn("for _, resource in ipairs(BUILD_ORDER_EDITOR_RESOURCES) do", resources)
        self.assertIn(
            'BuildOrderEditor_ValidateOptionalPositiveInteger(errors, path .. "." .. resource',
            resources,
        )

        check = function_body(self.model, "BuildOrderEditor_ValidateCheck")
        self.assertIn('path .. ".payload.count"', check)
        self.assertIn(
            'BuildOrderEditor_ValidateResourceFields(errors, path .. ".payload"',
            check,
        )
        self.assertIn('path .. ".payload.no_collect"', check)
        self.assertIn("if noCollect == nil then", check)
        self.assertIn('if type(noCollect) == "table" then', check)
        self.assertIn("noCollectCount = #noCollect", check)
        self.assertNotIn("#(payload.no_collect or {})", check)

    def test_validation_checks_required_lists_and_live_semantic_kinds(self) -> None:
        alternatives = function_body(self.model, "BuildOrderEditor_ValidateAlternatives")
        self.assertIn('type(ids) ~= "table" or #ids == 0', alternatives)
        self.assertIn("BuildOrderEditor_ValidateLiveID", alternatives)
        type_guard = alternatives.find('type(id) ~= "string" or id == ""')
        self.assertGreaterEqual(type_guard, 0)
        self.assertLess(
            type_guard,
            alternatives.index("seen[id]"),
            msg="malformed selections must not be used as Lua table keys",
        )

        live_id = function_body(self.model, "BuildOrderEditor_ValidateLiveID")
        self.assertIn("BuildOrderEditor_DiscoveryHasID", live_id)
        self.assertIn("expectedKinds", live_id)
        self.assertIn('"does not match the required game-data kind"', live_id)

        family = function_body(self.model, "BuildOrderEditor_ValidateFamily")
        self.assertIn("BuildOrderEditor_GetFamilyIDs(family)", family)
        self.assertIn("#ids == 0", family)
        self.assertIn("BuildOrderEditor_DiscoveryHasFamily", family)

    def test_runtime_conversion_refuses_invalid_drafts_and_preserves_step_order(self) -> None:
        convert = function_body(self.model, "BuildOrderEditor_ToRuntime")
        self.assertIn("local errors = BuildOrderEditor_Validate(draft, nil)", convert)
        self.assertIn("if #errors > 0 then", convert)
        self.assertIn("return nil, nil", convert)
        self.assertIn("for stepIndex, draftStep in ipairs(draft.steps) do", convert)
        self.assertIn("for _, draftCheck in ipairs(draftStep.checks) do", convert)
        self.assertIn("table.insert(runtimeSteps, runtimeStep)", convert)
        self.assertIn("return orderID, buildOrder", convert)

    def test_constant_production_is_always_optional_at_runtime(self) -> None:
        check = function_body(self.model, "BuildOrderEditor_CheckToRuntime")
        self.assertIn("local optional = draftCheck.optional == true", check)
        self.assertIn("if draftCheck.kind == \"produce\" and payload.constant then", check)
        self.assertIn("optional = true", check)
        self.assertIn("optional = optional", check)

    def test_titles_are_derived_from_current_canonical_fields_not_author_aliases(self) -> None:
        title = function_body(self.model, "BuildOrderEditor_MakeCheckTitle")
        self.assertIn("BuildOrderEditor_GetSelectionLabel", title)
        self.assertIn("BuildOrderEditor_HumanizeID", title)
        self.assertIn('return "Build "', title)
        self.assertIn('return "Age up: "', title)
        self.assertIn('return "Assign "', title)
        self.assertNotIn("author", title.lower())


class BuildOrderEditorModelBehaviorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runtime = ScarRuntime(MODEL_PATH.read_text(encoding="utf-8"))

    def valid_draft(
        self, checks: list[dict[str, object]], title: str = "Plan"
    ) -> dict[str, object]:
        return {
            "original_id": None,
            "civ": "english",
            "title": title,
            "steps": [{"title": "Opening", "checks": checks}],
        }

    def test_draft_lifecycle_deep_copies_and_copy_suffixes_are_collision_free(self) -> None:
        blank = self.runtime.call("BuildOrderEditor_NewDraft", "english")
        self.assertEqual(blank["civ"], "english")
        self.assertEqual(blank["title"], "")
        self.assertEqual(blank["steps"].array(), [])
        self.assertIsNone(blank["original_id"])

        source = self.runtime.table(
            {
                "id": "english-plan",
                "civ": "english",
                "title": "Plan",
                "steps": [
                    {
                        "title": "Opening",
                        "checks": [
                            {
                                "id": "english-plan:1:hints:1",
                                "kind": "hints",
                                "title": "[HINT] Scout",
                                "optional": True,
                                "payload": {"text": "Scout"},
                            }
                        ],
                    }
                ],
            }
        )
        edit = self.runtime.call("BuildOrderEditor_EditDraft", source)
        self.assertEqual(edit["original_id"], "english-plan")
        self.assertEqual(edit["original_civ"], "english")
        self.assertEqual(edit["original_title"], "Plan")
        edit["steps"][1]["title"] = "Changed"
        edit["steps"][1]["checks"][1]["payload"]["text"] = "Changed hint"
        self.assertEqual(source["steps"][1]["title"], "Opening")
        self.assertEqual(source["steps"][1]["checks"][1]["payload"]["text"], "Scout")

        catalog = {
            "english-plan-copy": {},
            "english-plan-copy-2": {},
        }
        copied = self.runtime.call("BuildOrderEditor_CopyDraft", source, catalog)
        self.assertIsNone(copied["original_id"])
        self.assertIsNone(copied["original_civ"])
        self.assertIsNone(copied["original_title"])
        self.assertEqual(copied["title"], "Plan (copy 3)")

    def test_alternatives_and_unit_families_convert_to_canonical_runtime_payloads(self) -> None:
        one = self.runtime.call(
            "BuildOrderEditor_SetAlternatives",
            {},
            ["building_barracks_eng"],
        )
        self.assertEqual(one["id"], "building_barracks_eng")
        self.assertIsNone(one["oneof"])

        many = self.runtime.call(
            "BuildOrderEditor_SetAlternatives",
            {},
            ["building_barracks_eng", "building_archery_range_eng"],
        )
        self.assertIsNone(many["id"])
        self.assertEqual(
            many["oneof"].array(),
            ["building_barracks_eng", "building_archery_range_eng"],
        )

        draft = self.valid_draft(
            [
                {
                    "kind": "built",
                    "optional": False,
                    "payload": {
                        "alternatives": ["building_barracks_eng"],
                        "count": 1,
                    },
                },
                {
                    "kind": "age_up",
                    "optional": False,
                    "payload": {
                        "alternatives": [
                            "building_landmark_age2_eng",
                            "building_town_center_eng",
                        ]
                    },
                },
                {
                    "kind": "units",
                    "optional": False,
                    "payload": {
                        "family": {
                            "label": "Spearman",
                            "ids": [
                                "unit_spearman_1_eng",
                                "unit_spearman_2_eng",
                            ],
                        },
                        "count": 2,
                    },
                },
            ],
            title="Conversion",
        )
        new_id, order = self.runtime.call("BuildOrderEditor_ToRuntime", draft)
        self.assertEqual(new_id, "english-conversion")
        checks = order["steps"][1]["checks"].array()
        self.assertEqual(checks[0]["payload"]["id"], "building_barracks_eng")
        self.assertIsNone(checks[0]["payload"]["oneof"])
        self.assertEqual(
            checks[1]["payload"]["oneof"].array(),
            ["building_landmark_age2_eng", "building_town_center_eng"],
        )
        self.assertIsNone(checks[1]["payload"]["id"])
        self.assertEqual(
            checks[2]["payload"]["ids"].array(),
            ["unit_spearman_1_eng", "unit_spearman_2_eng"],
        )
        self.assertIsNone(checks[2]["payload"]["id"])
        self.assertEqual(
            [check["id"] for check in checks],
            [
                "english-conversion:1:built:1",
                "english-conversion:1:age_up:1",
                "english-conversion:1:units:1",
            ],
        )

    def test_vils_and_resources_expand_in_card_and_resource_order(self) -> None:
        draft = self.valid_draft(
            [
                {
                    "kind": "vils",
                    "optional": False,
                    "payload": {
                        "food": 7,
                        "wood": 3,
                        "no_collect": ["gold", "stone"],
                    },
                },
                {
                    "kind": "resources",
                    "optional": False,
                    "payload": {"food": 100, "stone": 200},
                },
            ],
            title="Economy",
        )
        _, order = self.runtime.call("BuildOrderEditor_ToRuntime", draft)
        checks = order["steps"][1]["checks"].array()
        self.assertEqual(
            [check["kind"] for check in checks],
            ["vils", "vils", "vils", "resources", "resources"],
        )
        self.assertEqual(checks[0]["payload"]["food"], 7)
        self.assertEqual(checks[0]["payload"]["wood"], 3)
        self.assertEqual(
            [(check["payload"]["resource"], check["payload"]["no_collect"]) for check in checks[1:3]],
            [("gold", True), ("stone", True)],
        )
        self.assertEqual(
            [(check["payload"]["resource"], check["payload"]["count"]) for check in checks[3:]],
            [("food", 100), ("stone", 200)],
        )

    def test_add_delete_and_reorder_recompute_entering_ages(self) -> None:
        normal_step = lambda title: {
            "title": title,
            "checks": [{"kind": "hints", "optional": True, "payload": {"text": title}}],
        }
        age_step = {
            "title": "Age",
            "checks": [
                {
                    "kind": "age_up",
                    "optional": False,
                    "payload": {"alternatives": ["landmark"]},
                }
            ],
        }
        draft = self.runtime.table(
            {
                "civ": "english",
                "title": "Ages",
                "steps": [normal_step("One"), normal_step("Two")],
            }
        )
        self.runtime.call("BuildOrderEditor_InferAges", draft)
        self.assertEqual([step["inferred_age"] for step in draft["steps"].array()], [1, 1])

        draft["steps"].append(self.runtime.table(age_step))
        self.runtime.call("BuildOrderEditor_InferAges", draft)
        self.assertEqual([step["inferred_age"] for step in draft["steps"].array()], [1, 1, 1])

        self.assertTrue(self.runtime.call("BuildOrderEditor_Move", draft["steps"], 3, 1))
        self.assertEqual([step["inferred_age"] for step in draft["steps"].array()], [1, 2, 2])

        draft["steps"].delete_at(1)
        self.runtime.call("BuildOrderEditor_InferAges", draft)
        self.assertEqual([step["inferred_age"] for step in draft["steps"].array()], [1, 1])

    def test_unchanged_unicode_title_preserves_original_id_but_rename_derives_one(self) -> None:
        source = {
            "id": "english-cafe",
            "civ": "english",
            "title": "Café",
            "steps": [
                {
                    "title": "Opening",
                    "checks": [
                        {
                            "id": "english-cafe:1:hints:1",
                            "kind": "hints",
                            "title": "[HINT] Scout",
                            "optional": True,
                            "payload": {"text": "Scout"},
                        }
                    ],
                }
            ],
        }
        draft = self.runtime.call("BuildOrderEditor_EditDraft", source)
        unchanged_id, unchanged = self.runtime.call("BuildOrderEditor_ToRuntime", draft)
        self.assertEqual(unchanged_id, "english-cafe")
        self.assertEqual(unchanged["id"], "english-cafe")

        draft["title"] = "Cafe Fast"
        renamed_id, renamed = self.runtime.call("BuildOrderEditor_ToRuntime", draft)
        self.assertEqual(renamed_id, "english-cafe-fast")
        self.assertEqual(renamed["id"], "english-cafe-fast")

        draft = self.runtime.call("BuildOrderEditor_EditDraft", source)
        draft["civ"] = "french"
        reciv_id, reciv = self.runtime.call("BuildOrderEditor_ToRuntime", draft)
        self.assertEqual(reciv_id, "french-caf")
        self.assertEqual(reciv["id"], "french-caf")

    def test_false_no_collect_is_rejected_instead_of_defaulted(self) -> None:
        draft = self.valid_draft(
            [
                {
                    "kind": "vils",
                    "optional": False,
                    "payload": {"food": 7, "no_collect": False},
                }
            ]
        )
        errors = self.runtime.call("BuildOrderEditor_Validate", draft, None)
        self.assertIn(
            "steps.1.checks.1.payload.no_collect",
            [error["path"] for error in errors.array()],
        )
        self.assertEqual(
            self.runtime.call("BuildOrderEditor_ToRuntime", draft),
            (None, None),
        )

    def test_hints_are_optional_and_optional_upgrade_title_is_explicit(self) -> None:
        imported_hint = self.runtime.call(
            "BuildOrderEditor_FromRuntimeCheck",
            {
                "kind": "hints",
                "optional": False,
                "payload": {"text": "Scout"},
            },
        )
        self.assertTrue(imported_hint["optional"])

        draft = self.valid_draft(
            [
                {
                    "kind": "hints",
                    "optional": False,
                    "payload": {"text": "Scout"},
                },
                {
                    "kind": "upgrades",
                    "optional": True,
                    "payload": {"id": "wheelbarrow", "queued": False},
                },
            ],
            title="Guidance",
        )
        _, order = self.runtime.call("BuildOrderEditor_ToRuntime", draft)
        hint, upgrade = order["steps"][1]["checks"].array()
        self.assertTrue(hint["optional"])
        self.assertEqual(hint["title"], "[HINT] Scout")
        self.assertTrue(upgrade["optional"])
        self.assertEqual(upgrade["title"], "[Optional] Research wheelbarrow")
        queued_title = self.runtime.call(
            "BuildOrderEditor_MakeCheckTitle",
            {
                "kind": "upgrades",
                "optional": True,
                "payload": {"id": "wheelbarrow", "queued": True},
            },
            {},
        )
        self.assertEqual(queued_title, "[Optional] Queue wheelbarrow for research")


if __name__ == "__main__":
    unittest.main()
