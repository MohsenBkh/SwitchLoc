# -*- coding: utf-8 -*-
"""model of validation issues (main-prompt §19, GeoGrid-audit §10 decision).

An issue is *the* unit of engineering traceability: every exclusion,
assumption or data gap in SwitchLoc must surface as one of these.
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field, asdict
from typing import Optional

SEVERITY_ERROR = "Error"              # blocks a valid computation
SEVERITY_WARNING = "Warning"          # computable, result is constrained
SEVERITY_INFO = "Information"         # notice / recorded assumption


@dataclass
class ValidationIssue:
    """One engineering/data discrepancy (main prompt §5-7).

    Fields mirror the main prompt exactly: source file, layer, record id,
    related field, current value, suggested fix, study impact, status.
    """
    code: str
    severity: str                      # Error | Warning | Information
    message_fa: str
    source_file: str = ""
    layer: str = ""
    record_id: str = ""
    field: str = ""
    current_value: str = ""
    suggestion_fa: str = ""
    impact_fa: str = ""
    status: str = "open"               # open | resolved | waived
    meta: dict = dc_field(default_factory=dict)

    def as_dict(self):
        return asdict(self)


class IssueLog:
    """Ordered, filterable issue collector with stable ids (SL-0001...)."""

    def __init__(self):
        self._items: list[ValidationIssue] = []

    def add(self, issue: ValidationIssue) -> ValidationIssue:
        issue.meta.setdefault("issue_id", f"SL-{len(self._items) + 1:05d}")
        self._items.append(issue)
        return issue

    def extend(self, issues) -> None:
        for i in issues:
            self.add(i)

    def count(self, severity: Optional[str] = None) -> int:
        if severity is None:
            return len(self._items)
        return sum(1 for i in self._items if i.severity == severity)

    def by_code(self, code: str):
        return [i for i in self._items if i.code == code]

    def items(self):
        return list(self._items)

    def has_errors(self) -> bool:
        return self.count(SEVERITY_ERROR) > 0
