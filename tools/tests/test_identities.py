import pytest

from aoe4 import aoe4world
import aoe4.build_orders.checks.register_all as _  # checks registered to singleton
from aoe4.build_orders import identities
from aoe4.build_orders.checks.tech import UpgradeCheck
from aoe4.build_orders.types import CheckRegistry
from aoe4.constants import TECHNOLOGIES, UNITS, UPGRADES


def _family(id, *variations):
    return {'id': id, 'variations': [{'id': v, 'attribName': a} for v, a in variations]}


SPEARMAN = _family(
    "spearman", ("spearman-2", "unit_spearman_2_eng"), ("spearman-3", "unit_spearman_3_eng"))
CULTURE_WING = _family(
    "culture-wing", ("culture-wing-1", "upgrade_add_culture_wing"),
    ("culture-wing-2", "upgrade_add_culture_wing_feudal"))
WHEELBARROW = _family(
    "wheelbarrow", ("wheelbarrow-1", "upgrade_unit_town_center_wheelbarrow_1"))


def test_unit_family_and_aliases_resolve_to_whole_family():
    ids = identities.author_ids_from_families(UNITS, [SPEARMAN])
    family = ["unit_spearman_2_eng", "unit_spearman_3_eng"]
    assert identities.resolve_ids(ids, UNITS, ["spearman"]) == family
    assert identities.resolve_ids(ids, UNITS, ["spearman_3"]) == family
    assert identities.reverse_ids(ids, family) == ["spearman"]


def test_family_resolves_every_age_and_variations_one():
    ids = identities.author_ids_from_families(TECHNOLOGIES, [CULTURE_WING, WHEELBARROW])
    family = ["upgrade_add_culture_wing", "upgrade_add_culture_wing_feudal"]
    assert identities.resolve_ids(ids, TECHNOLOGIES, ["culture_wing"]) == family
    assert identities.resolve_ids(ids, TECHNOLOGIES, ["culture_wing_2"]) == ["upgrade_add_culture_wing_feudal"]
    assert identities.reverse_ids(ids, family) == ["culture_wing"]
    assert identities.reverse_ids(ids, ["upgrade_add_culture_wing_feudal"]) == ["culture_wing_2"]
    assert identities.reverse_ids(ids, ["upgrade_unit_town_center_wheelbarrow_1"]) == ["wheelbarrow"]


def test_oneof_without_a_covering_family_reverses_each_id():
    ids = identities.author_ids_from_families(TECHNOLOGIES, [CULTURE_WING, WHEELBARROW])
    game_ids = ["upgrade_add_culture_wing_feudal", "upgrade_unit_town_center_wheelbarrow_1"]
    assert identities.reverse_ids(ids, game_ids) == ["culture_wing_2", "wheelbarrow"]


def test_upgrade_family_round_trips(monkeypatch):
    ids = identities.author_ids_from_families(TECHNOLOGIES, [CULTURE_WING])
    monkeypatch.setattr(identities, "_civ_author_ids", lambda civ, category: ids)
    factory = CheckRegistry()[UpgradeCheck]
    check, = factory.from_yaml([{'id': "culture_wing", 'queued': True}], "abbasid")
    stored, = factory.to_datastore(check)
    assert stored['payload'] == {'oneof': ["upgrade_add_culture_wing", "upgrade_add_culture_wing_feudal"], 'queued': True}
    assert factory.to_yaml(factory.from_datastore(stored, "abbasid"), "abbasid") == [{'id': "culture_wing", 'queued': True}]


def test_game_ids_pass_through_and_unknown_ids_raise():
    ids = identities.author_ids_from_families(TECHNOLOGIES, [WHEELBARROW])
    assert identities.resolve_ids(ids, TECHNOLOGIES, ["upgrade_unit_town_center_wheelbarrow_1"]) == ["upgrade_unit_town_center_wheelbarrow_1"]
    with pytest.raises(ValueError):
        identities.resolve_ids(ids, TECHNOLOGIES, ["not_a_tech"])


def test_missing_data_passes_ids_through():
    assert identities.resolve_ids(None, UNITS, ["spearman"]) == ["spearman"]
    assert identities.reverse_ids(None, ["unit_spearman_2_eng"]) == ["unit_spearman_2_eng"]


def test_upgrades_cover_technologies_and_unit_upgrades(monkeypatch):
    VETERAN_SPEARMEN = _family("veteran-spearmen", ("veteran-spearmen-3", "upgrade_unit_spearman_3"))
    upstream = {TECHNOLOGIES: [WHEELBARROW], UPGRADES: [VETERAN_SPEARMEN]}
    monkeypatch.setattr(aoe4world, "load_unified", lambda category, civ: upstream[category])
    identities._civ_author_ids.cache_clear()
    assert identities.resolve("english", UPGRADES, ["wheelbarrow", "veteran_spearmen"]) == [
        "upgrade_unit_town_center_wheelbarrow_1", "upgrade_unit_spearman_3"]
    identities._civ_author_ids.cache_clear()
