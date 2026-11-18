# -*- coding: utf-8 -*-
"""Exact, auditable Level-2 placement search primitives.

The search minimizes the reliability engine's EENS objective over a finite,
explicit candidate set. Operating limits are supplied by the application-layer
feeder load-flow evaluator and are hard feasibility constraints (not penalty
terms). The algorithm never truncates the candidate set silently.
"""
from __future__ import annotations

import itertools

from ..task_control import check_cancelled
import math
from dataclasses import asdict, dataclass, field
from typing import Iterable

from ..reliability.switch_placement import SWITCH_TYPES


@dataclass(frozen=True)
class Level2Settings:
    """Finite search dimensions; counts are exact, not upper bounds."""

    nc_budget_by_feeder: dict[str, int]
    no_budget: int = 0
    max_search_states: int = 100_000
    candidate_mode: str = "load_points"
    switch_types: tuple[str, ...] = SWITCH_TYPES

    def validate(self) -> None:
        if int(self.max_search_states) != self.max_search_states or self.max_search_states < 1:
            raise ValueError("max_search_states باید عدد صحیح مثبت باشد.")
        if int(self.no_budget) != self.no_budget or self.no_budget < 0:
            raise ValueError("no_budget باید عدد صحیح نامنفی باشد.")
        if self.candidate_mode not in {"load_points", "all_nodes"}:
            raise ValueError("candidate_mode باید load_points یا all_nodes باشد.")
        if (not isinstance(self.switch_types, (tuple, list)) or not self.switch_types
                or any(t not in SWITCH_TYPES for t in self.switch_types)
                or len(set(self.switch_types)) != len(self.switch_types)):
            raise ValueError("switch_types باید فهرستی از recloser/sectionalizer/disconnector باشد.")
        if any(int(v) != v or int(v) < 0
               for v in self.nc_budget_by_feeder.values()):
            raise ValueError("بودجهٔ NC هر فیدر باید عدد صحیح نامنفی باشد.")
        if self.no_budget == 0 and not any(int(v) > 0
                                           for v in self.nc_budget_by_feeder.values()):
            raise ValueError("حداقل یک بودجهٔ NC یا NO برای جایابی لازم است.")

    def as_dict(self) -> dict:
        return {
            "nc_budget_by_feeder": {str(k): int(v) for k, v in self.nc_budget_by_feeder.items()},
            "no_budget": int(self.no_budget),
            "max_search_states": int(self.max_search_states),
            "candidate_mode": self.candidate_mode,
            "switch_types": list(self.switch_types),
            "search": "exhaustive-combinations",
        }


@dataclass
class Level2Plan:
    switch_type: str
    nc_by_feeder: dict[str, list[dict]]
    normally_open_ties: list[dict]
    base_eens_kwh_per_year: float
    post_plan_eens_kwh_per_year: float
    gain_kwh_per_year: float
    flow_feasible: bool
    base_eens_by_feeder: dict[str, float] = field(default_factory=dict)
    post_plan_eens_by_feeder: dict[str, float] = field(default_factory=dict)
    flow_scenarios: list[dict] = field(default_factory=list)
    infeasibility_reasons: list[str] = field(default_factory=list)
    state_index: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Level2StudyResult:
    settings: dict
    feeder_keys: list[str]
    baseline_eens_by_type: dict[str, dict[str, float]]
    best_plans: dict[str, dict | None]
    feasible_plan_count_by_type: dict[str, int]
    rejected_plan_count_by_type: dict[str, int]
    search_state_count: int
    flow_baseline: list[dict]
    unresolved: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    status: str = "ok"

    def as_dict(self) -> dict:
        return asdict(self)

    @property
    def markdown(self) -> str:
        lines = [
            "# جایابی سطح دوم مبتنی بر EENS و پخش بار",
            "",
            "جست‌وجوی شمارشی کامل روی مجموعهٔ کاندیدهای ثبت‌شده؛ طرح فقط وقتی "
            "پذیرفته است که قیود پخش بار و شعاعی‌بودن برقرار باشند.",
            "",
            f"**وضعیت مطالعه:** `{self.status}` · "
            f"**فیدرهای مطالعه:** {len(self.feeder_keys)} · "
            f"**حالت‌های ارزیابی‌شده:** {self.search_state_count:,}",
            "",
            "| نوع کلید | EENS پایه (kWh/سال) | EENS طرح (kWh/سال) | کاهش (kWh/سال) | "
            "NC انتخابی | NO انتخابی | طرح‌های مجاز | طرح‌های ردشده |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for switch_type, plan in self.best_plans.items():
            base = sum(self.baseline_eens_by_type.get(switch_type, {}).values())
            if plan is None:
                lines.append(
                    f"| {switch_type} | {base:.3f} | — | — | — | — | "
                    f"{self.feasible_plan_count_by_type.get(switch_type, 0)} | "
                    f"{self.rejected_plan_count_by_type.get(switch_type, 0)} |")
                continue
            nc_count = sum(len(v) for v in plan.get("nc_by_feeder", {}).values())
            no_count = len(plan.get("normally_open_ties", []))
            lines.append(
                f"| {switch_type} | {base:.3f} | "
                f"{plan['post_plan_eens_kwh_per_year']:.3f} | "
                f"{plan['gain_kwh_per_year']:.3f} | {nc_count} | {no_count} | "
                f"{self.feasible_plan_count_by_type.get(switch_type, 0)} | "
                f"{self.rejected_plan_count_by_type.get(switch_type, 0)} |")
        lines += ["", f"**تعداد حالت‌های ارزیابی‌شده:** {self.search_state_count}", ""]
        if self.flow_baseline:
            lines += ["## پخش بار پایه", "",
                      "| فیدر | وضعیت | Vmin (pu) | بیشینهٔ جریان (%) | بیشینهٔ بارگیری ترانس (%) |",
                      "|---|---|---:|---:|---:|"]
            for row in self.flow_baseline:
                lines.append(
                    f"| {row.get('feeder_key', '—')} | {row.get('status', '—')} | "
                    f"{_fmt(row.get('min_voltage_pu'))} | "
                    f"{_fmt(row.get('max_line_loading_pct'))} | "
                    f"{_fmt(row.get('max_transformer_loading_pct'))} |")
            lines.append("")
        for switch_type, plan in self.best_plans.items():
            if plan is None:
                continue
            lines += [f"## طرح منتخب: {switch_type}", "",
                      "| فیدر | EENS پایه (kWh/سال) | EENS پس از طرح (kWh/سال) | کاهش (kWh/سال) |",
                      "|---|---:|---:|---:|"]
            for feeder in sorted(set(plan.get("base_eens_by_feeder", {}))
                                 | set(plan.get("post_plan_eens_by_feeder", {}))):
                base_value = plan.get("base_eens_by_feeder", {}).get(feeder, 0.0)
                post_value = plan.get("post_plan_eens_by_feeder", {}).get(feeder, 0.0)
                lines.append(f"| {feeder} | {base_value:.3f} | {post_value:.3f} | "
                             f"{base_value - post_value:.3f} |")
            lines.append("")
            for feeder, devices in plan.get("nc_by_feeder", {}).items():
                for device in devices:
                    lines.append(
                        f"- NC در فیدر {feeder}: گره `{device['node']}`؛ "
                        f"{device.get('label', '')}")
            for tie in plan.get("normally_open_ties", []):
                lines.append(
                    f"- NO کاندید: `{tie.get('id')}` در گره `{tie.get('node')}` "
                    f"({tie.get('feeder_a')} ↔ {tie.get('feeder_b')})")
            if plan.get("infeasibility_reasons"):
                lines += ["", "موارد نقض:"]
                lines.extend(f"- {x}" for x in plan["infeasibility_reasons"])
            lines.append("")
        if self.unresolved:
            lines += ["## داده‌ها/حالت‌های حل‌نشده", ""]
            lines.extend(f"- {x}" for x in self.unresolved)
            lines.append("")
        if self.assumptions:
            lines += ["## فرض‌ها و مرز اعتبار", ""]
            lines.extend(f"- {x}" for x in self.assumptions)
        return "\n".join(lines)


def exact_plan_count(candidate_lists: dict[str, list], budgets: dict[str, int],
                     no_candidate_count: int, no_budget: int) -> int:
    """Calculate the exact finite state-space cardinality (before evaluation)."""
    count = math.comb(no_candidate_count, no_budget) if no_budget <= no_candidate_count else 0
    for feeder, budget in budgets.items():
        n = len(candidate_lists.get(feeder, ()))
        if int(budget) > n:
            return 0
        count *= math.comb(n, int(budget))
    return count


def enumerate_location_plans(candidate_lists: dict[str, list],
                              budgets: dict[str, int],
                              no_candidates: Iterable,
                              no_budget: int,
                              max_states: int):
    """Yield every (per-feeder NC selection, NO selection) exactly once.

    Raises instead of pruning when the requested exhaustive space exceeds the
    configured cap. A physical node cannot receive duplicate new switches.
    """
    no_candidates = sorted(no_candidates, key=lambda x: str(getattr(x, "id", "")))
    count = exact_plan_count(candidate_lists, budgets, len(no_candidates), no_budget)
    if count == 0:
        raise ValueError("بودجهٔ نصب با تعداد کاندیدهای معتبر سازگار نیست.")
    if count > max_states:
        raise ValueError(
            f"فضای جست‌وجوی دقیق {count:,} حالت است و از سقف "
            f"max_search_states={max_states:,} بیشتر است؛ کاندیدها/بودجه را "
            "صریح کاهش دهید یا سقف محاسباتی را افزایش دهید.")
    feeders = sorted(budgets)
    choices = []
    for feeder in feeders:
        check_cancelled()
        cand = sorted(candidate_lists.get(feeder, ()),
                      key=lambda x: (str(getattr(x, "node", "")),
                                     str(getattr(x, "edge_id", ""))))
        choices.append(list(itertools.combinations(cand, int(budgets[feeder]))))
    no_choices = itertools.combinations(no_candidates, int(no_budget))
    for no_sel in no_choices:
        check_cancelled()
        for feeder_choices in itertools.product(*choices):
            check_cancelled()
            selected_nodes = [str(getattr(c, "node", ""))
                              for batch in feeder_choices for c in batch]
            if len(selected_nodes) != len(set(selected_nodes)):
                continue
            yield ({feeder: list(batch)
                    for feeder, batch in zip(feeders, feeder_choices, strict=True)},
                   list(no_sel))


def _fmt(value) -> str:
    return "—" if value is None else f"{float(value):.4f}"
