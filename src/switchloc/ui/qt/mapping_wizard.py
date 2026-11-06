# -*- coding: utf-8 -*-
"""Mapping wizard — Qt front-end of the layer/field mapping service (D-04).

Wraps `gis.mapping.LayerMappingService` (the Phase-1 service — unchanged):
  suggest() → suggestion table with confidence/reason → user review →
  confirm() with recorded confirmer (no automatic mapping is ever final —
  rule §5-3).

The engineering logic lives in the service; this dialog only binds Qt
widgets to it.  (The former placeholder tab builders were replaced by
the rich tab panels in `main_window.launch()`.)
"""
from __future__ import annotations

from ...gis.mapping.layer_mapping import LayerMappingService
from ...gis.readers.base import LayerInfo

# English one-line reasons shown in the wizard (the service keeps the
# Persian audit text in `reason_fa`; the UI displays these).
_REASONS_EN: tuple[tuple[str, str | None, str], ...] = (
    ("high", None,
     "Layer name matches the documented naming catalog."),
    ("medium", "transformer",
     "Transformer capacity field (T_strn) present in the layer."),
    ("medium", "switch_manual",
     "Switch-type / remote-control fields present in the layer."),
    ("none", "unmapped",
     "No known role matched the name or field signature; "
     "the role must be chosen manually."),
)


def _reason_en(suggestion) -> str:
    conf, slot = suggestion.confidence, suggestion.slot_key
    for c, s, text in _REASONS_EN:
        if conf == c and (s is None or slot == s):
            return text
    return str(getattr(suggestion, "reason_fa", ""))


class MappingWizardPage:
    """Review-and-confirm dialog over MappingSuggestions (requires Qt)."""

    def __init__(self, suggestions, mapping: LayerMappingService,
                 layers: list[LayerInfo], parent=None):     # pragma: no cover
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, \
            QTableWidget, QVBoxLayout

        self.dialog = QDialog(parent)
        self.dialog.setWindowTitle(
            "Confirm layer mapping — no automatic mapping is final")
        self.suggestions = suggestions
        self.mapping = mapping
        self.layers = {li.name: li for li in layers}

        lay = QVBoxLayout(self.dialog)
        lay.addWidget(QLabel(
            "Review the suggested role of each layer. A mapping becomes "
            "final only with your explicit confirmation "
            "(confirmer and timestamp are recorded)."))
        self.table = QTableWidget(len(suggestions), 3)
        self.table.setHorizontalHeaderLabels(
            ["Layer", "Suggested role", "Confidence / reason"])
        for r, s in enumerate(suggestions):
            self.table.setItem(r, 0, self._item(s.layer_name))
            self.table.setItem(r, 1, self._item(s.slot_key))
            self.table.setItem(r, 2, self._item(f"{s.confidence} — {_reason_en(s)}"))
        self.table.setColumnWidth(2, 420)
        lay.addWidget(self.table)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.dialog.accept)
        buttons.rejected.connect(self.dialog.reject)
        lay.addWidget(buttons)

    @staticmethod
    def _item(text: str):                          # pragma: no cover
        from PySide6.QtWidgets import QTableWidgetItem
        return QTableWidgetItem(text)

    def exec(self) -> bool:                        # pragma: no cover
        # Scoped enum access — instance-level unscoped enums (e.g.
        # `self.dialog.Accepted`) were removed in recent PySide6.
        from PySide6.QtWidgets import QDialog
        return self.dialog.exec() == QDialog.DialogCode.Accepted

    def apply(self) -> bool:                       # pragma: no cover
        """Write the user's (possibly edited) decisions into the service."""
        for r, s in enumerate(self.suggestions):
            slot = self.table.item(r, 1).text().strip()
            li = self.layers[s.layer_name]
            if slot and slot != s.slot_key:
                s.slot_key = slot
            self.mapping.confirm(li, s.slot_key,
                                 confirmed_by="ui-user",
                                 field_map=s.field_map)
        return True
