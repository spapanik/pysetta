from __future__ import annotations

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
    from typing_extensions import Self  # upgrade: py3.10: import from typing

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

    @classmethod
    def from_text(cls, inner_text: str) -> Self:
        stripped = inner_text.strip()
        key = sha3_224(stripped.encode()).hexdigest()
        original = stripped

        return cls(key=key, original=original)


@dataclass(frozen=True, slots=True)
class Formatter:
    suffix: str
    command: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Language:
    code: str
    construction_message: str
    translations_dir: Path
    translated_dir: Path

    def get_translations_path(self, path: Path, config: Config) -> Path:
        relative_path = path.relative_to(config.template_root)
        suffix = f"{relative_path.suffix}{TRANSLATION_SUFFIX}"
        return self.translations_dir.joinpath(relative_path).with_suffix(suffix)

    def get_translated_path(self, path: Path, config: Config) -> Path:
        relative_path = path.relative_to(config.template_root)
        return self.translated_dir.joinpath(relative_path)


@dataclass(frozen=True, slots=True)
class Config:
    original: str
    languages: tuple[Language, ...]
    strict: bool
    formatters: tuple[Formatter, ...]
    project_dir: Path

    @property
    def template_root(self) -> Path:
        return self.project_dir.joinpath(self.original)


@dataclass(frozen=True, slots=True)
class Translation:
    key: str
    original: str
    translated: str
    whitespace: str

    @classmethod
    def from_text(cls, inner_text: str) -> Self:
        tag_data = TagData.from_text(inner_text)
        whitespace = inner_text[: len(inner_text) - len(inner_text.lstrip())]
        return cls(
            key=tag_data.key,
            original=tag_data.original,
            translated="",
            whitespace=whitespace,
        )

    @staticmethod
    def _prepare_str(string: str) -> str:
        if "\n" in string:
            return LiteralScalarString(string)
        return string or DoubleQuotedScalarString("")

    def as_json(self) -> JSONType:
        output: dict[str, JSONType] = {
            "original": self._prepare_str(self.original),
            "translated": self._prepare_str(self.translated),
        }
        if self.whitespace:
            output["whitespace"] = self.whitespace
        return output

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
        "translations", sections=["languages"], rtype=dict
    )
    original_language: str = get_pysetta_setting(
        "original", sections=["languages"], rtype=str
    )
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

    languages = []
    formatters = tuple(
        Formatter(suffix=suffix, command=tuple(formatter_command))
        for suffix, formatter_command in formatters_config.items()
    )

    for language_code, construction_message in all_languages.items():
        language_translations = project_dir.joinpath(
            "translations", language_code
        ).absolute()

        language_translated = project_dir.joinpath(language_code).absolute()

        languages.append(
            Language(
                language_code,
                construction_message,
                language_translations,
                language_translated,
            )
        )

    return Config(
        original=original_language,
        languages=tuple(languages),
        formatters=formatters,
        strict=strict_mode,
        project_dir=project_dir,
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
                whitespace=value.get("whitespace", ""),
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
