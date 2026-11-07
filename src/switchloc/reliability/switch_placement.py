# -*- coding: utf-8 -*-
"""روش جایابی بهینهٔ کلید و کاهش EENS — موتور تحلیلی SwitchLoc.

این ماژول پیش‌تر «بهینه‌سازی سکشنالایزر» نام داشت؛ اکنون هر سه نوع کلید
توزیع را جایابی می‌کند: **ریکلوزر**، **سکشنالایزر** و **سکسیونر**. نوع
کلید در ورودی انتخاب می‌شود و دستهٔ خطاهایی که هر نوع پوشش می‌دهد متفاوت
است (``SWITCH_TYPE_FAULT_SCOPE``).

این ماژول **روش** کد PowerFactory («F2 MESHKIN — FAST SECTIONALIZER
OPTIMIZATION»)  را به ساختار داده‌ای SwitchLoc منتقل می‌کند؛ هیچ وابستگی
به PowerFactory، Qt یا Matplotlib ندارد و روی گراف/ردیابی/مدل بار خودِ
SwitchLoc کار می‌کند (قابل آزمون با pytest و اجرا از CLI).

مدل مهندسی (همان مبنای کد مرجع، مستند و قابل ردیابی — بند ۱۹)
--------------------------------------------------------------------
* هر فیدر یک درخت شعاعی است که از گره منبع (سر فیدر) ریشه می‌گیرد.
* نرخ خرابی کل فیدر λ_feeder (خرابی/سال) **متناسب با طول خط** بین
  قطعات توزیع می‌شود: λ_i = λ_feeder · L_i / L_total.
* برای خطای قطعهٔ i:
    - بار خود قطعه به مدت «زمان تعمیر» (پیش‌فرض ۵۰ دقیقه) بی‌برق است؛
    - بقیهٔ بار شبکه پس از «زمان بازیابی» (پیش‌فرض ۲۰ دقیقه) برمی‌گردد.
  در مدل پیش‌فرض ``restoration_model="uniform"`` (هم‌ارز کد مرجع) همهٔ
  بار غیرمعیوب با زمان بازیابی برمی‌گردد:

      EENS = Σ_i (λ_i/60) · [ T_rep·P_i + T_rest·(P_total − P_i) ]

* مدل ``restoration_model="directional"`` سخت‌گیرانه‌تر است و واقعیت
  شعاعی را می‌پذیرد: قطعات بالادست/موازی خطا **بی‌برق نمی‌شوند**،
  قطعهٔ معیوب T_rep و فقط قطعات پایین‌دست T_rest (و آن هم تا سقف ظرفیت
  پشتیبان ``backup_kw``؛ بار بازپُل‌نشده T_rep می‌ماند).
* سقف ظرفیت پشتیبان اختیاری است (``backup_kw`` هر فیدر). پیش‌فرض
  «نامحدود» است تا نتیجه با کد مرجع مقایسه‌پذیر بماند؛ این فرض در
  خروجی صریح ثبت می‌شود (`assumptions`).

تفاوت‌های عمدی با کد مرجع (بهبود، نه انتقال خط‌به‌خط)
------------------------------------------------------
1. **کلیدهای موجود**: در SwitchLoc مرزهای زون از کلیدهای موجود
   (DCS/CBR/REC/SEC و NO) ساخته می‌شوند. این کلیدها به‌صورت قطعه‌بندی
   موجود در حالت پایه لحاظ می‌شوند (``use_existing_switches``) — کد
   مرجع همهٔ فیدر را یک قطعه می‌گرفت و بهبود را بیش‌برآورد می‌کرد.
2. **گراف غیردرختی**: کد مرجع در صورت وجود حلقه/خط موازی کل اجرا را رد
   می‌کرد. اینجا درخت پوشای BFS ساخته می‌شود، یال‌های اضافی و طولشان
   (به گرهٔ جد مشترک) صریح ثبت می‌شوند و اجرا با هشدار ادامه می‌یابد.
3. **بار واقعی SwitchLoc**: بار هر گره از مدل بار (Load Model) می‌آید
   (kW)، نه فقط یک عدد کل فیدر.
4. سکشنالایزر روی گره‌ای که از قبل تجهیز دارد پیشنهاد نمی‌شود، و یال
   سرِ فیدر (ورودی پست) هرگز کاندید نیست.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field as dc_field
from typing import Iterable, Sequence

from ..topology.graph import NetworkGraph
from ..topology.tracing import feeder_key as normalize_feeder_key

#: λ پیش‌فرض هر فیدر (خرابی/سال) — همان عدد کد مرجع (۳۰)
DEFAULT_FAILURE_RATE_PER_YEAR = 30.0
#: زمان تعمیر قطعهٔ معیوب (دقیقه) — کد مرجع
DEFAULT_REPAIR_TIME_MIN = 50.0
#: زمان بازیابی بار سالم (دقیقه) — کد مرجع
DEFAULT_RESTORATION_TIME_MIN = 20.0
#: سقف تعداد سکشنالایزر پیشنهادی هر فیدر
DEFAULT_MAX_SECTIONALIZERS = 3
#: سهم بار پایین‌دست از کل فیدر که فراتر از آن کاندید رد می‌شود
DEFAULT_MAX_DOWNSTREAM_LOAD_RATIO = 0.80
#: کمترین عمق (تعداد یال از سر فیدر) برای کاندیدبودن
DEFAULT_MIN_CANDIDATE_DEPTH = 3

#: مدل‌های مجاز بازیابی
RESTORATION_MODELS = ("uniform", "directional")
RESTORATION_MODEL_FA = {
    "uniform": "یکنواخت (هم‌ارز کد مرجع PowerFactory)",
    "directional": "شعاعی/جهت‌دار (بالادست بی‌برق نمی‌شود)",
}

#: ---------------------------------------------------------------------------
#: انواع کلید قابل جایابی (درخواست کاربر: هر سه نوع کلید)
#: ---------------------------------------------------------------------------
SWITCH_RECLOSER = "recloser"
SWITCH_SECTIONALIZER = "sectionalizer"
SWITCH_DISCONNECTOR = "disconnector"
SWITCH_TYPES = (SWITCH_RECLOSER, SWITCH_SECTIONALIZER, SWITCH_DISCONNECTOR)

SWITCH_TYPE_FA = {
    SWITCH_RECLOSER: "ریکلوزر (Recloser)",
    SWITCH_SECTIONALIZER: "سکشنالایزر (Sectionalizer)",
    SWITCH_DISCONNECTOR: "سکسیونر (Disconnector)",
}

#: دستهٔ خطاهایی که هر نوع کلید برای آن‌ها ارزیابی می‌شود.
#:  * ریکلوزر: گذرا + دائمی (گذرا برای وقفهٔ کوتاه و احتمال موفقیت وصل مجدد،
#:    دائمی برای جداسازی محدودهٔ معیوب و بازیابی بار سالم).
#:  * سکشنالایزر: فقط دائمی (خطای گذرا رخداد مستقلِ نیازمند جداسازی نیست).
#:  * سکسیونر: فقط دائمی برای EENS؛ خاموشی برنامه‌ای در تحلیل مانور/تعمیرات
#:    جداگانه استفاده می‌شود و خطای گذرا معیار جایابی نیست.
SWITCH_TYPE_FAULT_SCOPE = {
    SWITCH_RECLOSER: ("transient", "permanent"),
    SWITCH_SECTIONALIZER: ("permanent",),
    SWITCH_DISCONNECTOR: ("permanent",),
}

#: توضیح فنی هر نوع کلید (برای راهنما/گزارش)
SWITCH_TYPE_NOTE_FA = {
    SWITCH_RECLOSER: "خطای گذرا با وصل مجدد پاک می‌شود؛ بار پایین‌دست فقط "
                     "به‌اندازهٔ زمان ریکلوز بی‌برق می‌ماند.",
    SWITCH_SECTIONALIZER: "قطع خودکار پس از عملکرد حفاظت بالادست؛ معیار "
                          "جایابی خطاهای دائمی است.",
    SWITCH_DISCONNECTOR: "قطع/وصل دستی؛ جداسازی محدودهٔ معیوب و انتقال بار "
                         "با زمان بازیابی دستی انجام می‌شود.",
}


# ---------------------------------------------------------------------------
# تنظیمات
# ---------------------------------------------------------------------------
@dataclass
class SwitchPlacementSettings:
    """تنظیمات موتور — همهٔ اعداد منشأ دارند و در خروجی ثبت می‌شوند."""

    #: λ پیش‌فرض هر فیدر (خرابی/سال) وقتی نرخ واقعی خاموشی موجود نباشد
    total_failure_rate_per_year: float = DEFAULT_FAILURE_RATE_PER_YEAR
    repair_time_min: float = DEFAULT_REPAIR_TIME_MIN
    restoration_time_min: float = DEFAULT_RESTORATION_TIME_MIN
    max_sectionalizers: int = DEFAULT_MAX_SECTIONALIZERS
    max_downstream_load_ratio: float = DEFAULT_MAX_DOWNSTREAM_LOAD_RATIO
    min_candidate_depth: int = DEFAULT_MIN_CANDIDATE_DEPTH
    #: قطعه‌بندی موجود (کلیدهای نصب‌شده) در حالت پایه لحاظ شود
    use_existing_switches: bool = True
    #: uniform (کد مرجع) یا directional (سخت‌گیرانه)
    restoration_model: str = "uniform"
    #: گره‌هایی که از قبل کلید دارند کاندید نشوند (نصب دوبارهٔ کلید)
    exclude_nodes_with_switch: bool = True
    #: گره ترمینال ترانس هم کاندید نشود (پیش‌فرض: مجاز — نصب روی ترانس رایج است)
    exclude_transformer_terminal_nodes: bool = False
    #: توقف جست‌وجو وقتی بهبود یک گام از این مقدار کمتر شد
    stop_without_gain: bool = True
    min_gain_kwh_per_year: float = 1e-6
    #: سقف تعداد کاندید هر فیدر (۰ = بی‌سقف؛ فقط برای کارایی)
    max_candidates_per_feeder: int = 0
    #: نوع کلید مورد جایابی: recloser | sectionalizer | disconnector
    switch_type: str = SWITCH_SECTIONALIZER
    #: خطای گذرا: حداکثر مدت (دقیقه) برای اینکه رخداد «گذرا» شمرده شود
    transient_max_duration_min: float = 3.0
    #: زمان بی‌برقی کامل هنگام خطای گذرا در نبود ریکلوزر (دقیقه)
    transient_interruption_min: float = 1.0
    #: زمان وصل مجدد ریکلوزر (دقیقه) — وقفهٔ بار پایین‌دست در خطای گذرا
    reclose_time_min: float = 0.25
    #: احتمال موفقیت وصل مجدد (۰..۱)؛ در صورت شکست، وقفهٔ گذرا کامل می‌شود
    reclose_success_probability: float = 0.70
    #: زمان بازیابی بار برای کلید دستی (سکسیونر) — دقیقه
    manual_restoration_time_min: float = 30.0

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if self.restoration_model not in RESTORATION_MODELS:
            raise ValueError(
                f"restoration_model نامعتبر: {self.restoration_model} "
                f"(مجاز: {', '.join(RESTORATION_MODELS)})")
        if float(self.total_failure_rate_per_year) < 0:
            raise ValueError("نرخ خرابی نمی‌تواند منفی باشد.")
        if float(self.repair_time_min) < 0 or float(self.restoration_time_min) < 0:
            raise ValueError("زمان تعمیر/بازیابی نمی‌تواند منفی باشد.")
        if int(self.max_sectionalizers) < 0:
            raise ValueError("سقف تعداد سکشنالایزر نمی‌تواند منفی باشد.")
        if not (0.0 < float(self.max_downstream_load_ratio) <= 1.0):
            raise ValueError("سهم بار پایین‌دست باید در بازه (۰، ۱] باشد.")
        if int(self.min_candidate_depth) < 0:
            raise ValueError("کمترین عمق کاندید نمی‌تواند منفی باشد.")
        if self.switch_type not in SWITCH_TYPES:
            raise ValueError(
                f"switch_type نامعتبر: {self.switch_type} "
                f"(مجاز: {', '.join(SWITCH_TYPES)})")
        if not (0.0 <= float(self.reclose_success_probability) <= 1.0):
            raise ValueError("احتمال موفقیت وصل مجدد باید در بازهٔ [0، 1] باشد.")
        if float(self.transient_max_duration_min) < 0:
            raise ValueError("حداکثر مدت خطای گذرا نمی‌تواند منفی باشد.")
        if float(self.manual_restoration_time_min) < 0:
            raise ValueError("زمان بازیابی دستی نمی‌تواند منفی باشد.")

    def as_dict(self) -> dict:
        return {
            "total_failure_rate_per_year": float(self.total_failure_rate_per_year),
            "repair_time_min": float(self.repair_time_min),
            "restoration_time_min": float(self.restoration_time_min),
            "max_sectionalizers": int(self.max_sectionalizers),
            "max_downstream_load_ratio": float(self.max_downstream_load_ratio),
            "min_candidate_depth": int(self.min_candidate_depth),
            "use_existing_switches": bool(self.use_existing_switches),
            "exclude_nodes_with_switch": bool(self.exclude_nodes_with_switch),
            "exclude_transformer_terminal_nodes":
                bool(self.exclude_transformer_terminal_nodes),
            "restoration_model": self.restoration_model,
            "restoration_model_fa": RESTORATION_MODEL_FA[self.restoration_model],
            "stop_without_gain": bool(self.stop_without_gain),
            "min_gain_kwh_per_year": float(self.min_gain_kwh_per_year),
            "max_candidates_per_feeder": int(self.max_candidates_per_feeder),
            "switch_type": self.switch_type,
            "switch_type_fa": SWITCH_TYPE_FA[self.switch_type],
            "fault_scope": list(SWITCH_TYPE_FAULT_SCOPE[self.switch_type]),
            "transient_max_duration_min": float(self.transient_max_duration_min),
            "transient_interruption_min": float(self.transient_interruption_min),
            "reclose_time_min": float(self.reclose_time_min),
            "reclose_success_probability": float(self.reclose_success_probability),
            "manual_restoration_time_min": float(self.manual_restoration_time_min),
            # زمان بازیابی مؤثر پس از اعمال نوع کلید (سکسیونر: دستی)
            "effective_restoration_time_min":
                float(self.effective_restoration_time_min),
        }

    @property
    def uses_transient_faults(self) -> bool:
        return "transient" in SWITCH_TYPE_FAULT_SCOPE[self.switch_type]

    @property
    def effective_restoration_time_min(self) -> float:
        """زمان بازیابی بار برای نوع کلید انتخاب‌شده.

        سکشنالایزر/ریکلوزر خودکار عمل می‌کنند (زمان تنظیمات)؛ سکسیونر
        دستی است و زمان بازیابی دستی استفاده می‌شود.
        """
        if self.switch_type == SWITCH_DISCONNECTOR:
            return float(self.manual_restoration_time_min)
        return float(self.restoration_time_min)

    @classmethod
    def from_dict(cls, d: dict | None) -> "SectionalizerSettings":
        known = {k: v for k, v in dict(d or {}).items()
                 if k in cls.__dataclass_fields__}
        return cls(**known)


# ---------------------------------------------------------------------------
# درخت شعاعی
# ---------------------------------------------------------------------------
@dataclass
class RadialTree:
    """درخت پوشای یک فیدر + جمع‌های پایین‌دست (یک‌بار محاسبه)."""

    root: str
    order: list = dc_field(default_factory=list)        # ترتیب BFS
    parent: dict = dc_field(default_factory=dict)       # node → والد
    parent_edge: dict = dc_field(default_factory=dict)  # node → یال والد
    depth: dict = dc_field(default_factory=dict)
    tin: dict = dc_field(default_factory=dict)
    tout: dict = dc_field(default_factory=dict)
    subtree_load_kw: dict = dc_field(default_factory=dict)
    subtree_length_m: dict = dc_field(default_factory=dict)
    own_load_kw: dict = dc_field(default_factory=dict)
    edge_length_m: dict = dc_field(default_factory=dict)  # گره → طول یال والد
    extra_edge_ids: list = dc_field(default_factory=list)
    extra_length_m: float = 0.0
    unreachable_edge_ids: list = dc_field(default_factory=list)
    total_load_kw: float = 0.0
    total_length_m: float = 0.0

    # -- پرس‌وجوهای ساختاری ------------------------------------------------
    def is_ancestor(self, a: str, b: str) -> bool:
        """True اگر ``a`` جد (یا خود) ``b`` باشد — O(1) با بازهٔ اویلر."""
        if a == b:
            return True
        return (self.tin.get(a, 0) <= self.tin.get(b, 0)
                and self.tout.get(b, 0) <= self.tout.get(a, 0))

    def is_strict_ancestor(self, a: str, b: str) -> bool:
        return a != b and self.is_ancestor(a, b)

    def path_to_root(self, node: str) -> list:
        out, seen = [], set()
        cur = node
        while cur is not None and cur not in seen:
            out.append(cur)
            seen.add(cur)
            cur = self.parent.get(cur)
        return out

    def descendants(self, node: str) -> list:
        tin, tout = self.tin.get(node), self.tout.get(node)
        if tin is None or tout is None:
            return []
        return [n for n in self.order
                if tin <= self.tin.get(n, -1) and self.tout.get(n, -1) <= tout]


def build_radial_tree(graph: NetworkGraph, trace, node_load_kw: dict
                      ) -> RadialTree:
    """درخت شعاعی یک فیدر را از ردیابی نرمال‌حالت آن می‌سازد.

    یال‌های اضافی (حلقه/موازی) حذف نمی‌شوند: شناسه و طول‌شان ثبت و طول
    به گرهٔ «جد مشترک» دو سر اضافه می‌شود تا Σ طول قطعه‌ها با طول واقعی
    فیدر برابر بماند (بند ۱۹ — هیچ طولی گم نمی‌شود).
    """
    trace_edges = set(getattr(trace, "edges", ()) or ())
    root = getattr(trace, "source_node", None)
    if root is None or root not in graph.nodes:
        # ریشهٔ جایگزین: اولین گره لبه‌های ردیابی (وضعیت نادر/غیرعادی)
        for eid in sorted(trace_edges):
            e = graph.edges.get(eid)
            if e is not None:
                root = e.a
                break
    tree = RadialTree(root=str(root or ""))
    if not root:
        return tree

    visited = {tree.root}
    tree.parent[tree.root] = None
    tree.parent_edge[tree.root] = None
    tree.depth[tree.root] = 0
    used_edges: set[str] = set()
    queue = deque([tree.root])
    while queue:
        u = queue.popleft()
        tree.order.append(u)
        for v, eid in sorted(graph.neighbors(u)):
            if eid not in trace_edges or eid in used_edges:
                continue
            if v in visited:
                continue
            edge = graph.edges.get(eid)
            if edge is None:
                continue
            visited.add(v)
            used_edges.add(eid)
            tree.parent[v] = u
            tree.parent_edge[v] = eid
            tree.depth[v] = tree.depth[u] + 1
            tree.edge_length_m[v] = float(edge.length_m or 0.0)
            queue.append(v)

    tree.extra_edge_ids = sorted(trace_edges - used_edges)
    # یال‌هایی که هیچ سرشان به درخت نرسیده است (برشِ ردیابی/فیدر جدا)
    tree.unreachable_edge_ids = sorted(
        eid for eid in tree.extra_edge_ids
        if not ({graph.edges[eid].a, graph.edges[eid].b} <= visited))

    # بازهٔ اویلر (tin/tout) از روی درخت — تکراری‌ها امن‌اند
    clock = 0
    children: dict[str, list] = {n: [] for n in tree.order}
    for n in tree.order:
        p = tree.parent.get(n)
        if p is not None:
            children.setdefault(p, []).append(n)
    stack = [(tree.root, False)]
    while stack:
        node, done = stack.pop()
        if done:
            clock += 1
            tree.tout[node] = clock
            continue
        clock += 1
        tree.tin[node] = clock
        stack.append((node, True))
        for ch in reversed(children.get(node, ())):
            stack.append((ch, False))

    # بار و طول هر گره
    for n in tree.order:
        tree.own_load_kw[n] = max(0.0, float(node_load_kw.get(n, 0.0) or 0.0))
        tree.subtree_load_kw[n] = tree.own_load_kw[n]
        tree.subtree_length_m[n] = float(tree.edge_length_m.get(n, 0.0))

    # طول یال‌های اضافی → گرهٔ جد مشترک دو سر (تا در قطعهٔ درست بیفتد)
    for eid in tree.extra_edge_ids:
        edge = graph.edges.get(eid)
        if edge is None:
            continue
        a, b = edge.a, edge.b
        if a not in tree.own_load_kw or b not in tree.own_load_kw:
            continue
        lca = a
        seen = set()
        while lca is not None and not tree.is_ancestor(lca, b) and lca not in seen:
            seen.add(lca)
            lca = tree.parent.get(lca)
        if lca is None:
            lca = tree.root
        tree.subtree_length_m[lca] += float(edge.length_m or 0.0)
        tree.extra_length_m += float(edge.length_m or 0.0)

    for n in reversed(tree.order):
        p = tree.parent.get(n)
        if p is not None:
            tree.subtree_load_kw[p] += tree.subtree_load_kw[n]
            tree.subtree_length_m[p] += tree.subtree_length_m[n]

    tree.total_load_kw = float(tree.subtree_load_kw.get(tree.root, 0.0))
    tree.total_length_m = float(tree.subtree_length_m.get(tree.root, 0.0))
    return tree


#: برچسب فارسی نوع خط برای نام کاندید
_EDGE_KIND_FA = {
    "line_aerial": "خط هوایی",
    "line_underground": "خط زمینی",
    "jumper": "جامپر",
    "line_misc": "خط متفرقه",
}


def _candidate_label(feeder_key: str, edge, node_obj, depth: int) -> str:
    """برچسب خوانا برای یک کاندید: فیدر · نوع خط · مختصات (در صورت وجود)."""
    kind = str(getattr(edge, "kind", "") or "")
    kind_fa = _EDGE_KIND_FA.get(kind, kind or "خط")
    coord = getattr(node_obj, "coord", None) if node_obj is not None else None
    if coord is not None:
        return (f"{feeder_key} · {kind_fa} · "
                f"@ {float(coord[0]):.0f}, {float(coord[1]):.0f} m")
    return f"{feeder_key} · {kind_fa} · depth {depth}"


# ---------------------------------------------------------------------------
# قطعه‌ها و EENS
# ---------------------------------------------------------------------------
@dataclass
class Section:
    """یک قطعهٔ شبکه بین مرزهای جداسازی."""

    index: int
    cut_node: str | None          # None = قطعهٔ ریشه (بالادست همهٔ برش‌ها)
    parent_index: int | None      # قطعهٔ بالادست در درخت
    load_kw: float
    length_m: float
    lambda_per_year: float = 0.0
    load_ratio: float = 0.0
    length_ratio: float = 0.0
    eens_contribution_kwh: float = 0.0

    def as_dict(self) -> dict:
        return {
            "index": self.index,
            "cut_node": self.cut_node,
            "parent_index": self.parent_index,
            "load_kw": round(self.load_kw, 6),
            "length_m": round(self.length_m, 6),
            "length_km": round(self.length_m / 1000.0, 6),
            "lambda_per_year": round(self.lambda_per_year, 9),
            "load_ratio": round(self.load_ratio, 9),
            "length_ratio": round(self.length_ratio, 9),
            "eens_kwh_per_year": round(self.eens_contribution_kwh, 6),
        }


def _nearest_selected_ancestor(tree: RadialTree, node: str,
                               selected: set) -> str | None:
    cur = tree.parent.get(node)
    while cur is not None:
        if cur in selected:
            return cur
        cur = tree.parent.get(cur)
    return None


def build_sections(tree: RadialTree, cut_nodes: Iterable[str]) -> list[Section]:
    """قطعه‌بندی درخت با مجموعهٔ گره‌های برش (کلید موجود + کاندید).

    قطعهٔ ۰ قطعهٔ ریشه است (همهٔ گره‌هایی که زیر هیچ برشی نیستند)؛ هر
    گره برش یک قطعه می‌سازد که زیرقطعه‌های تودرتوی خودش را کم می‌کند —
    همان مدل قطعی کد مرجع، ولی با پشتیبانی از برش‌های تودرتو.
    """
    cuts = [c for c in dict.fromkeys(cut_nodes) if c in tree.parent
            and c != tree.root]
    cut_set = set(cuts)
    top = [c for c in cuts if _nearest_selected_ancestor(tree, c, cut_set) is None]

    root_load = tree.total_load_kw - sum(tree.subtree_load_kw[c] for c in top)
    root_length = tree.total_length_m - sum(tree.subtree_length_m[c] for c in top)
    sections = [Section(index=0, cut_node=None, parent_index=None,
                        load_kw=max(0.0, root_load),
                        length_m=max(0.0, root_length))]
    index_of: dict[str, int] = {}
    for c in sorted(cuts, key=lambda n: (tree.depth.get(n, 0), n)):
        index_of[c] = len(sections)
        parent = _nearest_selected_ancestor(tree, c, cut_set)
        sections.append(Section(
            index=index_of[c], cut_node=c,
            parent_index=(index_of[parent] if parent is not None else 0),
            load_kw=max(0.0, tree.subtree_load_kw.get(c, 0.0)),
            length_m=max(0.0, tree.subtree_length_m.get(c, 0.0))))
    # کم‌کردن زیردرختِ *خام* هر قطعه از والدش. مهم است که مقدار خام کم شود
    # نه مقدار اصلاح‌شدهٔ همان قطعه؛ وگرنه در زنجیرهٔ برش‌های تودرتو
    # (ریشه → a → b → c) طول/بارِ c دو بار شمرده می‌شود (SEC-NESTED).
    raw = {c: (tree.subtree_load_kw.get(c, 0.0), tree.subtree_length_m.get(c, 0.0))
           for c in cuts}
    for sec in sections[1:]:
        if sec.parent_index in (None, 0):
            # قطعهٔ ریشه پیش‌تر به‌اندازهٔ همهٔ زیردرخت‌های سطح‌اول کم شده است
            continue
        parent = sections[sec.parent_index]
        r_load, r_len = raw[sec.cut_node]
        parent.load_kw = max(0.0, parent.load_kw - r_load)
        parent.length_m = max(0.0, parent.length_m - r_len)
    return sections


def _assign_lambdas(sections: Sequence[Section], failure_rate: float,
                    total_length_m: float) -> None:
    total = float(total_length_m or 0.0)
    for sec in sections:
        sec.length_ratio = (sec.length_m / total) if total > 0 else 0.0
        sec.lambda_per_year = float(failure_rate) * sec.length_ratio


def compute_eens_kwh(sections: Sequence[Section], *, failure_rate: float,
                     total_length_m: float, total_load_kw: float,
                     repair_time_min: float, restoration_time_min: float,
                     restoration_model: str = "uniform",
                     backup_kw: float | None = None) -> float:
    """EENS سالانه (kWh/سال) برای یک قطعه‌بندی داده‌شده.

    ``backup_kw=None`` یعنی ظرفیت پشتیبان نامحدود (فرض کد مرجع).
    """
    _assign_lambdas(sections, failure_rate, total_length_m)
    total = float(total_load_kw or 0.0)
    rep = float(repair_time_min)
    # بار سالم هرگز دیرتر از پایان تعمیر برنمی‌گردد: اگر بازیابی (مثلاً
    # سکسیونر دستی) از تعمیر کندتر باشد، عملاً همان انتظار تعمیر است. بدون
    # این clamp مدل برای زمان بازیابی > تعمیر، نصب کلید را *بدتر* نشان می‌داد.
    rest = min(float(restoration_time_min), rep)
    total_eens = 0.0
    if restoration_model == "directional":
        # قطعه‌های پایین‌دست هر قطعه (بر اساس زنجیرهٔ والد)
        for sec in sections:
            downstream = [s for s in sections
                          if s.index != sec.index
                          and _section_is_descendant(s, sec, sections)]
            fault_load = sec.load_kw
            down_load = sum(s.load_kw for s in downstream)
            if backup_kw is None:
                restored = down_load
            else:
                restored = min(down_load, max(0.0, float(backup_kw)))
            contribution = (sec.lambda_per_year / 60.0) * (
                rep * fault_load + rest * restored + rep * (down_load - restored))
            sec.eens_contribution_kwh = contribution
            total_eens += contribution
        return total_eens

    for sec in sections:
        healthy = max(0.0, total - sec.load_kw)
        if backup_kw is None:
            restored = healthy              # فرض کد مرجع: پشتیبان نامحدود
        else:
            restored = min(healthy, max(0.0, float(backup_kw)))
        contribution = (sec.lambda_per_year / 60.0) * (
            rep * sec.load_kw + rest * restored +
            rep * (healthy - restored))
        sec.eens_contribution_kwh = contribution
        total_eens += contribution
    return total_eens


def compute_transient_eens_kwh(tree: RadialTree, sections: Sequence[Section], *,
                              transient_rate: float, total_load_kw: float,
                              transient_time_min: float = 1.0,
                              reclose_time_min: float = 0.25,
                              reclose_success_probability: float = 0.70,
                              recloser_nodes: Iterable[str] = ()) -> float:
    """EENS سالانهٔ ناشی از **خطاهای گذرا** (kWh/سال) — فقط برای ریکلوزر.

    مدل (مستند و قابل ردیابی):

    * λ_گذرا همانند λ دائمی متناسب طول بین قطعه‌ها پخش می‌شود.
    * خطای گذرا در نبود ریکلوزر، کل فیدر را ``transient_time_min`` دقیقه
      بی‌برق می‌کند.
    * ریکلوزرِ بالادستِ خطا، بار پایین‌دست خود را فقط به‌اندازهٔ
      ``reclose_time_min`` (موفق) یا ``reclose_time_min + (1-p)·transient``
      (شکست وصل مجدد) بی‌برق می‌گذارد؛ بار بالادست همچنان کامل قطع می‌شود.

    ورودی ``recloser_nodes`` مجموعهٔ گره‌هایی است که ریکلوزر روی آن‌ها
    نصب‌شده/فرض‌شده است.
    """
    if transient_rate <= 0 or total_load_kw <= 0 or not tree.order:
        return 0.0
    rec = set(recloser_nodes)
    total_len = sum(float(sc.length_m) for sc in sections) or 0.0
    if total_len <= 0:
        return 0.0
    p_ok = min(1.0, max(0.0, float(reclose_success_probability)))
    protected_interruption = (float(reclose_time_min)
                              + (1.0 - p_ok) * float(transient_time_min))
    total = 0.0
    for sec in sections:
        share = float(sec.length_m) / total_len
        gov = None
        cur = sec.cut_node
        while cur is not None:
            if cur in rec:
                gov = cur
                break
            cur = tree.parent.get(cur)
        protected = float(tree.subtree_load_kw.get(gov, 0.0)) if gov else 0.0
        protected = min(protected, float(total_load_kw))
        interrupted = ((float(total_load_kw) - protected)
                       * float(transient_time_min)
                       + protected * protected_interruption)
        total += (float(transient_rate) * share / 60.0) * interrupted
    return total


def _section_is_descendant(child: Section, parent: Section,
                           sections: Sequence[Section]) -> bool:
    by_index = {s.index: s for s in sections}
    cur = child.parent_index
    guard = 0
    while cur is not None and guard < len(sections) + 2:
        if cur == parent.index:
            return True
        nxt = by_index.get(cur)
        cur = nxt.parent_index if nxt is not None else None
        guard += 1
    return False


# ---------------------------------------------------------------------------
# کاندیدها و نتیجهٔ جست‌وجو
# ---------------------------------------------------------------------------
@dataclass
class SectionCandidate:
    """یک خط/گره قابل نصب کلید."""

    node: str
    feeder_key: str
    depth: int
    edge_id: str
    branch_id: str = ""
    label: str = ""
    downstream_load_kw: float = 0.0
    downstream_ratio: float = 0.0
    downstream_length_m: float = 0.0
    coord: tuple | None = None
    zone_id: str = ""
    rank: int = 0
    #: تجهیز موجود روی همان گره (FCT/DCS/…) — صرفاً اطلاعاتی برای مهندس
    existing_device: str = ""

    def as_dict(self) -> dict:
        return {
            "node": self.node, "feeder_key": self.feeder_key,
            "depth": int(self.depth), "edge_id": self.edge_id,
            "branch_id": self.branch_id, "label": self.label,
            "downstream_load_kw": round(self.downstream_load_kw, 6),
            "downstream_ratio": round(self.downstream_ratio, 9),
            "downstream_length_km": round(self.downstream_length_m / 1000.0, 6),
            "coord": list(self.coord) if self.coord is not None else None,
            "zone_id": self.zone_id, "rank": int(self.rank),
            "existing_device": self.existing_device,
        }


@dataclass
class OptimizationStep:
    """نتیجهٔ نصب k کلید (انتخاب حریصانه)."""

    count: int
    selected: list = dc_field(default_factory=list)     # [SectionCandidate]
    eens_kwh: float = 0.0
    gain_kwh: float = 0.0
    improvement_percent: float = 0.0
    sections: list = dc_field(default_factory=list)     # [Section]

    def as_dict(self) -> dict:
        return {
            "count": int(self.count),
            "selected": [c.as_dict() for c in self.selected],
            "eens_kwh_per_year": round(self.eens_kwh, 6),
            "eens_mwh_per_year": round(self.eens_kwh / 1000.0, 9),
            "gain_kwh_per_year": round(self.gain_kwh, 6),
            "improvement_percent": round(self.improvement_percent, 6),
            "sections": [s.as_dict() for s in self.sections],
        }


@dataclass
class FeederStudy:
    """نتیجهٔ کامل یک فیدر."""

    feeder_key: str
    root: str = ""
    node_count: int = 0
    edge_count: int = 0
    line_length_m: float = 0.0
    total_load_kw: float = 0.0
    failure_rate_per_year: float = 0.0
    failure_rate_source: str = "configured"
    switch_type: str = "sectionalizer"
    repair_time_min: float = 50.0
    transient_rate_per_year: float = 0.0
    transient_eens_kwh: float = 0.0
    restoration_model: str = "uniform"
    backup_kw: float | None = None
    radial: bool = True
    extra_edges: int = 0
    unreachable_edges: int = 0
    existing_cut_nodes: list = dc_field(default_factory=list)
    baseline_sections: list = dc_field(default_factory=list)
    baseline_eens_kwh: float = 0.0
    theoretical_eens_kwh: float = 0.0
    candidates: list = dc_field(default_factory=list)
    rejected: dict = dc_field(default_factory=dict)
    steps: list = dc_field(default_factory=list)
    best: OptimizationStep | None = None
    notes: list = dc_field(default_factory=list)
    status: str = "ok"

    @property
    def best_eens_kwh(self) -> float:
        return self.best.eens_kwh if self.best is not None else self.baseline_eens_kwh

    @property
    def improvement_percent(self) -> float:
        if self.baseline_eens_kwh <= 0:
            return 0.0
        return (self.baseline_eens_kwh - self.best_eens_kwh) / \
            self.baseline_eens_kwh * 100.0

    def as_dict(self) -> dict:
        return {
            "feeder_key": self.feeder_key, "root": self.root,
            "node_count": self.node_count, "edge_count": self.edge_count,
            "line_length_km": round(self.line_length_m / 1000.0, 6),
            "total_load_kw": round(self.total_load_kw, 6),
            "failure_rate_per_year": round(self.failure_rate_per_year, 9),
            "failure_rate_source": self.failure_rate_source,
            "switch_type": self.switch_type,
            "switch_type_fa": SWITCH_TYPE_FA.get(self.switch_type, self.switch_type),
            "repair_time_min": round(self.repair_time_min, 3),
            "transient_rate_per_year": round(self.transient_rate_per_year, 9),
            "transient_eens_kwh_per_year": round(self.transient_eens_kwh, 6),
            "restoration_model": self.restoration_model,
            "backup_kw": self.backup_kw,
            "radial": self.radial, "extra_edges": self.extra_edges,
            "unreachable_edges": self.unreachable_edges,
            "existing_cut_nodes": list(self.existing_cut_nodes),
            "existing_section_count": len(self.baseline_sections),
            "baseline_eens_kwh_per_year": round(self.baseline_eens_kwh, 6),
            "baseline_eens_mwh_per_year": round(self.baseline_eens_kwh / 1000.0, 9),
            "theoretical_eens_kwh_per_year": round(self.theoretical_eens_kwh, 6),
            "baseline_sections": [s.as_dict() for s in self.baseline_sections],
            "candidate_count": len(self.candidates),
            "candidates": [c.as_dict() for c in self.candidates],
            "rejected": dict(self.rejected),
            "steps": [s.as_dict() for s in self.steps],
            "best": self.best.as_dict() if self.best is not None else None,
            "best_eens_kwh_per_year": round(self.best_eens_kwh, 6),
            "improvement_percent": round(self.improvement_percent, 6),
            "notes": list(self.notes),
            "status": self.status,
        }


@dataclass
class SwitchPlacementStudy:
    """خروجی کامل موتور جایابی کلید برای همهٔ فیدرهای مطالعه."""

    settings: dict = dc_field(default_factory=dict)
    feeders: list = dc_field(default_factory=list)      # [FeederStudy]
    assumptions: list = dc_field(default_factory=list)
    notes: list = dc_field(default_factory=list)
    algo_version: str = ""

    # -- جمع‌های کل ---------------------------------------------------------
    @property
    def baseline_eens_kwh(self) -> float:
        return sum(f.baseline_eens_kwh for f in self.feeders)

    @property
    def best_eens_kwh(self) -> float:
        return sum(f.best_eens_kwh for f in self.feeders)

    @property
    def improvement_percent(self) -> float:
        base = self.baseline_eens_kwh
        if base <= 0:
            return 0.0
        return (base - self.best_eens_kwh) / base * 100.0

    @property
    def total_selected(self) -> int:
        return sum(len(f.best.selected) for f in self.feeders if f.best)

    def feeder(self, key: str) -> FeederStudy | None:
        norm = normalize_feeder_key(key) or str(key or "").strip().upper()
        for f in self.feeders:
            if f.feeder_key == norm:
                return f
        return None

    def summary_rows(self) -> list[dict]:
        """ردیف‌های جدول خلاصه (هر فیدر) برای GUI/گزارش."""
        rows = []
        for f in self.feeders:
            best = f.best
            rows.append({
                "feeder_key": f.feeder_key,
                "status": f.status,
                "radial": f.radial,
                "line_length_km": round(f.line_length_m / 1000.0, 3),
                "total_load_kw": round(f.total_load_kw, 1),
                "failure_rate_per_year": round(f.failure_rate_per_year, 3),
                "failure_rate_source": f.failure_rate_source,
                "switch_type": f.switch_type,
                "switch_type_fa": SWITCH_TYPE_FA.get(f.switch_type, f.switch_type),
                "repair_time_min": round(f.repair_time_min, 3),
                "existing_sections": len(f.baseline_sections),
                "candidate_count": len(f.candidates),
                "baseline_eens_mwh": round(f.baseline_eens_kwh / 1000.0, 4),
                "selected_count": len(best.selected) if best else 0,
                "best_eens_mwh": round(f.best_eens_kwh / 1000.0, 4),
                "gain_mwh": round((f.baseline_eens_kwh - f.best_eens_kwh) / 1000.0, 4),
                "improvement_percent": round(f.improvement_percent, 3),
                "selected_labels": [c.label for c in (best.selected if best else [])],
                "selected_nodes": [c.node for c in (best.selected if best else [])],
            })
        return rows

    def candidate_rows(self) -> list[dict]:
        """همهٔ کاندیدها (مرتب بر اساس بار پایین‌دست) برای جدول جزئیات."""
        rows = []
        for f in self.feeders:
            chosen = {c.node for c in (f.best.selected if f.best else [])}
            for c in f.candidates:
                rows.append({
                    "feeder_key": f.feeder_key,
                    "rank": c.rank,
                    "label": c.label,
                    "node": c.node,
                    "zone_id": c.zone_id,
                    "depth": c.depth,
                    "downstream_load_kw": round(c.downstream_load_kw, 2),
                    "downstream_ratio": round(c.downstream_ratio, 4),
                    "downstream_length_km": round(c.downstream_length_m / 1000.0, 3),
                    "selected": c.node in chosen,
                    "coord": c.coord,
                })
        return rows

    def as_dict(self) -> dict:
        return {
            "algo_version": self.algo_version,
            "settings": dict(self.settings),
            "assumptions": list(self.assumptions),
            "notes": list(self.notes),
            "total_baseline_eens_kwh_per_year": round(self.baseline_eens_kwh, 6),
            "total_best_eens_kwh_per_year": round(self.best_eens_kwh, 6),
            "total_improvement_percent": round(self.improvement_percent, 6),
            "total_selected_switches": self.total_selected,
            "total_selected_sectionalizers": self.total_selected,
            "feeders": [f.as_dict() for f in self.feeders],
            "summary_rows": self.summary_rows(),
        }

    def to_markdown(self) -> str:
        s = self.settings
        lines = [
            "# روش جایابی بهینهٔ کلید و کاهش EENS",
            "",
            f"λ پیش‌فرض هر فیدر: {s.get('total_failure_rate_per_year')} خرابی/سال · "
            f"زمان تعمیر: {s.get('repair_time_min')} دقیقه · "
            f"زمان بازیابی: {s.get('restoration_time_min')} دقیقه · "
            f"نوع کلید: {s.get('switch_type_fa', s.get('switch_type'))} · "
            f"سقف کلید هر فیدر: {s.get('max_sectionalizers')}",
            "",
            f"مدل بازیابی: {s.get('restoration_model_fa', s.get('restoration_model'))}",
            "",
            "| فیدر | طول (km) | بار (kW) | λ (۱/سال) | منبع λ | قطعه موجود | "
            "کاندید | EENS پایه (MWh/سال) | تعداد کلید پیشنهادی | EENS نهایی "
            "(MWh/سال) | کاهش (٪) | خطوط پیشنهادی |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for r in self.summary_rows():
            lines.append(
                f"| {r['feeder_key']} | {r['line_length_km']:.2f} | "
                f"{r['total_load_kw']:,.1f} | {r['failure_rate_per_year']:.2f} | "
                f"{r['failure_rate_source']} | {r['existing_sections']} | "
                f"{r['candidate_count']} | {r['baseline_eens_mwh']:.4f} | "
                f"{r['selected_count']} | {r['best_eens_mwh']:.4f} | "
                f"{r['improvement_percent']:.2f} | "
                f"{', '.join(r['selected_labels']) or '—'} |")
        lines += [
            "",
            f"**جمع کل:** EENS پایه {self.baseline_eens_kwh / 1000.0:,.3f} "
            f"MWh/سال → {self.best_eens_kwh / 1000.0:,.3f} MWh/سال "
            f"(کاهش {self.improvement_percent:.2f}٪ با "
            f"{self.total_selected} کلید).",
            "",
        ]
        if self.assumptions:
            lines.append("## فرض‌های صریح")
            lines.append("")
            for a in self.assumptions:
                lines.append(f"- {a}")
            lines.append("")
        if self.notes:
            lines.append("## یادداشت‌ها")
            lines.append("")
            for n in self.notes:
                lines.append(f"- {n}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# موتور
# ---------------------------------------------------------------------------
class SwitchPlacementEngine:
    """جست‌وجوی حریصانهٔ محل کلید (ریکلوزر/سکشنالایزر/سکسیونر) برای کمینه‌کردن EENS."""

    def __init__(self, settings: SwitchPlacementSettings | None = None,
                 zone_policy=None):
        self.settings = settings or SwitchPlacementSettings()
        #: سیاست زون‌بندی (ZonePolicy) برای تشخیص «کلید موجود»؛ None = پیش‌فرض
        self.zone_policy = zone_policy

    # -- تشخیص برش‌های موجود ----------------------------------------------
    def existing_cut_nodes(self, graph: NetworkGraph, net,
                           traces: list) -> dict[str, set]:
        """گره‌هایی که در وضعیت نرمال مرز قطعه‌اند (کلیدهای موجود)."""
        if net is None:
            return {}
        from ..topology.zones import ZoneBuilder
        builder = ZoneBuilder(graph, net, traces, self.zone_policy)
        out: dict[str, set] = {}
        for tr in traces:
            key = normalize_feeder_key(tr.feeder_key) or tr.feeder_key
            cuts = {n for n in (tr.nodes or ())
                    if n in graph.switch_ids_at and builder.node_is_cut(n)}
            out[key] = cuts
        return out

    # ------------------------------------------------------------------
    def run(self, graph: NetworkGraph, traces: list,
            node_load_kw: dict, *, net=None,
            failure_rates: dict | None = None,
            transient_rates: dict | None = None,
            repair_times: dict | None = None,
            failure_rate_source: str = "configured",
            backup_kw: dict | None = None,
            feeders: Iterable[str] | None = None,
            zone_of_node: dict | None = None,
            existing_cut_nodes: dict | None = None,
            branch_labels: dict | None = None) -> SwitchPlacementStudy:
        """اجرای موتور روی همهٔ فیدرهای ردیابی‌شده (یا زیرمجموعهٔ ``feeders``)."""
        st = self.settings
        wanted = ({normalize_feeder_key(f) or str(f).strip().upper()
                   for f in feeders} if feeders else None)
        cuts_map = existing_cut_nodes
        if cuts_map is None:
            cuts_map = self.existing_cut_nodes(graph, net, traces)
        study = SwitchPlacementStudy(
            settings={**st.as_dict(), "failure_rate_source": failure_rate_source},
            assumptions=self._assumptions(failure_rate_source, backup_kw))
        if not traces:
            study.notes.append("هیچ فیدر ردیابی‌شده‌ای وجود ندارد.")
            return study

        for tr in sorted(traces, key=lambda t: t.feeder_key or ""):
            key = normalize_feeder_key(tr.feeder_key) or str(tr.feeder_key)
            if wanted is not None and key not in wanted:
                continue
            rate = None
            source = "configured-default"
            if failure_rates and key in failure_rates:
                value = failure_rates.get(key)
                if value is not None and float(value) >= 0:
                    rate = float(value)
                    source = "outage-lambda"
            if rate is None:
                rate = float(st.total_failure_rate_per_year)
            backup = (float(backup_kw[key]) if backup_kw and key in backup_kw
                      else None)
            rep = None
            if repair_times and key in repair_times:
                value = repair_times.get(key)
                if value is not None and float(value) >= 0:
                    rep = float(value)
            tr_rate = 0.0
            if transient_rates and key in transient_rates:
                value = transient_rates.get(key)
                if value is not None and float(value) >= 0:
                    tr_rate = float(value)
            study.feeders.append(self._run_feeder(
                graph, tr, key, node_load_kw, rate, source, backup,
                cuts_map.get(key, set()), zone_of_node or {}, branch_labels or {},
                net=net, transient_rate=tr_rate, repair_time=rep))
        return study

    # ------------------------------------------------------------------
    def _assumptions(self, failure_rate_source: str,
                     backup_kw: dict | None) -> list[str]:
        st = self.settings
        out = [
            f"نوع کلید مورد جایابی: {SWITCH_TYPE_FA[st.switch_type]} — "
            f"{SWITCH_TYPE_NOTE_FA[st.switch_type]}",
            f"دستهٔ خطای ارزیابی‌شده: "
            f"{'گذرا + دائمی' if st.uses_transient_faults else 'فقط دائمی'}"
            f" (دامنهٔ {SWITCH_TYPE_FA[st.switch_type]}).",
            f"λ هر فیدر = {st.total_failure_rate_per_year:g} خرابی/سال "
            "(یا λ واقعی خاموشی همان فیدر، هرگاه موجود باشد) و بین قطعات "
            "متناسب با طول خط توزیع می‌شود — قاعدهٔ کد مرجع PowerFactory.",
            f"زمان تعمیر قطعهٔ معیوب = {st.repair_time_min:g} دقیقه (یا r واقعی "
            f"همان فیدر در روش خودکار) و زمان "
            f"بازیابی بار سالم = {st.effective_restoration_time_min:g} دقیقه"
            + (" (سکسیونر: بازیابی دستی)." if st.switch_type == SWITCH_DISCONNECTOR
               else "."),
            f"مدل بازیابی: {RESTORATION_MODEL_FA[st.restoration_model]}.",
        ]
        if backup_kw:
            out.append("سقف ظرفیت پشتیبان برای بازپُل بار پایین‌دست اعمال شد "
                       "(backup_kw به‌ازای فیدر).")
        else:
            out.append("ظرفیت پشتیبان نامحدود فرض شد (همان فرض کد مرجع)؛ "
                       "برای نتیجهٔ محافظه‌کارانه، ظرفیت پشتیبان را وارد کنید.")
        if st.use_existing_switches:
            out.append("کلیدهای موجود (مرزهای زون) در حالت پایه قطعه‌بندی "
                       "می‌کنند؛ EENS پایه، وضعیت فعلی شبکه است.")
        else:
            out.append("کلیدهای موجود در حالت پایه نادیده گرفته شدند "
                       "(EENS پایه = فیدر یک‌قطعه‌ای؛ مقایسه با کد مرجع).")
        if st.uses_transient_faults:
            out.append(
                f"خطاهای گذرا (مدت ≤ {st.transient_max_duration_min:g} دقیقه) "
                f"با λ گذرای همان فیدر و وقفهٔ {st.transient_interruption_min:g} "
                f"دقیقه مدل شدند؛ ریکلوزر وقفهٔ بار پایین‌دست را به "
                f"{st.reclose_time_min:g} دقیقه (احتمال موفقیت "
                f"{st.reclose_success_probability:.0%}) کاهش می‌دهد.")
        if failure_rate_source == "configured":
            out.append("منبع λ «پیش‌فرض تنظیمات» است؛ در صورت وجود ماتریس "
                       "λ/r خاموشی، حالت «λ واقعی خاموشی» را انتخاب کنید.")
        return out

    # ------------------------------------------------------------------
    def _run_feeder(self, graph: NetworkGraph, tr, key: str,
                    node_load_kw: dict, rate: float, source: str,
                    backup: float | None, existing_cuts: set,
                    zone_of_node: dict, branch_labels: dict,
                    net=None, transient_rate: float = 0.0,
                    repair_time: float | None = None) -> FeederStudy:
        st = self.settings
        rep_min = (float(repair_time) if repair_time is not None
                   else float(st.repair_time_min))
        rest_min = st.effective_restoration_time_min
        tr_rate = float(transient_rate or 0.0) if st.uses_transient_faults else 0.0
        tree = build_radial_tree(graph, tr, node_load_kw)
        study = FeederStudy(
            feeder_key=key, root=tree.root, node_count=len(tree.order),
            edge_count=len(tree.order) - 1 if tree.order else 0,
            line_length_m=tree.total_length_m, total_load_kw=tree.total_load_kw,
            failure_rate_per_year=rate, failure_rate_source=source,
            switch_type=st.switch_type, repair_time_min=rep_min,
            transient_rate_per_year=tr_rate,
            restoration_model=st.restoration_model, backup_kw=backup,
            radial=not tree.extra_edge_ids,
            extra_edges=len(tree.extra_edge_ids),
            unreachable_edges=len(tree.unreachable_edge_ids),
            theoretical_eens_kwh=rate / 60.0 * rep_min * tree.total_load_kw,
        )
        if not tree.order:
            study.status = "empty"
            study.notes.append("درخت شعاعی ساخته نشد (گره ریشه/یال ردیابی نیست).")
            return study
        if tree.total_length_m <= 0:
            study.status = "no-length"
            study.notes.append("طول خط صفر است؛ توزیع λ ممکن نیست.")
            return study
        if tree.extra_edge_ids:
            study.notes.append(
                f"{len(tree.extra_edge_ids)} یال اضافی (حلقه/خط موازی) در ردیابی "
                "وجود دارد؛ درخت پوشای BFS ساخته شد و طول یال‌های اضافی به گرهٔ "
                "جد مشترک افزوده شد (TOPO/SEC-NOT-RADIAL).")
        if tree.total_load_kw <= 0:
            study.notes.append(
                "بار فیدر صفر است؛ EENS صفر می‌شود — مدل بار را کامل کنید.")

        if st.use_existing_switches:
            study.existing_cut_nodes = sorted(
                n for n in existing_cuts if n in tree.parent and n != tree.root)
        if st.effective_restoration_time_min >= rep_min:
            study.notes.append(
                f"زمان بازیابی بار سالم ({st.effective_restoration_time_min:g} "
                f"دقیقه) از زمان تعمیر ({rep_min:g} دقیقه) کمتر نیست؛ در این "
                "حالت جداسازی خطا بار سالم را زودتر برنمی‌گرداند و نصب کلید "
                "EENS را کاهش نمی‌دهد — زمان بازیابی/نوع کلید را بازبینی کنید.")

        base_cuts = set(study.existing_cut_nodes)
        study.baseline_sections = build_sections(tree, base_cuts)

        def _total_eens(sections, cut_nodes) -> tuple[float, float]:
            """(EENS کل، بخش گذرا) برای یک مجموعهٔ برش."""
            perm = compute_eens_kwh(
                sections, failure_rate=rate,
                total_length_m=tree.total_length_m,
                total_load_kw=tree.total_load_kw,
                repair_time_min=rep_min,
                restoration_time_min=rest_min,
                restoration_model=st.restoration_model, backup_kw=backup)
            tr = (compute_transient_eens_kwh(
                      tree, sections, transient_rate=tr_rate,
                      total_load_kw=tree.total_load_kw,
                      transient_time_min=st.transient_interruption_min,
                      reclose_time_min=st.reclose_time_min,
                      reclose_success_probability=st.reclose_success_probability,
                      recloser_nodes=cut_nodes)
                  if (st.uses_transient_faults and tr_rate > 0) else 0.0)
            return perm + tr, tr

        _base_total, _base_tr = _total_eens(study.baseline_sections, base_cuts)
        study.baseline_eens_kwh = _base_total
        study.transient_eens_kwh = _base_tr

        # -- کاندیدها -------------------------------------------------------
        rejected = {"no_downstream_load": 0, "over_load_ratio": 0,
                    "too_shallow": 0, "already_has_device": 0,
                    "head_edge": 0, "zero_length": 0}
        candidates: list[SectionCandidate] = []
        device_nodes = set(getattr(graph, "switch_ids_at", {}) or {})
        transformer_nodes = set(getattr(graph, "transformer_ids_at", {}) or {})
        switch_by_id = {s.id: s for s in (getattr(net, "switches", None) or [])}
        for node in tree.order:
            if node == tree.root:
                continue
            depth = tree.depth.get(node, 0)
            edge_id = tree.parent_edge.get(node)
            parent = tree.parent.get(node)
            if edge_id is None or parent is None:
                continue
            if parent == tree.root and depth == 1:
                rejected["head_edge"] += 1
                continue
            if node in base_cuts:
                # مرز موجود — سکشنالایزر دوباره معنی ندارد
                rejected["already_has_device"] += 1
                continue
            existing_codes = sorted({
                getattr(switch_by_id.get(sid), "family", None).value[:3].upper()
                for sid in (graph.switch_ids_at.get(node) or ())
                if getattr(switch_by_id.get(sid), "family", None) is not None})
            if st.exclude_nodes_with_switch and existing_codes:
                rejected["already_has_device"] += 1
                continue
            if st.exclude_transformer_terminal_nodes and node in transformer_nodes:
                rejected["already_has_device"] += 1
                continue
            if depth < st.min_candidate_depth:
                rejected["too_shallow"] += 1
                continue
            downstream = tree.subtree_load_kw.get(node, 0.0)
            if downstream <= 0:
                rejected["no_downstream_load"] += 1
                continue
            ratio = (downstream / tree.total_load_kw
                     if tree.total_load_kw > 0 else 0.0)
            if ratio > st.max_downstream_load_ratio:
                rejected["over_load_ratio"] += 1
                continue
            length = tree.subtree_length_m.get(node, 0.0)
            if length <= 0:
                rejected["zero_length"] += 1
                continue
            edge = graph.edges.get(edge_id)
            node_obj = graph.nodes.get(node)
            branch_id = getattr(edge, "branch_id", "") or ""
            candidates.append(SectionCandidate(
                node=node, feeder_key=key, depth=depth, edge_id=edge_id,
                branch_id=branch_id,
                label=(branch_labels.get(branch_id)
                       or _candidate_label(key, edge, node_obj, depth)),
                downstream_load_kw=downstream, downstream_ratio=ratio,
                downstream_length_m=length,
                coord=(tuple(node_obj.coord) if node_obj is not None
                       and node_obj.coord is not None else None),
                zone_id=str(zone_of_node.get(node, "") or ""),
                existing_device="/".join(existing_codes)))

        if st.max_candidates_per_feeder and \
                len(candidates) > int(st.max_candidates_per_feeder):
            study.notes.append(
                f"تعداد کاندیدها به {st.max_candidates_per_feeder} محدود شد "
                f"(از {len(candidates)}) — فقط برای کارایی.")
            candidates = sorted(candidates,
                                key=lambda c: (-c.downstream_load_kw, c.node)
                                )[:int(st.max_candidates_per_feeder)]
        candidates.sort(key=lambda c: (-c.downstream_load_kw, c.depth, c.node))
        for i, c in enumerate(candidates, start=1):
            c.rank = i
        study.candidates = candidates
        study.rejected = rejected

        # -- جست‌وجوی حریصانه ----------------------------------------------
        current_eens = study.baseline_eens_kwh
        selected_nodes: list[str] = []
        selected: list[SectionCandidate] = []
        for step in range(1, int(st.max_sectionalizers) + 1):
            best_c, best_eens, best_sections = None, None, None
            available = [c for c in candidates if c.node not in selected_nodes]
            for c in available:
                trial_cuts = base_cuts | set(selected_nodes) | {c.node}
                sections = build_sections(tree, trial_cuts)
                eens, _ = _total_eens(sections, trial_cuts)
                if best_eens is None or eens < best_eens - 1e-12:
                    best_c, best_eens, best_sections = c, eens, sections
            if best_c is None:
                study.notes.append("کاندید معتبر دیگری برای نصب وجود ندارد.")
                break
            gain = current_eens - best_eens
            if st.stop_without_gain and gain <= float(st.min_gain_kwh_per_year):
                if gain < -1e-6:
                    why = ("مدل با کمینهٔ زمان بازیابی/تعمیر کار می‌کند؛ این "
                           "گزینه EENS را بهبود نمی‌دهد")
                else:
                    why = "بهبود محسوسی ندارد"
                study.notes.append(
                    f"گام {step}: کاندید بعدی {why} (تغییر خالص "
                    f"{gain:,.3f} kWh/سال) → جست‌وجو متوقف شد.")
                break
            selected_nodes.append(best_c.node)
            selected.append(best_c)
            current_eens = best_eens
            improvement = ((study.baseline_eens_kwh - current_eens)
                           / study.baseline_eens_kwh * 100.0
                           if study.baseline_eens_kwh > 0 else 0.0)
            study.steps.append(OptimizationStep(
                count=step, selected=list(selected), eens_kwh=current_eens,
                gain_kwh=study.baseline_eens_kwh - current_eens,
                improvement_percent=improvement,
                sections=best_sections or []))
        study.best = study.steps[-1] if study.steps else OptimizationStep(
            count=0, selected=[], eens_kwh=study.baseline_eens_kwh,
            gain_kwh=0.0, improvement_percent=0.0,
            sections=list(study.baseline_sections))
        if not candidates:
            study.notes.append(
                "هیچ کاندید معتبری پیدا نشد (بار پایین‌دست/عمق/سهم بار).")
        return study


# ---------------------------------------------------------------------------
# کمکی‌های مستقل (قابل آزمون بدون گراف)
# ---------------------------------------------------------------------------
def eens_single_section_kwh(load_kw: float, failure_rate_per_year: float,
                            repair_time_min: float) -> float:
    """EENS پایهٔ فیدر یک‌قطعه‌ای — لنگر تحلیلی کد مرجع."""
    return float(failure_rate_per_year) / 60.0 * float(repair_time_min) * \
        float(load_kw)


def length_weighted_lambdas(lengths_m: Sequence[float],
                            failure_rate_per_year: float) -> list[float]:
    """λ هر قطعه متناسب با طول (Σ قطعه‌ها = λ فیدر)."""
    total = float(sum(float(x) for x in lengths_m))
    if total <= 0:
        return [0.0 for _ in lengths_m]
    return [float(failure_rate_per_year) * float(x) / total for x in lengths_m]


def theoretical_eens_kwh(load_kw: float, failure_rate_per_year: float,
                         repair_time_min: float) -> float:
    """EENS نظری کد مرجع: (λ/60)·T_rep·P_total — برای کنترل محاسبه."""
    return eens_single_section_kwh(load_kw, failure_rate_per_year,
                                   repair_time_min)


# ---------------------------------------------------------------------------
# نام‌های قدیمی (سازگاری) — کد جدید از نام‌های SwitchPlacement* استفاده کند
# ---------------------------------------------------------------------------
SectionalizerSettings = SwitchPlacementSettings
SectionalizerStudy = SwitchPlacementStudy
SectionalizerEngine = SwitchPlacementEngine
SwitchCandidate = SectionCandidate
PlacementStep = OptimizationStep
