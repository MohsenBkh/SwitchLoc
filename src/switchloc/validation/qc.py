# -*- coding: utf-8 -*-
"""QC engine + report (main prompt §۱۹ / ARCHITECTURE.md §۳).

The reader/assembler already emit the atomic issues; the QC engine
*aggregates and judges*: per-severity/code/layer counts, the acceptance
verdict (0 unresolved Error issues) and a Persian markdown report.
Nothing here mutates the underlying issues.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field as dc_field

from .issues import IssueLog, SEVERITY_ERROR, SEVERITY_INFO, SEVERITY_WARNING


@dataclass
class QcReport:
    project: str
    total_features: int = 0
    layers: dict = dc_field(default_factory=dict)
    severity_counts: Counter = dc_field(default_factory=Counter)
    code_counts: Counter = dc_field(default_factory=Counter)
    layer_severity: dict = dc_field(default_factory=lambda: defaultdict(Counter))
    error_issues: list = dc_field(default_factory=list)
    summary: dict = dc_field(default_factory=dict)
    verdict: str = "FAIL"           # PASS | FAIL
    verdict_reason_fa: str = ""

    def as_dict(self) -> dict:
        return {
            "project": self.project,
            "verdict": self.verdict,
            "verdict_reason_fa": self.verdict_reason_fa,
            "total_features": self.total_features,
            "summary": self.summary,
            "layers": self.layers,
            "severity_counts": dict(self.severity_counts),
            "code_counts": dict(self.code_counts.most_common()),
            "error_issues": [i.as_dict() for i in self.error_issues],
        }

    def to_markdown(self) -> str:
        lines = [
            f"# گزارش کنترل کیفیت ورود داده — {self.project}",
            "",
            f"**نتیجه پذیرش: {'✅ PASS' if self.verdict == 'PASS' else '❌ FAIL'}** — "
            f"{self.verdict_reason_fa}",
            "",
            "## خلاصه مدل canonical",
            "",
        ]
        for k, v in self.summary.items():
            lines.append(f"- {k}: {v}")
        lines += ["", "## شمارش اهمیت Issueها", ""]
        for sev in (SEVERITY_ERROR, SEVERITY_WARNING, SEVERITY_INFO):
            lines.append(f"- {sev}: {self.severity_counts.get(sev, 0)}")
        lines += ["", "## Issueها بر اساس کد", "", "| کد | تعداد |", "|---|---|"]
        for code, n in self.code_counts.most_common():
            lines.append(f"| {code} | {n} |")
        lines += ["", "## Issueها بر اساس لایه و اهمیت", "",
                  "| لایه | Error | Warning | Information |", "|---|---|---|---|"]
        for layer in sorted(self.layer_severity):
            c = self.layer_severity[layer]
            lines.append(f"| {layer} | {c.get(SEVERITY_ERROR, 0)} | "
                         f"{c.get(SEVERITY_WARNING, 0)} | {c.get(SEVERITY_INFO, 0)} |")
        if self.error_issues:
            lines += ["", "## فهرست Issueهای Error (حل‌نشده)", ""]
            for i in self.error_issues:
                lines.append(f"- **{i.code}** {i.message_fa} "
                             f"(لایه: {i.layer or '—'})")
        lines.append("")
        return "\n".join(lines)


def run_qc(network_summary: dict, issues: IssueLog, project: str,
           layer_feature_counts: dict | None = None) -> QcReport:
    rep = QcReport(project=project)
    rep.summary = network_summary
    rep.total_features = sum((layer_feature_counts or {}).values())
    rep.layers = dict(layer_feature_counts or {})
    for isu in issues.items():
        rep.severity_counts[isu.severity] += 1
        rep.code_counts[isu.code] += 1
        rep.layer_severity[isu.layer or "(بدون لایه)"][isu.severity] += 1
        if isu.severity == SEVERITY_ERROR and isu.status == "open":
            rep.error_issues.append(isu)
    n_err = len(rep.error_issues)
    if n_err == 0:
        rep.verdict = "PASS"
        rep.verdict_reason_fa = ("هیچ Issue از رده Error حل‌نشده وجود ندارد؛ "
                                 "مدل canonical وارد فاز توپولوژی می‌شود.")
    else:
        rep.verdict = "FAIL"
        rep.verdict_reason_fa = (f"{n_err} Issue از رده Error حل‌نشده وجود دارد؛ "
                                 f"اصلاح داده/نگاشت الزامی است.")
    return rep
