from __future__ import annotations

import subprocess
from collections import defaultdict
from typing import TYPE_CHECKING

from bs4 import BeautifulSoup
from bs4.element import NavigableString
from pyutilkit.term import SGROutput, SGRString

from pysetta.lib.constants import LITERAL, TRANSLATION_SUFFIX
from pysetta.lib.utils import (
    Language,
    PathData,
    TagData,
    Translation,
    deserialize,
    get_config,
    get_text,
    serialize,
)

if TYPE_CHECKING:
    import re
    from collections.abc import Iterator
    from pathlib import Path

    from pysetta.lib.type_defs import Extracted, Translations


class Command:
    __slots__ = ("config", "dry_run", "extracted", "templates", "verbosity")
    run_for_all: bool

    def __init__(
        self, templates: list[Path], verbosity: int, *, dry_run: bool, **_kwargs: object
    ) -> None:
        self.dry_run = dry_run
        self.verbosity = verbosity
        self.config = get_config()
        self.templates = templates
        self.format(templates)
        self.extracted = self.extract_translatable()

    def extract_translatable(self) -> Extracted:
        translations: Extracted = {"translations": {}, "paths": defaultdict(list)}
        for template in self.templates:
            translations["translations"][template] = {}
            soup = self.get_soup(template)
            for tag in soup.find_all(self.config.tags.translation):
                translation = Translation.from_tag(tag)
                translations["translations"][template][translation.key] = translation
                translations["paths"][translation.key].append(template)

        return translations

    def update_translations(
        self, new_translations: dict[Path, Translations], old_translations: Translations
    ) -> None:
        for key, paths in self.extracted["paths"].items():
            if (
                key not in old_translations
                or not (old_translation := old_translations[key]).translated
            ):
                continue

            for path in paths:
                new_translation = new_translations[path][key]
                if (
                    new_translation.translated
                    and new_translation.translated != old_translation.translated
                ):
                    msg = f"Translation mismatch for key '{key}':\n"
                    raise ValueError(msg)
                new_translations[path][key] = old_translation

    def get_translations(self, language: Language) -> dict[Path, Translations]:
        new_translations = self.extracted["translations"].copy()
        for path in language.translations_dir.rglob(f"*{TRANSLATION_SUFFIX}"):
            translations = deserialize(path)
            self.update_translations(new_translations, translations)

        return new_translations

    def get_translations_dict(
        self, language: Language, template: Path
    ) -> dict[str, str]:
        if language.is_default:
            return {
                key: translation.original
                for key, translation in self.extracted["translations"][template].items()
            }

        translations = deserialize(
            language.get_translations_path(template, self.config)
        )
        cleaned_translations = {}
        for key, translation in translations.items():
            translated = translation.translated
            if not translated:
                strict_mode = self.config.strict
                if strict_mode:
                    msg = f"Missing translation for {key=} in {language.code=}"
                    raise ValueError(msg)
                translated = translation.original
            for literal in translation.literals:
                if literal not in translated:
                    msg = f"Missing literal '{literal}' in {key=}"
                    raise ValueError(msg)
            cleaned_translations[key] = translated

        return cleaned_translations

    def get_soup(self, template: Path) -> BeautifulSoup:
        data = f"<pre>{template.read_text()}</pre>"
        return BeautifulSoup(data, "lxml")

    def format(self, paths: list[Path]) -> None:
        suffix_groups: dict[str, list[str]] = defaultdict(list)
        for path in paths:
            suffix_groups[path.suffix].append(path.as_posix())
        for formatter in self.config.formatters:
            matches = suffix_groups.get(formatter.suffix, [])
            if not matches:
                continue
            command = formatter.command
            if self.verbosity > 0:
                SGRString("Formatting").header(padding="=")
                SGROutput(
                    f"✍️ Formatting `{matches}` using `{' '.join(command)}`"
                ).print()
            subprocess.run([*command, *matches], check=True)  # noqa: S603
            if self.verbosity > 0:
                SGRString("Formatted").header(padding="=")

    def _clean_literal(self, regex_match: re.Match[str]) -> str:
        return regex_match.group("inner_text")

    def clean_translation(self, soup: BeautifulSoup) -> str:
        content = get_text(soup)
        return LITERAL.sub(self._clean_literal, content)

    def get_generate_data(self, language: Language) -> Iterator[PathData]:
        if language.is_default:
            return

        translations = self.get_translations(language)
        for template in self.templates:
            yield PathData(
                path=language.get_translations_path(template, self.config),
                language_code=language.code,
                content=serialize(translations[template]),
            )

    def get_translated_text(
        self, language: Language, template: Path
    ) -> Iterator[PathData]:
        translations_dict = self.get_translations_dict(language, template)

        soup = self.get_soup(template)
        for tag in soup.find_all(self.config.tags.translation):
            tag_data = TagData.from_tag(tag)
            tag.replace_with(NavigableString(translations_dict[tag_data.key]))

        yield PathData(
            path=language.get_translated_path(template, self.config),
            language_code=language.code,
            content=self.clean_translation(soup),
        )

    def write_path_data(self, path_data: list[PathData]) -> None:
        for data in path_data:
            if self.verbosity > 0:
                header = f"Writing `{data.path}` for `{data.language_code}`"
                SGRString(header).header(padding="=")
                SGROutput(data.content).print()

            if not self.dry_run:
                data.path.parent.mkdir(parents=True, exist_ok=True)
                data.path.write_text(data.content)

        if self.verbosity > 0:
            SGRString("Done").header(padding="=")

    def generate(self) -> None:
        path_data = [
            data
            for language in self.config.languages
            for data in self.get_generate_data(language)
        ]
        self.write_path_data(path_data)

        if not self.dry_run:
            self.format([data.path for data in path_data])

    def translate(self) -> None:
        if not self.dry_run:
            paths = [
                language.get_translations_path(template, self.config)
                for template in self.templates
                for language in self.config.languages
                if not language.is_default
            ]

            self.format(paths)

        path_data = [
            data
            for language in self.config.languages
            for template in self.templates
            for data in self.get_translated_text(language, template)
        ]
        self.write_path_data(path_data)

        if not self.dry_run:
            self.format([data.path for data in path_data])
