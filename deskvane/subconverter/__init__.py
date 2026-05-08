from .server import SubconverterServer

__all__ = ["SubconverterServer", "SubconverterDialog"]


def __getattr__(name: str):
    if name == "SubconverterDialog":
        from .gui import SubconverterDialog

        return SubconverterDialog
    raise AttributeError(name)
