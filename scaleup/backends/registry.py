"""Backend registry (Axis 1.1). Resolve an autopilot family by name and list
what is available. Backends self-register here; adding a third firmware is one
import + one register() call, no changes anywhere else."""
from . import ardupilot, px4

_REGISTRY = {}


def register(backend):
    _REGISTRY[backend.name] = backend


def get(name):
    if name not in _REGISTRY:
        raise KeyError(f"unknown autopilot backend '{name}'. Known: {sorted(_REGISTRY)}")
    return _REGISTRY[name]


def names():
    return sorted(_REGISTRY)


def all_backends():
    return [_REGISTRY[n] for n in names()]


register(ardupilot.backend())
register(px4.backend())
