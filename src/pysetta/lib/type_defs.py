from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from pathlib import Path

    from pysetta.lib.utils import Translation

JSONType = str | int | float | bool | None | list["JSONType"] | dict[str, "JSONType"]
Translations = dict[str, "Translation"]


class Extracted(TypedDict):
    translations: dict[Path, Translations]
    paths: dict[str, list[Path]]
