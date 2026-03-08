from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from .main_window import NovelGeneratorGUI

__all__ = ["NovelGeneratorGUI"]


def __getattr__(name: str) -> type[NovelGeneratorGUI]:
    if name != "NovelGeneratorGUI":
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    value = cast(type[NovelGeneratorGUI], getattr(import_module(".main_window", __name__), name))
    globals()[name] = value
    return value
