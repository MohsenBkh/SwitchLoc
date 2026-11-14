# -*- coding: utf-8 -*-
"""انتقال بار با Tieهای اتوماسیون — مدل مشترک جداول ۱۴/۱۵ و رابطه (۸)/(۱۱).

معناشناسی (سطح اول، بدون پخش بار — A-10):

  1. خطای زون/قطعهٔ i مجموعه خروجی = زیردرختِ همان گره در درخت رادیال است
     (بالادست با وصل مجدد بریکر برمی‌گردد — الگوی رابطه (۸)).
  2. عضو معیوب جداسازی می‌شود: یال‌های آن از مدار خارج می‌شوند و عبور
     توان از آن ممنوع است.
  3. جزیره‌های بازمانده = مؤلفه‌های همبندی اعضای پایین‌دست (بدون عضو
     معیوب): دو عضو متصل‌اند اگر نقطهٔ جداسازی مشترکی داشته باشند و
     حداقل یک تجهیزِ رسانا روی آن نقطه توان را رد کند (گره "مانع" طبق
     ``barrier_cut_nodes`` جزیره‌ها را جدا می‌کند). برای زون‌ها،
     «گره مشترک رسانا» ملاک همبندی است؛ برای درخت قطعه‌ها، هر کلید مرزیِ
     رسانا، قطعهٔ بالا و پایین را به هم وصل می‌کند. هر دو با ساختار
     درخت جداسازی سازگارند.
  4. برای هر جزیره:  restored = min(بار جزیره، مجموع ظرفیت Tieهای
     اتوماسیون‌پذیرِ همان جزیره) — ظرفیت هر فیدر پشتیبان فقط برای خود
     همان جزیره دیده می‌شود (جمع ظرفیت Tieهای همان جزیره).
  5. عضو معیوب هرگز بازپُل نمی‌شود؛ بالادست هرگز در مجموعه خروجی نیست.

محدودیت ثبت‌شده (بند ۱۹): ظرفیت دو Tie از یک فیدر پشتیبانِ واحد در یک
جزیره دوبار شمرده می‌شود؛ جزیره‌ای با دو Tie از یک فیدر واحد در عمل
به رزرو همان یک فیدر محدود است. این حالت نادر است و در بازبینی مهندس
صراحتاً مطرح می‌شود.
"""
from __future__ import annotations

from collections import defaultdict
from itertools import combinations


def components(ids, links) -> list[list[str]]:
    """مؤلفه‌های همبندی روی ``ids`` با یال‌های ``links`` (union-find فشرده،
    ریشهٔ قطعی به ترتیب الفبایی شناسه)."""
    parent = {i: i for i in ids}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for a, b in links:
        if a not in parent or b not in parent or a == b:
            continue
        ra, rb = find(a), find(b)
        if ra == rb:
            continue
        if rb < ra:
            ra, rb = rb, ra
        parent[rb] = ra
    comp: dict[str, list[str]] = defaultdict(list)
    for i in ids:
        comp[find(i)].append(i)
    return [sorted(v) for _root, v in sorted(comp.items())]


def shared_node_links(id_to_nodes: dict[str, set],
                      barrier_nodes: set[str] | None = None,
                      ) -> set[tuple[str, str]]:
    """جفت‌هایی از شناسه‌ها که حداقل یک گرهٔ رسانای مشترک دارند.

    ``barrier_nodes``: گره‌های مرزی که هیچ تجهیزی در آن‌ها توان را رد
    نمی‌کند (همهٔ تجهیزها NO غیراتوماسیون یا از سرویس خارج‌اند) —
    این گره‌ها جزیره‌ها را از هم جدا می‌کنند.
    """
    barrier = set(barrier_nodes or ())
    node_to_ids: dict[str, list[str]] = defaultdict(list)
    for i, nodes in id_to_nodes.items():
        for n in nodes:
            if n in barrier:
                continue
            node_to_ids[n].append(i)
    links: set[tuple[str, str]] = set()
    for ids in node_to_ids.values():
        if len(ids) < 2:
            continue
        for a, b in combinations(sorted(ids), 2):
            links.add((a, b))
    return links


def cut_node_links(upper_of: dict[str, str],
                   lower_of: dict[str, str],
                   barrier_nodes: set[str] | None = None,
                   ) -> set[tuple[str, str]]:
    """پیوند قطعهٔ بالا ↔ قطعهٔ پایین در هر کلید مرزیِ رسانا (درخت قطعه‌ها)."""
    barrier = set(barrier_nodes or ())
    links: set[tuple[str, str]] = set()
    for node, lower in lower_of.items():
        if node in barrier:
            continue
        upper = upper_of.get(node)
        if upper is not None and upper != lower:
            links.add(tuple(sorted((upper, lower))))
    return links


def barrier_cut_nodes(graph, net, ties) -> set[str]:
    """گره‌های مرزی که توان را عبور نمی‌دهند.

    تجهیز روی گره X هنگام جداسازی خطا توان را عبور می‌دهد اگر:
      * مسیر وصل‌شوندهٔ نرمال آن NC یا وضعیت نامعلوم باشد و در سرویس باشد؛
      * یا یک اتصال اتوماسیون‌پذیرِ روی همین گره باشد (طرح پس از خطا
        آن را می‌بندد — همان سازوکار بازپُل).
    گره‌ای که *هیچ‌کدام* از تجهیزهایش این شروط را نداشته باشد
    (همه NO غیراتوماسیون یا OUT_OF_SERVICE) مانع است و جزیره‌ها را
    جدا می‌کند؛ بستن دستیِ این کلیدها طبق جدول ۱۳ خارج از بازپُل است.
    """
    from ..domain.enums import SwitchState
    switches = {s.id: s for s in getattr(net, "switches", ())}
    auto_nodes = {t.node for t in ties if getattr(t, "automation_capable", False)
                  and getattr(t, "node", None)}
    barriers: set[str] = set()
    for node, sids in graph.switch_ids_at.items():
        conducts = node in auto_nodes
        if not conducts:
            for sid in sids:
                sw = switches.get(sid)
                if sw is None:
                    continue
                if sw.current_state == SwitchState.OUT_OF_SERVICE:
                    continue
                if (sw.normally_state or "").strip().upper() == "NO":
                    continue                     # باز مگر با اسکِم — اینجا نه
                conducts = True                  # NC / نامعلوم → رسانا (TOPO-POL-01)
                break
        if not conducts:
            barriers.add(node)
    return barriers


def islands_with_ties(member_ids, member_load: dict[str, float],
                      tie_cap_by_id: dict[str, float],
                      links) -> float:
    """بار کل قابل بازپُل (kW) برای یک خطای مشخص.

    ``member_ids``: شناسه‌های اعضای پایین‌دستِ عضو معیوب (بدون خودش).
    ``member_load``: kW هر عضو. ``tie_cap_by_id``: ظرفیت Tie هر عضو
    (۰ یعنی Tie ندارد). ``links``: یال‌های همبندی بین اعضا.
    """
    remaining = {i: float(member_load.get(i, 0.0) or 0.0)
                 for i in member_ids}
    if not remaining or sum(remaining.values()) <= 0.0:
        return 0.0
    restored = 0.0
    for comp in components(list(member_ids), links):
        load = sum(remaining[i] for i in comp)
        cap = 0.0
        for i in comp:
            cap += float(tie_cap_by_id.get(i, 0.0) or 0.0)
        take = min(load, cap)
        if take > 0.0:
            restored += take
    return restored
