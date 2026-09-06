import re
import unittest
from pathlib import Path


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
        self.assertIn("for _, resource in ipairs(payload.no_collect or {}) do", vils)
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
        self.assertIn('if type(payload.no_collect) == "table" then', check)
        self.assertIn("noCollectCount = #payload.no_collect", check)
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


if __name__ == "__main__":
    unittest.main()
