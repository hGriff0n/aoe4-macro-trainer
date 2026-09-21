from aoe4.build_orders.types import CheckRegistry

from aoe4.build_orders.checks.ageup import AgeUpCheck
from aoe4.build_orders.checks.buildings import BuiltCheck
from aoe4.build_orders.checks.other import HintCheck, RallypointCheck
from aoe4.build_orders.checks.resources import ResourceCheck
from aoe4.build_orders.checks.tech import UpgradeCheck
from aoe4.build_orders.checks.units import ProductionCheck, UnitCheck
from aoe4.build_orders.checks.vils import VilCheck

_registry = CheckRegistry()

if AgeUpCheck not in _registry:
    _registry.register(AgeUpCheck)
if BuiltCheck not in _registry:
    _registry.register(BuiltCheck)
if HintCheck not in _registry:
    _registry.register(HintCheck)
if RallypointCheck not in _registry:
    _registry.register(RallypointCheck)
if ResourceCheck not in _registry:
    _registry.register(ResourceCheck)
if UpgradeCheck not in _registry:
    _registry.register(UpgradeCheck)
if ProductionCheck not in _registry:
    _registry.register(ProductionCheck)
if UnitCheck not in _registry:
    _registry.register(UnitCheck)
if VilCheck not in _registry:
    _registry.register(VilCheck)
