"""Orchestrates the shared regular-expression editor.

The dialog sends the current fields here. This controller applies the caller's
case flag and the configured limits, then asks RegexEditorService to compile,
insert, and test. It does not touch widgets.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.services.regex_editor_service import (
    RegexBlock,
    RegexBlockGroup,
    RegexEditorService,
    RegexEditorValues,
    RegexExample,
    RegexExplainNode,
    RegexPreview,
)

__all__ = [
    "RegexBlock",
    "RegexBlockGroup",
    "RegexEditorController",
    "RegexExample",
    "RegexEditorValues",
    "RegexExplanation",
    "RegexPreview",
]


@dataclass(frozen=True)
class RegexExplanation:
    """One explanation row, with the sentence already filled in."""

    kind: str
    token: str
    text: str
    closing_token: str = ""
    children: Tuple["RegexExplanation", ...] = ()


class RegexEditorController:
    """Session rules for one opening of the regex editor."""

    def __init__(
        self,
        config: Dict[str, Any],
        *,
        case_sensitive: bool,
        show_replace: bool,
        replacement: str,
        service: Optional[RegexEditorService] = None,
        settings: Optional[Any] = None,
    ) -> None:
        self._config = config
        self._service = service or RegexEditorService()
        self._settings = settings
        self.case_sensitive = case_sensitive
        self.show_replace = show_replace
        self._replacement = replacement
        section = config.get("ui", {}).get("dialogs", {}).get("regex_editor", {})
        self._section = section if isinstance(section, dict) else {}

    def block_groups(self) -> List[RegexBlockGroup]:
        return self._service.block_groups(self._config)

    def examples(self) -> List[RegexExample]:
        return self._service.examples(self._config)

    def blocks(self) -> List[RegexBlock]:
        return self._service.blocks(self._config)

    def classify(self, pattern: str) -> List[Tuple[int, int, str]]:
        return self._service.classify(pattern)

    def insert_block(
        self,
        pattern: str,
        start: int,
        end: int,
        block: RegexBlock,
    ) -> Tuple[str, int, int]:
        return self._service.insert_block(pattern, start, end, block.insert, block.select_text)

    def starting_pattern(self, pattern: str) -> Tuple[str, Optional[int]]:
        """Pattern shown when the editor opens.

        An empty pattern is replaced by ``empty_template``. The cursor sits just
        before a trailing ``$`` when that template is anchored at both ends.
        """
        if pattern != "":
            return pattern, None
        template = str(self._section["empty_template"])
        cursor = len(template)
        if len(template) >= 2 and template.startswith("^") and template.endswith("$"):
            cursor = len(template) - 1
        return template, cursor

    def normalize_name(self, name: str) -> str:
        return self._service.normalize_name(name)

    def pattern_can_be_saved(self, pattern: str) -> bool:
        return self.preview(pattern, "", "").valid

    def replaces_current_pattern(self, pattern: str) -> bool:
        """A load should be confirmed when the editor holds something other than the template."""
        template, _cursor = self.starting_pattern("")
        return pattern != "" and pattern != template

    def saved_names(self) -> List[str]:
        return sorted(self._library().keys(), key=str.casefold)

    def saved_pattern(self, name: str) -> Optional[str]:
        return self._library().get(name)

    def library_has(self, name: str) -> bool:
        return name in self._library()

    def store_pattern(self, name: str, pattern: str) -> None:
        cleaned = self.normalize_name(name)
        if not cleaned or not self.pattern_can_be_saved(pattern):
            return
        library = self._library()
        library[cleaned] = pattern
        self._settings_service().update_saved_regexes(library)

    def remove_pattern(self, name: str) -> None:
        library = self._library()
        library.pop(name, None)
        self._settings_service().update_saved_regexes(library)

    def preview(self, pattern: str, replacement: str, sample: str) -> RegexPreview:
        return self._service.preview(
            pattern,
            replacement if self.show_replace else self._replacement,
            sample,
            case_sensitive=self.case_sensitive,
            max_sample_chars=int(self._section["max_sample_chars"]),
            max_matches=int(self._section["max_highlighted_matches"]),
        )

    def explain(self, pattern: str) -> List[RegexExplanation]:
        """Nested explanation of ``pattern``, using the configured sentences."""
        return [self._present(node) for node in self._service.explain(pattern)]

    def accepted_values(
        self,
        pattern: str,
        replacement: str,
        sample: str,
    ) -> Optional[RegexEditorValues]:
        """Values to keep when the user accepts, or None while the pattern is unusable."""
        preview = self.preview(pattern, replacement, sample)
        if not preview.valid:
            return None
        kept = replacement if self.show_replace else self._replacement
        return RegexEditorValues(pattern, kept)

    def _present(self, node: RegexExplainNode) -> RegexExplanation:
        templates = self._section["explain"]
        fields = {key: _format_value(value) for key, value in node.fields}
        if fields.get("case_matters") == "1":
            note_id = "case_sensitive_token" if self.case_sensitive else "case_insensitive_token"
            fields["case_note"] = " " + str(templates[note_id])
        else:
            fields["case_note"] = ""
        if fields.get("lazy") == "1":
            fields["lazy_note"] = str(templates["quantifier_lazy"])
        else:
            fields["lazy_note"] = ""
        return RegexExplanation(
            kind=node.kind,
            token=node.token,
            text=str(templates[node.message_id]).format(**fields),
            closing_token=node.closing_token,
            children=tuple(self._present(child) for child in node.children),
        )


    def _settings_service(self) -> Any:
        if self._settings is None:
            from app.services.user_settings_service import UserSettingsService

            self._settings = UserSettingsService.get_instance()
        return self._settings

    def _library(self) -> Dict[str, str]:
        raw = self._settings_service().get_saved_regexes()
        if not isinstance(raw, dict):
            return {}
        return {
            name: pattern
            for name, pattern in raw.items()
            if isinstance(name, str) and isinstance(pattern, str) and pattern != ""
        }


def _format_value(value: str) -> str:
    return value.replace("{", "{{").replace("}", "}}")
