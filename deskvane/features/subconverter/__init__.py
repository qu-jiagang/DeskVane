from .state import SubconverterState

__all__ = ["SubconverterFeatureModule", "SubconverterState"]


def __getattr__(name: str):
    if name == "SubconverterFeatureModule":
        from .module import SubconverterFeatureModule

        return SubconverterFeatureModule
    raise AttributeError(name)
