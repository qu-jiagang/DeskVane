from .state import TranslatorState

__all__ = ["TranslatorFeatureModule", "TranslatorState"]


def __getattr__(name: str):
    if name == "TranslatorFeatureModule":
        from .module import TranslatorFeatureModule

        return TranslatorFeatureModule
    raise AttributeError(name)
