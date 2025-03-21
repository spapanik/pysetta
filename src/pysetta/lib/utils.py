from __future__ import annotations

import re
from dataclasses import dataclass
from functools import partial
from hashlib import sha3_224
from pathlib import Path
from typing import TYPE_CHECKING

from dj_settings import get_setting
from ruamel.yaml import YAML
from ruamel.yaml.compat import StringIO
from ruamel.yaml.scalarstring import DoubleQuotedScalarString, LiteralScalarString

from pysetta.lib.constants import CONFIG_DIR_NAME, CONFIG_FILE_NAME, TRANSLATION_SUFFIX
from pysetta.lib.exceptions import MissingProjectRootError

if TYPE_CHECKING:
    from typing_extensions import Self

    from pysetta.lib.type_defs import JSONType, Translations


@dataclass(frozen=True, slots=True)
class PathData:
    path: Path
    language_code: str
    content: str


@dataclass(frozen=True, slots=True)
class TagData:
    key: str
    original: str
    comments: tuple[str, ...]

    @classmethod
    def from_text(cls, inner_text: str) -> Self:
        stripped = inner_text.strip()
        key = sha3_224(stripped.encode()).hexdigest()
        original = stripped
        comments = ()

        try:
            empty, key, original = stripped.split("::", maxsplit=2)
        except ValueError:
            original = stripped
        else:
            if empty == "":
                comments = tuple(sorted(key.split("//")))  # type: ignore[assignment]
            else:
                original = stripped

        return cls(key=key, original=original, comments=comments)


@dataclass(frozen=True, slots=True)
class Formatter:
    suffix: str
    command: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Paths:
    translations: Path
    translated: Path


@dataclass(frozen=True, slots=True)
class Language:
    code: str
    is_default: bool
    construction_message: str
    translations_dir: Path
    translated_dir: Path

    def get_translations_path(self, template: Path, config: Config) -> Path:
        relative_path = template.relative_to(config.templates)
        suffix = f"{relative_path.suffix}{TRANSLATION_SUFFIX}"
        return self.translations_dir.joinpath(relative_path).with_suffix(suffix)

    def get_translated_path(self, template: Path, config: Config) -> Path:
        relative_path = template.relative_to(config.templates)
        return self.translated_dir.joinpath(relative_path)


@dataclass(frozen=True, slots=True)
class Boundary:
    opening: str
    closing: str

    @property
    def regex(self) -> re.Pattern[str]:
        opening = re.escape(self.opening)
        closing = re.escape(self.closing)
        return re.compile(rf"{opening}(?P<inner_text>.*?){closing}")


@dataclass(frozen=True, slots=True)
class Boundaries:
    translation: Boundary
    literal: Boundary
    mark: Boundary


@dataclass(frozen=True, slots=True)
class Config:
    languages: tuple[Language, ...]
    templates: Path
    strict: bool
    formatters: tuple[Formatter, ...]
    boundaries: Boundaries


@dataclass(frozen=True, slots=True)
class Translation:
    key: str
    original: str
    translated: str
    comments: tuple[str, ...]
    literals: tuple[str, ...]

    @classmethod
    def from_text(cls, inner_text: str, boundary: Boundary) -> Self:
        tag_data = TagData.from_text(inner_text)
        literals = set(boundary.regex.findall(tag_data.original))
        return cls(
            key=tag_data.key,
            original=tag_data.original,
            translated="",
            comments=tag_data.comments,
            literals=tuple(sorted(literals)),
        )

    @staticmethod
    def _prepare_str(string: str) -> str:
        if "\n" in string:
            return LiteralScalarString(string)
        return string or DoubleQuotedScalarString("")

    def as_json(self) -> JSONType:
        base: dict[str, JSONType] = {
            "original": self._prepare_str(self.original),
            "translated": self._prepare_str(self.translated),
        }
        if self.comments:
            base["comments"] = list(self.comments)
        if self.literals:
            base["literals"] = list(self.literals)
        return base

    def get_text(self) -> str:
        return self.translated


def _get_project_dir() -> Path:
    cwd = Path.cwd().resolve()
    while not cwd.joinpath(CONFIG_DIR_NAME).is_dir():
        if cwd.as_posix() == "/":
            raise MissingProjectRootError(cwd)
        cwd = cwd.parent
    return cwd


def get_config(required_languages: list[str]) -> Config:
    project_dir = _get_project_dir()
    get_pysetta_setting = partial(
        get_setting,
        use_env=False,
        project_dir=project_dir.joinpath(CONFIG_DIR_NAME),
        filename=CONFIG_FILE_NAME,
    )

    all_languages: dict[str, str] = get_pysetta_setting(
        "others", sections=["languages"], rtype=dict
    )
    default_language: str = get_pysetta_setting(
        "default", sections=["languages"], rtype=str
    )
    all_languages[default_language] = "__default__"
    if required_languages:
        all_languages = {
            key: value
            for key, value in all_languages.items()
            if key in required_languages
        }

    strict_mode = get_pysetta_setting(
        "strict", sections=["app"], rtype=bool, default=False
    )

    formatters_config: dict[str, list[str]] = get_pysetta_setting(
        "formatters", sections=["utils"], rtype=dict, default={}
    )

    templates: str = get_pysetta_setting("templates", sections=["paths"])
    translations: str = get_pysetta_setting("translations", sections=["paths"])
    translated: str = get_pysetta_setting("translated", sections=["paths"])

    translation_boundary: dict[str, str] = get_pysetta_setting(
        "translation", sections=["boundaries"], rtype=dict
    )
    literal_boundary: dict[str, str] = get_pysetta_setting(
        "literal", sections=["boundaries"], rtype=dict
    )
    mark_boundary: dict[str, str] = get_pysetta_setting(
        "mark", sections=["boundaries"], rtype=dict
    )

    boundaries = Boundaries(
        translation=Boundary(**translation_boundary),
        literal=Boundary(**literal_boundary),
        mark=Boundary(**mark_boundary),
    )

    languages = []
    formatters = tuple(
        Formatter(suffix=suffix, command=tuple(formatter_command))
        for suffix, formatter_command in formatters_config.items()
    )

    for language_code, construction_message in all_languages.items():
        language_translations = project_dir.joinpath(
            translations.format(language=language_code)
        ).absolute()

        language_translated = project_dir.joinpath(
            translated.format(language=language_code)
        ).absolute()

        languages.append(
            Language(
                language_code,
                language_code == default_language,
                construction_message,
                language_translations,
                language_translated,
            )
        )

    return Config(
        languages=tuple(languages),
        formatters=formatters,
        strict=strict_mode,
        templates=project_dir.joinpath(templates).resolve(),
        boundaries=boundaries,
    )


def deserialize(stream: Path) -> Translations:
    yaml = YAML()
    with stream.open() as file:
        data = yaml.load(file)
        return {
            key: Translation(
                key=key,
                original=value["original"],
                translated=value["translated"],
                comments=tuple(value.get("comments", ())),
                literals=tuple(value.get("literals", ())),
            )
            for key, value in data.items()
        }


def serialize(data: Translations) -> str:
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.default_flow_style = False
    yaml.version = (1, 2)
    yaml.allow_unicode = True

    string_stream = StringIO()
    yaml.dump({key: value.as_json() for key, value in data.items()}, string_stream)
    return string_stream.getvalue()
