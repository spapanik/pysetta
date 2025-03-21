from __future__ import annotations

import subprocess
from collections import defaultdict
from functools import partial
from typing import TYPE_CHECKING

from pyutilkit.term import SGROutput, SGRString

from pysetta.lib.constants import TRANSLATION_SUFFIX
from pysetta.lib.exceptions import IncompleteTranslationsError
from pysetta.lib.utils import (
    Language,
    PathData,
    TagData,
    Translation,
    deserialize,
    get_config,
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
        self,
        templates: list[Path],
        languages: list[str],
        verbosity: int,
        *,
        dry_run: bool,
    ) -> None:
        self.dry_run = dry_run
        self.verbosity = verbosity
        self.config = get_config(languages)
        self.templates = templates
        self.format(templates)
        self.extracted = self.extract_translatable()

    def extract_translatable(self) -> Extracted:
        translatable = self.config.boundaries.translation.regex
        literal = self.config.boundaries.literal
        translations: Extracted = {"translations": {}, "paths": defaultdict(list)}
        for template in self.templates:
            translations["translations"][template] = {}
            for regex_match in translatable.finditer(template.read_text()):
                translation = Translation.from_text(
                    regex_match.group("inner_text"), literal
                )
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
        literal_regex = self.config.boundaries.literal.regex
        cleaned_translations = {}
        for key, translation in translations.items():
            cleaned_translations[key] = translation.translated
            if not translation.translated:
                msg = f"Missing translation for {key=} in {language.code=}"
                if self.config.strict:
                    raise KeyError(msg)
                raise IncompleteTranslationsError(msg)

            if translation.literals:
                for literal in translation.literals:
                    if literal not in translation.translated:
                        msg = f"Missing literal '{literal}' in {key=}"
                        raise ValueError(msg)

                cleaned_translations[key] = literal_regex.sub(
                    self._get_inner_text, translation.translated
                )

        return cleaned_translations

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

    def _get_inner_text(self, regex_match: re.Match[str]) -> str:
        return regex_match.group("inner_text")

    def _get_translated(
        self, regex_match: re.Match[str], translations_dict: dict[str, str]
    ) -> str:
        full_text = regex_match.group(0)
        inner_text = regex_match.group("inner_text")
        if full_text[1] != "$":
            return inner_text
        key = TagData.from_text(inner_text).key
        return translations_dict[key]

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
        try:
            translations_dict = self.get_translations_dict(language, template)
        except IncompleteTranslationsError:
            content = language.construction_message
        else:
            translations = partial(
                self._get_translated, translations_dict=translations_dict
            )
            template_text = template.read_text()
            translatable = self.config.boundaries.translation.regex
            content = translatable.sub(translations, template_text)

        yield PathData(
            path=language.get_translated_path(template, self.config),
            language_code=language.code,
            content=content,
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
