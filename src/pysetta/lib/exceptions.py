from __future__ import annotations

from itertools import chain
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


class MissingProjectRootError(FileNotFoundError):
    __slots__ = ()

    def __init__(self, cwd: Path) -> None:
        super().__init__("Couldn't find a project root directory")
        self.__notes__ = list(
            chain(
                ["Locations searched:"],
                (f"    * {path.joinpath('.euler')}" for path in cwd.parents),
            )
        )


class IncompleteTranslationsError(KeyError):
    __slots__ = ()
