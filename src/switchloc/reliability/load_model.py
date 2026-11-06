# -*- coding: utf-8 -*-
"""Three-level load model (نیاز ۱۱ — مدل بار سه‌سطحی با منشأ ردیابی‌پذیر).

سطح‌ها (پیشنهاد کاربر، جدول رسمی نیاز + روش چهارم «Load Scaling»):

  ┌───────────┬───────────────────────────────────────┬──────────────────┐
  │ سطح       │ منبع بار                              │ کاربرد           │
  ├───────────┼───────────────────────────────────────┼──────────────────┤
  │ precise   │ بار واقعی ترانس یا کنتورهای اندازه‌گیری │ مطالعات معتبر    │
  │ estimated │ بار پیک ترانس × ضریب بارگذاری         │ مطالعات مقدماتی  │
  │ substitute│ ظرفیت نامی ترانس × ضریب فرضی          │ نبود داده واقعی  │
  │ scaled    │ بار فیدر (P،Q) توزیع بین ترانس‌ها      │ روش کاربر        │
  └───────────┴───────────────────────────────────────┴──────────────────┘

روش Load Scaling (سطح چهارم — درخواست کاربر):

  ورودی کاربر به‌ازای هر فیدر: P_load، Q_load (مثلاً پیک تابستان)
      S_load  = √(P² + Q²)
      φ       = arctan(Q / P)
      cos φ   = P / S_load            (= cos(arctan(Q/P)))
      P_rated_i = S_rated_i × cos φ   (ظرفیت مؤثر هر ترانس)
      K_f     = S_load / Σ S_rated    (ضریب مقیاس فیدر)
      P_Ti    = K_f × P_rated_i = K_f × S_rated_i × cos φ

  پس Σ P_Ti = S_load × cos φ = P_load — بار فیدر دقیقاً بین
  ترانس‌هایش به نسبت ظرفیت نامی توزیع می‌شود.

قواعد:
  * ضریب بارگذاری (``loading_factor``) و ضریب جایگزین
    (``substitute_factor``) قابل تنظیم‌اند و در settings_log ثبت می‌شوند.
  * منشأ «هر مقدار» ردیابی‌پذیر است: به‌ازای هر گره، برچسب منشأ
    (load id / transformer id × ضریب) برگردانده می‌شود — هیچ عدد
    بی‌منشأ وارد محاسبات نمی‌شود (بند ۱۹).
  * در سطح precise، گره‌های بدون بار واقعی، صفر در نظر گرفته و شمارش
    می‌شوند (پوشش داده بار صریح گزارش می‌شود؛ حدس زده نمی‌شود).
  * در سطح scaled، فیدر بدون ورودی P/Q صفر می‌گیرد و هشدار صریح
    می‌سازد (هیچ بار حدسی برایش فرض نمی‌شود).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.entities import CanonicalNetwork
from ..topology.graph import NetworkGraph
from ..validation.issues import (IssueLog, SEVERITY_INFO, SEVERITY_WARNING,
                                 ValidationIssue)

LEVEL_PRECISE = "precise"
LEVEL_ESTIMATED = "estimated"
LEVEL_SUBSTITUTE = "substitute"
LEVEL_SCALED = "scaled"          # روش Load Scaling (ورودی P/Q هر فیدر)
LEVELS = (LEVEL_PRECISE, LEVEL_ESTIMATED, LEVEL_SUBSTITUTE, LEVEL_SCALED)

LEVEL_FA = {
    LEVEL_PRECISE: "دقیق (بار واقعی کنتور/ترانس)",
    LEVEL_ESTIMATED: "تخمینی (بار پیک ترانس × ضریب بارگذاری)",
    LEVEL_SUBSTITUTE: "جایگزین (ظرفیت نامی ترانس × ضریب فرضی)",
    LEVEL_SCALED: "مقیاس‌شده (Load Scaling: بار فیدر بین ترانس‌ها توزیع می‌شود)",
}

#: پیش‌فرض ضریب بارگذاری (سیاست شرکت — قابل تنظیم و ثبت در settings_log)
DEFAULT_LOADING_FACTOR = 0.7
#: پیش‌فرض ضریب جایگزین (رفتار قبلی نرم‌افزار: kVA ≈ kW)
DEFAULT_SUBSTITUTE_FACTOR = 1.0

#: data_source های «بار واقعی» در مدل کانونی (ورود فاز ۱/۳)
_MEASURED_SOURCES = {"measured", "meter", "ampermeter", "contor", "real"}


@dataclass
class LoadModelSettings:
    """تنظیمات مدل بار — قابل تنظیم از GUI، ثبت‌شده در گزارش/پایگاه.

    ``feeder_pq``: ورودی روش Load Scaling (سطح scaled) — کلید فیدر →
    {"p_kw": بار اکتیو فیدر، "q_kvar": بار راکتیو فیدر}.  مقادیر به
    شکل خام ذخیره می‌شوند تا محاسبه K و cosφ در هر اجرا قابل ردیابی
    و تکرار باشد (منشأ عدد، بند ۱۹).
    """
    level: str = LEVEL_SCALED              # پیش‌فرض: بار کل فیدر (Load Scaling)
    loading_factor: float = DEFAULT_LOADING_FACTOR
    substitute_factor: float = DEFAULT_SUBSTITUTE_FACTOR
    feeder_pq: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.level not in LEVELS:
            raise ValueError(
                f"سطح مدل بار نامعتبر: {self.level} (مجاز: {LEVELS})")
        if not (0.0 < float(self.loading_factor) <= 1.5):
            raise ValueError("ضریب بارگذاری باید در بازه (0، 1.5] باشد.")
        if not (0.0 < float(self.substitute_factor) <= 2.0):
            raise ValueError("ضریب جایگزین باید در بازه (0، 2] باشد.")
        for fk, pq in dict(self.feeder_pq or {}).items():
            if not isinstance(pq, dict):
                raise ValueError(
                    f"ورودی بار فیدر {fk} باید dict با p_kw/q_kvar باشد.")
            p = float(pq.get("p_kw", 0.0) or 0.0)
            q = float(pq.get("q_kvar", 0.0) or 0.0)
            if p < 0.0 or q < 0.0 or (p == 0.0 and q == 0.0):
                raise ValueError(
                    f"ورودی بار فیدر {fk} نامعتبر است: "
                    "P و Q باید نامنفی و مجموع‌شان مثبت باشد.")

    def as_dict(self) -> dict:
        return {"level": self.level,
                "level_fa": LEVEL_FA[self.level],
                "loading_factor": self.loading_factor,
                "substitute_factor": self.substitute_factor,
                "feeder_pq": {k: dict(v)
                              for k, v in (self.feeder_pq or {}).items()}}

    @classmethod
    def from_dict(cls, d: dict) -> "LoadModelSettings":
        """بازسازی از as_dict/JSON — کلیدهای نمایشی مثل level_fa نادیده
        گرفته می‌شوند تا رفت‌وبرگشت تنظیمات همیشه کار کند."""
        known = {k: v for k, v in dict(d or {}).items()
                 if k in cls.__dataclass_fields__}
        return cls(**known)


@dataclass
class LoadModelResult:
    """خروجی مدل بار — مقدار + منشأ هر گره (ردیابی کامل)."""
    level: str = LEVEL_SCALED
    node_kw: dict = field(default_factory=dict)          # node → kW
    node_origin: dict = field(default_factory=dict)      # node → برچسب منشأ
    per_feeder_kw: dict = field(default_factory=dict)    # feeder_key → kW
    coverage: dict = field(default_factory=dict)         # آمار پوشش
    issues: list = field(default_factory=list)
    #: سطح scaled — طرح مقیاس هر فیدر (S_load، cosφ، K، ΣS_rated) برای
    #: نمایش در GUI و گزارش محاسبات کامل
    scaling_plan: dict = field(default_factory=dict)
    # Load-scaling reconciliation. Transformer load absent from the graph is
    # never silently redistributed to the remaining transformers.
    transformer_kw_by_id: dict = field(default_factory=dict)
    unassigned_transformer_ids: list = field(default_factory=list)
    unassigned_kw_by_feeder: dict = field(default_factory=dict)
    accounting: dict = field(default_factory=dict)


def feeder_key_of(name: str) -> str:
    """کلید کوتاه فیدر (نظیر ردیابی) برای گروه‌بندی ترانس‌ها."""
    from ..topology.tracing import feeder_key as fk
    return fk(name)


def scaling_plan(net: CanonicalNetwork,
                 feeder_pq: dict) -> tuple[dict, list]:
    """طرح مقیاس Load Scaling به‌ازای هر فیدر — فرمول‌های کاربر.

    ورودی:  feeder_pq = {feeder_key: {"p_kw": P, "q_kvar": Q}}
    خروجی: (plan, warnings) با plan[feeder_key] =
      {"p_kw", "q_kvar", "s_load_kva", "cos_phi", "k_scale",
       "sum_s_rated_kva", "n_transformers", "n_no_capacity"}

    warnings: فهرست (code, message_fa) برای فیدر بدون ورودی و فیدری
    که جمع ظرفیت نامی‌اش صفر است — صریح، هرگز سکوت (بند ۱۹).
    """
    import math
    caps_by_feeder: dict[str, list] = {}
    n_no_cap: dict[str, int] = {}
    for t in getattr(net, "transformers", []) or []:
        k = feeder_key_of(t.feeder_name) or "(بدون برچسب)"
        lst = caps_by_feeder.setdefault(k, [])
        if t.capacity_kva:
            lst.append(float(t.capacity_kva))
        else:
            n_no_cap[k] = n_no_cap.get(k, 0) + 1
    plan: dict = {}
    warnings: list = []
    keys = set(caps_by_feeder) | set(dict(feeder_pq or {}))
    for k in sorted(keys):
        pq = dict(feeder_pq or {}).get(k) or {}
        p = float(pq.get("p_kw", 0.0) or 0.0)
        q = float(pq.get("q_kvar", 0.0) or 0.0)
        s_rated = sum(caps_by_feeder.get(k, []))
        s_load = math.hypot(p, q)
        cos_phi = (p / s_load) if s_load > 0.0 else 0.0
        k_scale = (s_load / s_rated) if s_rated > 0.0 else 0.0
        plan[k] = {"p_kw": p, "q_kvar": q, "s_load_kva": round(s_load, 3),
                   "cos_phi": round(cos_phi, 6), "k_scale": round(k_scale, 8),
                   "sum_s_rated_kva": round(s_rated, 1),
                   "n_transformers": len(caps_by_feeder.get(k, [])),
                   "n_no_capacity": n_no_cap.get(k, 0)}
        if k not in (feeder_pq or {}):
            warnings.append((
                "LOAD-SCALING-FEEDER-NO-INPUT",
                f"فیدر {k} در روش Load Scaling ورودی P/Q ندارد — بار تمام "
                "ترانس‌های آن صفر گرفته شد (حدسی فرض نشد؛ بند ۱۹)."))
        elif k in caps_by_feeder and s_rated <= 0.0:
            warnings.append((
                "LOAD-SCALING-ZERO-CAPACITY",
                f"فیدر {k} ورودی بار دارد اما جمع ظرفیت نامی ترانس‌هایش "
                "صفر است — بار توزیع نشد (ظرفیت ترانس‌ها در GIS وارد شود)."))
    return plan, warnings


def build_node_loads(graph: NetworkGraph, net: CanonicalNetwork,
                     settings: LoadModelSettings | None = None,
                     issues: IssueLog | None = None) -> LoadModelResult:
    """بار هر گره را در سطح انتخابی می‌سازد (جایگزین node_load_map).

    * precise    : Σ بارهای با ``p_kw`` واقعی (data_source اندازه‌گیری)؛
                   گره بدون بار واقعی = 0 و در «پوشش» شمرده می‌شود.
    * estimated  : ظرفیت ترانس × ضریب بارگذاری (بار پیک تخمینی).
    * substitute : ظرفیت ترانس × ضریب جایگزین (رفتار قبلی kVA≈kW).
    * scaled     : روش Load Scaling — بار (P،Q) کاربر برای هر فیدر به
                   نسبت ظرفیت نامی بین ترانس‌های همان فیدر توزیع می‌شود
                   (P_Ti = K·S_rated_i·cosφ، K = S_load/ΣS_rated).
    """
    st = settings or LoadModelSettings()
    issues = issues if issues is not None else IssueLog()
    res = LoadModelResult(level=st.level)

    # ---- سطح scaled (روش کاربر): بار فیدر بین ترانس‌ها توزیع می‌شود -----
    if st.level == LEVEL_SCALED:
        plan, warns = scaling_plan(net, st.feeder_pq)
        res.scaling_plan = plan
        transformer_by_id = {str(t.id): t for t in net.transformers}
        for tid, t in transformer_by_id.items():
            fk = feeder_key_of(t.feeder_name) or "(بدون برچسب)"
            pf = plan.get(fk, {})
            cap = float(t.capacity_kva or 0.0)
            res.transformer_kw_by_id[tid] = (
                pf.get("k_scale", 0.0) * cap * pf.get("cos_phi", 0.0))
        graph_transformer_ids = {str(tid)
                                 for ids in graph.transformer_ids_at.values()
                                 for tid in ids}
        res.unassigned_transformer_ids = sorted(
            set(transformer_by_id) - graph_transformer_ids)
        for tid in res.unassigned_transformer_ids:
            t = transformer_by_id[tid]
            fk = feeder_key_of(t.feeder_name) or "(بدون برچسب)"
            res.unassigned_kw_by_feeder[fk] = (
                res.unassigned_kw_by_feeder.get(fk, 0.0)
                + res.transformer_kw_by_id.get(tid, 0.0))
        for node, ids in sorted(graph.transformer_ids_at.items()):
            trs = [t for t in net.transformers if t.id in set(ids)]
            total = 0.0
            origins = []
            for t in trs:
                fk = feeder_key_of(t.feeder_name) or "(بدون برچسب)"
                pf = plan.get(fk, {})
                cap = float(t.capacity_kva or 0.0)
                kw = res.transformer_kw_by_id.get(str(t.id), 0.0)
                total += kw
                if cap:
                    origins.append(
                        f"{t.id}: K={pf.get('k_scale', 0.0):.4g} × "
                        f"{cap:.0f}kVA × cosφ={pf.get('cos_phi', 0.0):.4g}")
            res.node_kw[node] = float(total)
            if total > 0:
                res.node_origin[node] = ("scaled (" + "; ".join(origins)
                                         + ")")
        # گره‌های دارای بار واقعی ولی بدون ترانس مدل‌شده — بدون تغییر
        load_of_node: dict[str, list] = {}
        for ld in net.loads:
            if ld.p_kw:
                load_of_node.setdefault(ld.node_id, []).append(ld)
        for node, lds in sorted(load_of_node.items()):
            if node not in res.node_kw:
                res.node_kw[node] = sum(ld.p_kw for ld in lds)
                res.node_origin[node] = ("real loads (no transformer): "
                                         + ",".join(sorted(ld.id
                                                           for ld in lds)))
        net_nodes = getattr(net, "nodes", None) or []
        feeder_of_node = {n.id: n.feeder_name for n in net_nodes}
        # یک مبنای واحد برای «بار هر فیدر» (نیاز ۱۱): بار منتسب به ترانس‌ها
        # را بر اساس کلید فیدرِ خود ترانس (همان مبنای scaling) جمع می‌زنیم —
        # نه بر اساس برچسب فیدرِ گره (که در اغلب GISها خالی است و جدول را
        # با اعداد بی‌معنی پر می‌کرد).
        assigned_by_feeder: dict[str, float] = {}
        for tid, kw in res.transformer_kw_by_id.items():
            if not kw:
                continue
            t = transformer_by_id.get(str(tid)) or transformer_by_id.get(tid)
            fk = feeder_key_of(t.feeder_name) if t is not None else ""
            fk = fk or "(بدون برچسب)"
            assigned_by_feeder[fk] = assigned_by_feeder.get(fk, 0.0) + kw
        res.per_feeder_kw = {k: round(v, 4)
                             for k, v in sorted(assigned_by_feeder.items())
                             if v > 0.0}
        # بارهای واقعی بدون ترانس — سطل برچسب گره (منشأ متفاوت، همان‌قدر صریح)
        for node, kw in res.node_kw.items():
            if kw and node not in graph.transformer_ids_at:
                key = feeder_of_node.get(node, "") or "(بدون برچسب)"
                res.per_feeder_kw[key] = round(
                    res.per_feeder_kw.get(key, 0.0) + kw, 4)
        fed_with_input = sum(1 for v in plan.values()
                             if v["p_kw"] or v["q_kvar"])
        input_kw = sum(v["p_kw"] for v in plan.values())
        assigned_transformer_kw = sum(
            res.transformer_kw_by_id.get(tid, 0.0)
            for tid in graph_transformer_ids if tid in transformer_by_id)
        unassigned_transformer_kw = sum(res.unassigned_kw_by_feeder.values())
        # A graph ID may occur at more than one node. Flag rather than
        # pretending the resulting node/zone sum is a valid partition.
        id_node_counts = {}
        for node, ids in graph.transformer_ids_at.items():
            for tid in ids:
                id_node_counts.setdefault(str(tid), set()).add(str(node))
        duplicated_ids = sorted(tid for tid, nodes in id_node_counts.items()
                                if len(nodes) > 1)
        res.accounting = {
            "feeder_input_p_kw": round(input_kw, 3),
            "graph_assigned_transformer_kw": round(assigned_transformer_kw, 3),
            "graph_unassigned_transformer_kw": round(unassigned_transformer_kw, 3),
            "transformer_count": len(transformer_by_id),
            "graph_assigned_count": len(graph_transformer_ids & set(transformer_by_id)),
            "graph_unassigned_count": len(res.unassigned_transformer_ids),
            "duplicate_transformer_ids": duplicated_ids,
            "reconciled": abs(input_kw - assigned_transformer_kw
                               - unassigned_transformer_kw) <= max(0.5, input_kw * 1e-6),
        }
        real_feeder_keys = {k for k in plan if k != "(بدون برچسب)"}
        res.coverage = {"nodes_total": len(graph.transformer_ids_at),
                        "feeders_total": len(real_feeder_keys),
                        "feeders_with_input": fed_with_input,
                        "no_capacity_transformers": sum(
                            v.get("n_no_capacity", 0)
                            for v in plan.values()),
                        "unlabeled_plan_bucket": "(بدون برچسب)" in plan,
                        "sum_p_kw": round(input_kw, 1),
                        "transformers_assigned_to_graph": len(
                            graph_transformer_ids & set(transformer_by_id)),
                        "transformers_unassigned_from_graph": len(
                            res.unassigned_transformer_ids)}
        if res.unassigned_transformer_ids or duplicated_ids:
            issues.add(ValidationIssue(
                code="LOAD-SCALING-TRANSFORMER-RECONCILIATION",
                severity=SEVERITY_WARNING,
                message_fa=(
                    f"از {len(transformer_by_id)} ترانس مدل‌شده، "
                    f"{len(res.unassigned_transformer_ids)} ترانس به گره‌های "
                    f"گراف متصل نیستند؛ بار متناظر "
                    f"{unassigned_transformer_kw:,.1f} kW در بار گره‌ها/زون‌ها "
                    "منظور نشده است."),
                suggestion_fa=("اتصال مکانی ترانس‌های فاقد گره، شناسه‌های "
                               "تکراری و فیدر منتسب به آن‌ها را در GIS بررسی کنید."),
                impact_fa=("این بار عمداً بین ترانس‌های متصل بازتوزیع نمی‌شود؛ "
                           "جمع بار زون‌ها می‌تواند کمتر از بار ورودی فیدر باشد."),
                meta=res.accounting))
            res.issues.append(issues.items()[-1])
        issues.add(ValidationIssue(
            code="LOAD-MODEL-LEVEL", severity=SEVERITY_INFO,
            message_fa=("مدل بار در سطح «Load Scaling» استفاده شد — بار هر "
                        "فیدر (P، Q) به نسبت ظرفیت نامی بین ترانس‌های همان "
                        "فیدر توزیع شد: K = S_load/ΣS_rated و "
                        "P_Ti = K·S_rated_i·cosφ."),
            suggestion_fa="ورودی P/Q هر فیدر از تنظیمات مهندسی (جدول بار "
                          "فیدرها) قابل ویرایش است.",
            impact_fa="جمع بار هر فیدر دقیقاً برابر P واردشده کاربر است؛ "
                      "فیدر بدون ورودی صفر است.",
            meta={"plan": plan, "coverage": res.coverage}))
        res.issues.append(issues.items()[-1])
        for code, msg in warns:
            issues.add(ValidationIssue(
                code=code, severity=SEVERITY_WARNING,
                message_fa=msg,
                suggestion_fa="ورودی بار فیدرها را از تنظیمات تکمیل یا "
                              "ظرفیت ترانس‌ها را در GIS اصلاح کنید.",
                impact_fa="بار آن فیدر در ENS و رتبه‌بندی صفر لحاظ می‌شود."))
            res.issues.append(issues.items()[-1])
        return res

    load_of_node: dict[str, list] = {}
    for ld in net.loads:
        if ld.p_kw:
            load_of_node.setdefault(ld.node_id, []).append(ld)

    for node, ids in sorted(graph.transformer_ids_at.items()):
        caps = [(t.id, (t.capacity_kva or 0.0)) for t in net.transformers
                if t.id in set(ids)]
        cap_sum = sum(c for _t, c in caps)
        if st.level == LEVEL_PRECISE:
            real = sum(ld.p_kw for ld in load_of_node.get(node, []))
            res.node_kw[node] = float(real)
            if real > 0:
                res.node_origin[node] = (
                    "real loads: " + ",".join(sorted(ld.id for ld
                                                     in load_of_node[node])))
        elif st.level == LEVEL_ESTIMATED:
            res.node_kw[node] = cap_sum * st.loading_factor
            res.node_origin[node] = (
                f"transformers ×LF({st.loading_factor:g}): "
                + ",".join(sorted(t for t, _c in caps)))
        else:                                  # substitute
            res.node_kw[node] = cap_sum * st.substitute_factor
            res.node_origin[node] = (
                f"transformers ×k({st.substitute_factor:g}): "
                + ",".join(sorted(t for t, _c in caps)))

    # گره‌های دارای بار واقعی ولی بدون ترانس مدل‌شده (precise کامل‌تر می‌کند)
    for node, lds in sorted(load_of_node.items()):
        if node not in res.node_kw:
            res.node_kw[node] = sum(ld.p_kw for ld in lds)
            res.node_origin[node] = ("real loads (no transformer): "
                                     + ",".join(sorted(ld.id for ld in lds)))

    # جمع به‌ازای هر فیدر (از برچسب فیدر گره‌های مدل؛ net بدون nodes → بدون جمع)
    net_nodes = getattr(net, "nodes", None) or []
    feeder_of_node = {n.id: n.feeder_name for n in net_nodes}
    for node, kw in res.node_kw.items():
        if kw:
            res.per_feeder_kw[feeder_of_node.get(node, "(بدون فیدر)")] = \
                res.per_feeder_kw.get(feeder_of_node.get(node, ""), 0.0) + kw

    total_nodes = len(graph.transformer_ids_at)
    if st.level == LEVEL_PRECISE:
        covered = sum(1 for v in res.node_kw.values() if v > 0)
        res.coverage = {"nodes_with_real_load": covered,
                        "nodes_total": total_nodes,
                        "coverage_percent": round(100.0 * covered
                                                  / total_nodes, 1)
                        if total_nodes else 0.0}
    else:
        res.coverage = {"nodes_total": total_nodes,
                        "factor": (st.loading_factor
                                   if st.level == LEVEL_ESTIMATED
                                   else st.substitute_factor)}

    issues.add(ValidationIssue(
        code="LOAD-MODEL-LEVEL", severity=SEVERITY_INFO,
        message_fa=(f"مدل بار در سطح «{LEVEL_FA[st.level]}» استفاده شد "
                    f"(نیاز ۱۱) — ضریب‌ها: بارگذاری "
                    f"{st.loading_factor:g}، جایگزین {st.substitute_factor:g}."),
        suggestion_fa="سطح مدل بار و ضرایب از تنظیمات مهندسی قابل تغییر "
                      "است؛ منشأ هر مقدار در خروجی LoadModelResult.node_origin "
                      "ثبت می‌شود.",
        impact_fa="بار زون‌ها/فیدرها در ENS و رتبه‌بندی با همین مدل محاسبه "
                  "می‌شود؛ سطح دقیق برای مطالعات معتبر لازم است.",
        meta=st.as_dict() | {"coverage": res.coverage}))
    res.issues.append(issues.items()[-1])
    if st.level == LEVEL_PRECISE and \
            res.coverage.get("coverage_percent", 100.0) < 50.0:
        issues.add(ValidationIssue(
            code="LOAD-MODEL-PRECISE-COVERAGE", severity=SEVERITY_WARNING,
            message_fa=("پوشش بار واقعی در سطح «دقیق» کم است: "
                        f"{res.coverage.get('coverage_percent')}٪ گره‌ها بار "
                        "واقعی دارند؛ گره‌های بدون داده، بار صفر گرفته شدند "
                        "(حدس نمی‌شود)."),
            suggestion_fa="برای مطالعه معتبر، بار کنتورها وارد شود یا سطح "
                          "«تخمینی» با ضریب بارگذاری تأییدشده به‌کار رود.",
            impact_fa="ENS و رتبه‌بندی می‌توانند به‌کندی برآورد شوند.",
            meta=res.coverage))
        res.issues.append(issues.items()[-1])
    return res
