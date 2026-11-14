# -*- coding: utf-8 -*-
"""Feeder ranking of گام ۶ (TAV122-02/00، بند ۷-۷-۵، فرمول (۱)، جدول ۱۶).

Six official criteria per feeder (weights ۱،۲،۲،۳،۱،۱ — PDF-verified):

  (1) معکوس تعداد ارتباطات نرمال‌شده   — tie count of جدول ۱۳, inverted
      with the official zero→10 rule (V-01);
  (2) EP نرمال‌شده                      — from the n-1 engine (جدول ۱۴);
  (3) معکوس TL نرمال‌شده                — transferability inverted: the
      less a feeder can be backed up, the higher its priority;
  (4) مجموع اولویت بارهای فیدر         — Σ(priority × load kW) روی
      ترانس‌های زون‌های مطالعه (یک مبنای واحد)؛ categories are unassigned in the sample
      GIS → the default priority is applied and REGISTERED (open
      decision 3, never guessed per load);
  (5) نرخ خرابی تصادفی λ نرمال‌شده      — total random λ of the Phase-3
      matrix (open decision 1 default) with λ_reducible reported
      alongside;
  (6) متوسط زمان خاموشی تصادفی r        — direct.

Every row carries raw, normalised, weighted values + score + rank
(بند ۱۲-۱ پرامپت مادر).  The audited kernels
`formulas.normalize` / `formulas.score_feeders` do the arithmetic —
this module only assembles the criterion columns on real data.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.entities import CanonicalNetwork
from ..reliability.lambdar import FeederLambdaR
from .formulas import FEEDER_RANKING_WEIGHTS, normalize, score_feeders
from .n_minus_1 import NMinusOneResult


# ---------------------------------------------------------------------------
@dataclass
class RankingSettings:
    weights: list = field(
        default_factory=lambda: list(FEEDER_RANKING_WEIGHTS))   # A-03
    #: open decision 3: load categories unassigned → baseline priority
    default_load_priority: float = 1.0        # روستایی (جدول ۱۲ baseline)
    #: literal «مجموع اولویت بارها» vs load-weighted sum (A-14)
    criterion4_mode: str = "load_weighted"    # | "priority_sum"
    #: open decision 1: total random λ (official text) + reducible λ aside
    lambda_source: str = "total_random"       # | "reducible_only"
    inverse_zero_policy: str = "confirmed"    # V-01 / A-02


@dataclass
class FeederRankRow:
    feeder_key: str
    raw: list                                 # [c1..c6]
    norm: list
    weighted: list
    score: float
    rank: int
    # supporting values (audit trail)
    ties_count: int = 0
    ep_percent: float = 0.0
    tl_percent: float = 0.0
    load_priority_sum: float = 0.0
    lambda_per_year: float = 0.0
    lambda_reducible: float = 0.0
    r_minutes: float = 0.0


@dataclass
class RankingResult:
    rows: list                                # sorted by rank
    issues: list = field(default_factory=list)
    settings: dict = field(default_factory=dict)


def _safe_normalize(values, inverse: bool, st: RankingSettings):
    """normalize() with the all-zero guard (all-zero column → zeros)."""
    try:
        return normalize(values, inverse=inverse,
                         inverse_zero_policy=st.inverse_zero_policy)
    except ValueError:
        return [0.0] * len(values)


def load_priority_by_transformer(net: CanonicalNetwork,
                                 st: RankingSettings) -> dict[str, float]:
    """transformer id → جدول ۱۲ priority (assigned loads win, else default).

    Load categories are unassigned in the sample GIS (open decision 3);
    every transformer that falls back to the default is counted so the
    report can show the coverage — nothing is silently guessed (بند ۱۹).
    """
    prio: dict[str, float] = {}
    for lp in net.loads:
        if lp.priority_weight is not None and lp.transformer_id:
            prio[lp.transformer_id] = float(lp.priority_weight)
    return prio


def feeder_criterion4(net: CanonicalNetwork, n1: NMinusOneResult,
                      feeder_key: str, prio_of_tr: dict[str, float],
                      st: RankingSettings,
                      load_kw_of_transformer: dict[str, float] | None = None
                      ) -> float:
    """Criterion 4 = مجموع اولویت بارهای فیدر (جدول ۱۱/۱۲).

    * ``load_weighted`` (default, A-14): Σ priority × **بار همان ترانس در
      مدل بار واحد** (kW) — یک مبنای واحد با زون‌ها/ENS. اگر نگاشت بار
      داده نشود، به‌صورت سابق capacity_kva (شاخص ظرفیت) استفاده می‌شود.
    * ``priority_sum``: the literal Σ priority (count of load points).
    """
    tree = n1.trees.get(feeder_key)
    if tree is None:
        return 0.0
    tr_ids = [tid for z in tree.zones for tid in z.transformer_ids]
    tr_by_id = {t.id: t for t in net.transformers}
    if st.criterion4_mode == "priority_sum":
        return float(sum(prio_of_tr.get(t, st.default_load_priority)
                         for t in tr_ids))
    total = 0.0
    for tid in tr_ids:
        if load_kw_of_transformer is not None:
            base = max(0.0, float(load_kw_of_transformer.get(tid, 0.0) or 0.0))
        else:
            t = tr_by_id.get(tid)
            base = (t.capacity_kva or 0.0) if t is not None else 0.0
        total += prio_of_tr.get(tid, st.default_load_priority) * base
    return total


def rank_feeders(n1: NMinusOneResult, net: CanonicalNetwork,
                 lam_matrix: list[FeederLambdaR] | None = None,
                 settings: RankingSettings | None = None,
                 scope_feeder: str | None = None,
                 scope_feeders=None,
                 transformer_load_kw: dict[str, float] | None = None,
                 ) -> RankingResult:
    """Assemble the 6 criteria; single-feeder studies normalize only that feeder."""
    st = settings or RankingSettings()
    issues: list = []

    keys = [f.feeder_key for f in n1.eptl]           # load-bearing feeders
    if scope_feeders:
        targets = {str(k).strip().upper() for k in scope_feeders if str(k).strip()}
        keys = [k for k in keys if str(k).strip().upper() in targets]
    elif scope_feeder:
        target = str(scope_feeder).strip().upper()
        keys = [k for k in keys if k == target]
    if not keys:
        return RankingResult(rows=[], issues=issues + [(
            "PLAC-NO-FEEDERS", "Warning",
            "هیچ فیدر دارای باری برای رتبه‌بندی وجود ندارد.")],
            settings=_settings_snapshot(st))

    lam_of = {m.feeder_key: m for m in (lam_matrix or [])}
    missing = [k for k in keys if k not in lam_of]
    if missing:
        issues.append((
            "PLAC-LAMBDA-MISSING", "Information",
            "ماتریس λ/r برای فیدرهای "
            f"{', '.join(sorted(missing))} در دسترس نیست؛ صفر وارد شد "
            "(معیارهای ۵/۶ صفر می‌مانند؛ سیاست صفر→۱۰ فقط معیار ۱ "
            "معکوس‌شونده را می‌گیرد)."))

    prio_of_tr = load_priority_by_transformer(net, st)
    assigned = len(prio_of_tr)
    if assigned == 0:
        issues.append((
            "PLAC-LOAD-CAT-DEFAULT", "Information",
            "دسته‌بندی بار (جدول ۱۲) برای هیچ نقطه باری ثبت نشده است؛ "
            f"اولویت پیش‌فرض {st.default_load_priority} برای همه "
            "بارها اعمال شد (تصمیم باز ۳ فاز ۳)."))

    # ---- raw criterion columns ------------------------------------------
    ties_count = {k: len(n1.ties_of_feeder.get(k, [])) for k in keys}
    ep_of = {f.feeder_key: f.ep.ep_percent for f in n1.eptl}
    tl_of = {f.feeder_key: f.ep.tl_percent for f in n1.eptl}
    raw1 = [float(ties_count[k]) for k in keys]
    raw2 = [ep_of[k] for k in keys]
    raw3 = [tl_of[k] for k in keys]
    raw4 = [feeder_criterion4(net, n1, k, prio_of_tr, st,
                              transformer_load_kw) for k in keys]
    raw5 = [(lam_of[k].lambda_per_year
             if st.lambda_source == "total_random"
             else lam_of[k].lambda_reducible_per_year) if k in lam_of else 0.0
            for k in keys]
    raw6 = [lam_of[k].r_minutes if k in lam_of else 0.0 for k in keys]

    # ---- normalisation (فرمول ۱ + سیاست صفر→۱۰ برای معکوس‌ها) -----------
    cols = [
        _safe_normalize(raw1, inverse=True, st=st),    # معیار ۱ (معکوس)
        _safe_normalize(raw2, inverse=False, st=st),   # معیار ۲
        _safe_normalize(raw3, inverse=True, st=st),    # معیار ۳ (معکوس)
        _safe_normalize(raw4, inverse=False, st=st),   # معیار ۴
        _safe_normalize(raw5, inverse=False, st=st),   # معیار ۵
        _safe_normalize(raw6, inverse=False, st=st),   # معیار ۶
    ]

    scores = score_feeders(list(zip(*cols)), weights=st.weights)

    rows = []
    for i, k in enumerate(keys):
        rows.append(FeederRankRow(
            feeder_key=k,
            raw=[raw1[i], raw2[i], raw3[i], raw4[i], raw5[i], raw6[i]],
            norm=[cols[j][i] for j in range(6)],
            weighted=[st.weights[j] * cols[j][i] for j in range(6)],
            score=scores[i]["score"], rank=scores[i]["rank"],
            ties_count=ties_count[k], ep_percent=ep_of[k],
            tl_percent=tl_of[k], load_priority_sum=raw4[i],
            lambda_per_year=raw5[i],
            lambda_reducible=(lam_of[k].lambda_reducible_per_year
                              if k in lam_of else 0.0),
            r_minutes=raw6[i]))
    rows.sort(key=lambda r: r.rank)

    if all(v == 0 for v in raw1):
        issues.append((
            "PLAC-TIES-ZERO", "Information",
            "هیچ فیدری اتصال اتوماسیون‌پذیر ندارد؛ معیار ۱ با سیاست "
            "صفر→۱۰ (V-01) یکسان‌سازی شد."))
    return RankingResult(rows=rows, issues=issues,
                         settings=_settings_snapshot(st))


def _settings_snapshot(st: RankingSettings) -> dict:
    return {
        "weights": list(st.weights),
        "default_load_priority": st.default_load_priority,
        "criterion4_mode": st.criterion4_mode,
        "lambda_source": st.lambda_source,
        "inverse_zero_policy": st.inverse_zero_policy,
        "anchors": {
            "formula_1": "TAV122-02/00 بند ۷-۷-۵، فرمول (۱)، صفحه ۳۳",
            "table_16": "جدول ۱۶ صفحه ۳۳ — وزن‌های ۱،۲،۲،۳،۱،۱",
            "zero_inverse": "«معکوس مقادیر صفر برابر با مقدار 10» (V-01)",
        },
    }
