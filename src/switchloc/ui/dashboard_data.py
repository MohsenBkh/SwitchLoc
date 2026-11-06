# -*- coding: utf-8 -*-
"""Dashboard data assembly — Qt-free (the management view of a study).

`build_dashboard()` merges, per feeder, the normal-state trace (nodes /
edges / km / transformers), the outage λ/r matrix (Phase 3), the n-1
EP/TL results, the formula-(1) ranking (table 16), the selected scheme
per feeder and the table-18 CE/CN comparison — one row per feeder,
ready for the Qt dashboard tab or any other presenter.

Discipline: the engineering logic lives here and is testable without
Qt; the Qt tab (`ui/qt/dashboard_tab.py`) only renders the dict it
receives (same split as map_canvas.py).
"""
from __future__ import annotations

from ..domain.entities import CanonicalNetwork
from ..topology.tracing import feeder_key as _feeder_key


def gis_transformer_map(net: CanonicalNetwork | None) -> dict:
    """ترانس‌ها به تفکیک فیدر بر اساس «برچسب GIS» (T_FeederNa).

    این «ترکیب رسمی فیدر» است که شرکت توزیع می‌شناسد (جدول کاربر) و
    ممکن است با تعداد ردیابی‌شده (مسیر تغذیه واقعی) متفاوت باشد —
    اختلاف این دو، ایراد داده GIS است (مثلاً ترانس‌های F6 با برچسب F5)
    و باید صریح گزارش شود، نه پنهان (بند ۱۹). خروجی:
      feeder_key → {"qty": تعداد, "s_rated_kva": جمع ظرفیت نامی,
                    "blank_label": تعداد بدون برچسب,
                    "no_capacity": تعداد بدون ظرفیت}
    """
    out: dict[str, dict] = {}
    for t in getattr(net, "transformers", []) or []:
        k = _feeder_key(t.feeder_name) or "(بدون برچسب)"
        d = out.setdefault(k, {"qty": 0, "s_rated_kva": 0.0,
                               "blank_label": 0, "no_capacity": 0})
        d["qty"] += 1
        if t.capacity_kva:
            d["s_rated_kva"] += float(t.capacity_kva)
        else:
            d["no_capacity"] += 1
        if not (t.feeder_name or "").strip():
            d["blank_label"] += 1
    return out


def zone_load_map(topo, net, load_model=None, placement=None) -> dict[str, float]:
    """Exact per-zone connected load (kW) on the same model as N-1.

    After a placement run the persisted N-1 zone allocation is authoritative.
    Before placement, reproduce its transformer allocation from the current
    load-model settings and assign each transformer to one deterministic
    owning zone (lowest zone_no at a shared boundary).
    """
    if topo is None or net is None:
        return {}
    if placement is not None:
        try:
            vals = placement.n1.zone_load_kw
            if vals:
                flat = {}
                for feeder_or_zone, value in vals.items():
                    if isinstance(value, dict):
                        for zone_id, kw in value.items():
                            flat[str(zone_id)] = float(kw or 0.0)
                    else:
                        flat[str(feeder_or_zone)] = float(value or 0.0)
                return flat
        except Exception:
            pass
    from ..reliability.load_model import LoadModelSettings, build_node_loads
    settings = LoadModelSettings.from_dict(dict(load_model or {}))
    lm = build_node_loads(topo.graph, net, settings)
    by_id = {t.id: t for t in net.transformers}
    tr_load: dict[str, float] = {}
    for node, tids in topo.graph.transformer_ids_at.items():
        ids = [tid for tid in tids if tid in by_id]
        if not ids:
            continue
        node_kw = max(0.0, float(lm.node_kw.get(node, 0.0) or 0.0))
        weights = {tid: max(0.0, float(by_id[tid].capacity_kva or 0.0))
                   for tid in ids}
        total = sum(weights.values())
        if total <= 0:
            weights = {tid: 1.0 for tid in ids}
            total = float(len(ids))
        for tid in ids:
            tr_load[tid] = node_kw * weights[tid] / total
    out: dict[str, float] = {}
    zones = list(getattr(topo.zones, "zones", []) or [])
    by_zone = {z.id: z for z in zones}
    node_owner: dict[str, str] = {}
    for z in sorted(zones, key=lambda z: (z.feeder, z.zone_no, z.id)):
        for nid in z.nodes:
            old = node_owner.get(nid)
            if old is None or z.zone_no < by_zone[old].zone_no:
                node_owner[nid] = z.id
    for z in zones:
        out[z.id] = 0.0
    for node, tids in topo.graph.transformer_ids_at.items():
        zid = node_owner.get(node)
        if zid is not None:
            out[zid] += sum(tr_load.get(tid, 0.0) for tid in tids)
    return out


def _length_label(length_m: float) -> str:
    """Engineering-friendly zone length: metres below 1 km, km otherwise."""
    value = max(0.0, float(length_m or 0.0))
    return f"{value:,.0f} m" if value < 1000.0 else f"{value / 1000.0:,.2f} km"


def zone_rows(topo, net=None, placement=None, load_model=None) -> list[dict]:
    """Build explicit, project-scoped zone records for the dashboard.

    When placement exists, its strict n-1 zone tree and load allocation are
    authoritative. Otherwise use the current topology zones and the same
    configured load model used by placement.
    """
    if topo is None:
        return []
    rows = []
    trees = getattr(getattr(placement, "n1", None), "trees", {}) or {}
    if trees:
        for fk, tree in sorted(trees.items()):
            for z in sorted(tree.zones, key=lambda x: (x.zone_no, x.id)):
                length = float(getattr(z, "length_m", 0.0) or 0.0)
                rows.append({
                    "feeder_key": fk, "zone_id": z.id, "zone_no": z.zone_no,
                    "kind": z.kind, "length_m": round(length, 1),
                    "length_label": _length_label(length),
                    "nodes": len(z.nodes), "edges": len(z.edges),
                    "transformers": len(z.transformer_ids),
                    "loads": len(z.load_ids),
                    "load_kw": round(float(tree.load_kw.get(z.id, 0.0) or 0.0), 2),
                    "source": "placement.n1",
                })
        return rows
    model = dict(load_model or {})
    has_explicit_load_model = bool(model) and (
        model.get("level") != "scaled" or bool(model.get("feeder_pq")))
    loads = (zone_load_map(topo, net, model, None)
             if has_explicit_load_model else {})
    for z in sorted(getattr(getattr(topo, "zones", None), "zones", []) or [],
                    key=lambda x: (x.feeder, x.zone_no, x.id)):
        length = float(getattr(z, "length_m", 0.0) or 0.0)
        rows.append({
            "feeder_key": z.feeder, "zone_id": z.id, "zone_no": z.zone_no,
            "kind": z.kind, "length_m": round(length, 1),
            "length_label": _length_label(length),
            "nodes": len(z.nodes), "edges": len(z.edges),
            "transformers": len(z.transformer_ids), "loads": len(z.load_ids),
            "load_kw": (round(float(loads[z.id] or 0.0), 2)
                        if z.id in loads else None),
            "source": "topology_load_model" if z.id in loads else "not_calculated",
        })
    return rows


# ---------------------------------------------------------------------------
# helpers — tolerate every partial input (no placement yet, no outage yet…)
# ---------------------------------------------------------------------------
def _outage_lambda_rows(outage) -> list[dict]:
    """OutageResult **or** a persisted-outage dict → λ/r rows as dicts."""
    if outage is None:
        return []
    rows = getattr(outage, "lambda_r", None)
    if rows is None and isinstance(outage, dict):
        rows = outage.get("lambda_r")
    out = []
    for r in rows or []:
        if hasattr(r, "as_dict"):
            out.append(r.as_dict())
        elif isinstance(r, dict):
            out.append(r)
    return out


def outage_coverage(outage) -> dict:
    """پوشش داده (نیاز ۸) از OutageResult یا حافظه پایدار — JSON-safe."""
    if outage is None:
        return {}
    cov = getattr(outage, "levels", {})
    cov = (cov or {}).get("coverage") if isinstance(cov, dict) else None
    if cov is None and isinstance(outage, dict):
        cov = (outage.get("summary") or {}).get("coverage")
        if cov is None:
            cov = outage.get("coverage")
    if not cov:
        return {}
    if hasattr(cov, "as_dict"):
        return cov.as_dict()
    return dict(cov)


def capacity_rows_map(capacity_rows) -> dict:
    """GUI/store capacity rows → feeder_key → dict (نیاز ۹)."""
    out = {}
    for r in capacity_rows or []:
        fk = str(r.get("feeder_key", "")).strip().upper()
        if not fk:
            continue
        nominal = r.get("nominal_kw")
        peak = r.get("peak_kw")
        emergency = r.get("emergency_kw")
        reserve = (nominal - peak) if (nominal is not None
                                       and peak is not None) else None
        out[fk] = {
            "nominal_kw": nominal, "peak_kw": peak,
            "emergency_kw": emergency, "reserve_kw": reserve,
            "status": ("ok" if (nominal is not None and
                                peak is not None)
                       else "needs_capacity_confirmation"),
        }
    return out


def plan_status_map(placement) -> dict:
    """placement → feeder_key → plan-status dict (نیاز ۱۰، بدون اجبار)."""
    if placement is None:
        return {}
    recs = getattr(placement, "recommendation", None) or []
    out = {}
    for r in recs:
        fk = r.get("feeder_key")
        if fk:
            out[fk] = {"status": r.get("status"),
                       "status_fa": r.get("status_fa"),
                       "scheme_kind": r.get("scheme_kind"),
                       "n_switches": r.get("n_switches", 0),
                       "approved": r.get("approved", False),
                       "reasons": r.get("decision_reasons", [])}
    return out


# ---------------------------------------------------------------------------
# نیاز کاربر — ریشه‌یابی اختلاف تعداد ترانس‌ها (جدول آشتی فیدرها)
# ---------------------------------------------------------------------------
def reconciliation_rows(rows: list[dict], gis_tr: dict | None) -> list[dict]:
    """جدول آشتی تعداد ترانس هر فیدر: برچسب GIS در برابر مسیر تغذیه.

    هر اختلاف = یا داده ناقص GIS (برچسب اشتباه/خالی، مثال واقعی:
    ترانس‌های F6 با برچسب F5 در خلخال) یا قطعه‌ای که با وضعیت کلیدها
    از منبع فیدر جدا افتاده (پشت کلید باز). هیچ‌کدام حدس زده
    نمی‌شود؛ فقط شمرده و گزارش می‌شوند (بند ۱۹).
    """
    out = []
    for r in rows:
        k = r["feeder_key"]
        g = (gis_tr or {}).get(k, {})
        out.append({
            "feeder_key": k,
            "qty_gis": g.get("qty", 0),
            "s_rated_kva": round(g.get("s_rated_kva", 0.0), 1),
            "qty_traced": r.get("transformers", 0),
            "diff": (g.get("qty", 0) - r.get("transformers", 0)),
            "blank_label": g.get("blank_label", 0),
            "no_capacity": g.get("no_capacity", 0),
        })
    for k, g in sorted((gis_tr or {}).items()):
        if k == "(بدون برچسب)" or any(o["feeder_key"] == k for o in out):
            continue
        out.append({"feeder_key": k, "qty_gis": g.get("qty", 0),
                    "s_rated_kva": round(g.get("s_rated_kva", 0.0), 1),
                    "qty_traced": 0, "diff": g.get("qty", 0),
                    "blank_label": g.get("blank_label", 0),
                    "no_capacity": g.get("no_capacity", 0)})
    return out


def _index_by(rows: list[dict], key: str = "feeder_key") -> dict:
    return {r.get(key): r for r in rows if r.get(key)}


def summarize_outage(outage, feeder_keys=None) -> dict:
    """Outage block of the dashboard (records, classes, years, λ/r).

    When a study scope is active, live records are filtered before counts
    and class summaries are built. Persisted compact payloads are filtered
    by their per-feeder lambda rows; aggregate-only counts are not falsely
    presented as scope-specific.
    """
    selected = ({str(k).strip() for k in feeder_keys if str(k).strip()}
                if feeder_keys else None)
    rows = _outage_lambda_rows(outage)
    if selected is not None:
        rows = [r for r in rows if r.get("feeder_key") in selected]
    if outage is None:
        return {"available": False, "lambda_r": []}
    if isinstance(outage, dict):                 # persisted-store payload
        summary = outage.get("summary") or {}
        records = outage.get("records") or []
        if selected is not None and records:
            records = [r for r in records
                       if (r.get("feeder_key") if isinstance(r, dict)
                           else getattr(r, "feeder_key", None)) in selected]
        scoped_records_known = bool(records) or selected is None
        classes = summary.get("class_summary", {})
        years = summary.get("years", [])
        if records:
            classes, years = {}, set()
            for r in records:
                get = r.get if isinstance(r, dict) else lambda k, d=None: getattr(r, k, d)
                cls = get("outage_class", "")
                if cls:
                    classes[cls] = classes.get(cls, 0) + 1
                if get("year"):
                    years.add(get("year"))
            years = sorted(years)
        return {
            "available": True,
            "source": outage.get("outage_run_id") or "",
            "records": (len(records) if records else
                        (summary.get("records", 0) if scoped_records_known else None)),
            "rows_empty_skipped": (summary.get("rows_empty_skipped", 0)
                                    if selected is None else None),
            "class_summary": classes if scoped_records_known else {},
            "years": years if scoped_records_known else [],
            "lambda_r": rows,
        }
    # OutageResult object
    records = list(getattr(outage, "records", []) or [])
    if selected is not None:
        records = [r for r in records if getattr(r, "feeder_key", None) in selected]
    classes = {}
    for r in records:
        cls = getattr(r, "outage_class", "")
        if cls:
            classes[cls] = classes.get(cls, 0) + 1
    return {
        "available": True,
        "source": getattr(outage, "outage_run_id", "") or "",
        "records": len(records),
        "rows_empty_skipped": (getattr(outage, "reader_stats", {}).get(
            "rows_empty_skipped", 0) if selected is None else None),
        "class_summary": (classes if selected is not None else
                          (getattr(outage, "levels", {}).get("class_summary", {}) or classes)),
        "years": sorted({r.year for r in records if getattr(r, "year", None)}),
        "lambda_r": rows,
    }


def feeder_rows(traces, lam_rows: list[dict], snap: dict,
                cap_map: dict | None = None,
                plan_map: dict | None = None,
                gis_tr: dict | None = None) -> list[dict]:
    """One merged row per feeder — the heart of the dashboard.

    ``gis_tr``: ترانس‌ها بر اساس برچسب GIS (ترکیب رسمی فیدر) — ستون
    «ترانس (GIS)» و جمع ظرفیت نامی؛ عدد ردیابی‌شده در ستون کناری می‌ماند
    تا اختلاف داده صریح دیده شود (ریشه‌یابی اختلاف تعداد ترانس خلخال).
    """
    lam_by = _index_by(lam_rows)
    eptl_by = _index_by(snap.get("table14_eptl") or [])
    rank_by = _index_by(snap.get("ranking") or [])
    rec_by = _index_by(snap.get("recommendation") or [])
    cap_map = cap_map or {}
    plan_map = plan_map or {}
    rows = []
    for t in sorted(traces, key=lambda t: t.feeder_key):
        k = t.feeder_key
        lam = lam_by.get(k, {})
        ep = eptl_by.get(k, {})
        rk = rank_by.get(k, {})
        rec = rec_by.get(k, {})
        cap = cap_map.get(k, {})
        plan = plan_map.get(k, {})
        g = (gis_tr or {}).get(k, {})
        rows.append({
            "feeder_key": k,
            "nodes": len(t.nodes),
            "edges": len(t.edges),
            "km": round(t.length_m / 1000.0, 2),
            "transformers": len(t.transformer_ids),
            "transformers_gis": g.get("qty"),
            "s_rated_kva_gis": (round(g.get("s_rated_kva"), 1)
                                 if g.get("s_rated_kva") else None),
            "tr_diff": ((g.get("qty") - len(t.transformer_ids))
                         if g.get("qty") is not None else None),
            "ens_kwh": ((snap.get("ens_before_kwh") or {}).get(k)),
            "ens_after_kwh": (snap.get("ens_after_kwh") or {}).get(k),
            "loads": len(t.load_ids),
            "lambda_per_year": float(lam.get("lambda_per_year",
                                             rk.get("lambda_per_year", 0.0)) or 0),
            "lambda_reducible": float(lam.get("lambda_reducible_per_year",
                                              rk.get("lambda_reducible", 0.0)) or 0),
            "r_minutes": float(lam.get("r_minutes",
                                       rk.get("r_minutes", 0.0)) or 0),
            "u_hours": float(lam.get("u_hours", 0.0) or 0),
            "exposure_days": lam.get("exposure_days"),
            "exposure_years": lam.get("exposure_years"),
            "ep_percent": ep.get("ep_percent", rk.get("ep_percent")),
            "tl_percent": ep.get("tl_percent", rk.get("tl_percent")),
            "total_load_kw": ep.get("total_load_kw"),
            "zone_count": ep.get("zone_count"),
            "rank": rk.get("rank"),
            "score": rk.get("score"),
            "ties_count": rk.get("ties_count"),
            "scheme_kind": rec.get("scheme_kind"),
            "n_switches": rec.get("n_switches", 0),
            "switches": rec.get("switches", []),
            # نیاز ۹ — ظرفیت
            "cap_nominal_kw": cap.get("nominal_kw"),
            "cap_peak_kw": cap.get("peak_kw"),
            "cap_emergency_kw": cap.get("emergency_kw"),
            "cap_reserve_kw": cap.get("reserve_kw"),
            "cap_status": cap.get("status"),
            # نیاز ۱۰ — وضعیت طرح
            "plan_status": plan.get("status"),
            "plan_status_fa": plan.get("status_fa"),
            "plan_approved": plan.get("approved", False),
        })
    return rows


# ---------------------------------------------------------------------------
# main builder
# ---------------------------------------------------------------------------
def build_dashboard(net: CanonicalNetwork | None = None,
                    topo=None, outage=None, placement=None,
                    db_path: str = "", lambda_source: str = "",
                    capacity_rows=None, scope: str | list | tuple | set | None = None) -> dict:
    """Assemble the complete dashboard payload (JSON-safe dict)."""
    snap = placement.to_dict() if placement is not None else {}
    lam_rows = _outage_lambda_rows(outage)
    if not lam_rows:
        # fall back to the λ the ranking actually used (persisted outage
        # run or zeros) — the dashboard must never show invented numbers
        lam_rows = [{"feeder_key": r["feeder_key"],
                     "lambda_per_year": r.get("lambda_per_year", 0.0),
                     "lambda_reducible_per_year": r.get("lambda_reducible", 0.0),
                     "r_minutes": r.get("r_minutes", 0.0),
                     "u_hours": 0.0}
                    for r in snap.get("ranking") or []]

    traces_all = getattr(topo, "traces", []) or []
    if scope is None or scope == "":
        selected = None
        scope_label = "whole network"
    elif isinstance(scope, str):
        selected = {scope.strip()} if scope.strip() else None
        scope_label = scope.strip() or "whole network"
    else:
        selected = {str(k).strip() for k in scope if str(k).strip()}
        scope_label = ", ".join(sorted(selected)) or "no feeders selected"
    traces = ([t for t in traces_all if t.feeder_key in selected]
              if selected is not None else list(traces_all))
    active_keys = {t.feeder_key for t in traces}
    zones_payload = zone_rows(topo, net=net, placement=placement,
                              load_model=(snap.get("load_model") or {}))
    if selected is not None:
        zones_payload = [z for z in zones_payload if z.get("feeder_key") in active_keys]
    if selected is not None:
        lam_rows = [r for r in lam_rows if r.get("feeder_key") in active_keys]
        for key in ("table13_connections", "table14_eptl", "table15_rows",
                    "ranking", "recommendation"):
            if isinstance(snap.get(key), list):
                if key == "table13_connections":
                    snap[key] = [r for r in snap[key]
                                 if r.get("feeder_a") in active_keys
                                 and r.get("feeder_b") in active_keys]
                else:
                    snap[key] = [r for r in snap[key]
                                 if r.get("feeder_key") in active_keys]
        if isinstance(snap.get("table18_comparison"), list):
            snap["table18_comparison"] = [r for r in snap["table18_comparison"]
                if not r.get("feeders") or set(r.get("feeders") or []) <= active_keys]
        if isinstance(snap.get("schemes"), list):
            snap["schemes"] = [r for r in snap["schemes"]
                if set(r.get("feeders") or []) <= active_keys]
    cap_map = capacity_rows_map(capacity_rows)
    if selected is not None:
        cap_map = {k: v for k, v in cap_map.items() if k in active_keys}
    plan_map = plan_status_map(placement)
    if selected is not None:
        plan_map = {k: v for k, v in plan_map.items() if k in active_keys}
    gis_tr = gis_transformer_map(net)
    if selected is not None:
        gis_tr = {k: v for k, v in gis_tr.items() if k in active_keys}
    rows = feeder_rows(traces, lam_rows, snap, cap_map=cap_map,
                       plan_map=plan_map, gis_tr=gis_tr)
    zone_load_by_feeder = {}
    for zr in zones_payload:
        fk = zr.get("feeder_key")
        if fk:
            zone_load_by_feeder[fk] = zone_load_by_feeder.get(fk, 0.0) + float(zr.get("load_kw", 0.0) or 0.0)
    if placement is not None and getattr(getattr(placement, "n1", None), "trees", None):
        for row in rows:
            fk = row["feeder_key"]
            if fk in zone_load_by_feeder:
                n1_total = row.get("total_load_kw")
                zone_total = zone_load_by_feeder[fk]
                row["load_input_kw"] = round(zone_total, 2)
                row["load_delta_kw"] = (round(zone_total - float(n1_total), 2)
                                         if n1_total is not None else None)
                row["total_load_kw"] = round(zone_total, 2)
                row["load_source"] = "n1_zone_allocation"
    else:
        for row in rows:
            row["load_input_kw"] = row.get("total_load_kw")
            row["load_delta_kw"] = 0.0 if row.get("total_load_kw") is not None else None
            row["load_source"] = "table14" if row.get("total_load_kw") is not None else "unavailable"
    coverage = outage_coverage(outage)
    if selected is not None and outage is not None:
        live_records = getattr(outage, "records", None)
        if live_records is not None:
            scoped_records = [r for r in (live_records or [])
                              if getattr(r, "feeder_key", None) in selected]
            settings = getattr(outage, "settings", {}) or {}
            cov_settings = settings.get("coverage", {}) if isinstance(settings, dict) else {}
            try:
                from ..reliability.coverage import compute_coverage
                coverage = compute_coverage(
                    scoped_records,
                    start=cov_settings.get("start"),
                    end=cov_settings.get("end"),
                    force_cover=cov_settings.get("force_cover_months", ()),
                    force_exclude=cov_settings.get("force_exclude_months", ()),
                ).as_dict()
            except Exception:
                coverage = {}
        elif isinstance(outage, dict):
            # Compact persisted summaries have no per-event dates; unless
            # their saved scope exactly matches the current one, suppress
            # global coverage rather than presenting it as feeder-specific.
            saved = outage.get("settings", {}) or {}
            saved_scope = set(saved.get("scope_feeders") or
                              ([saved.get("scope_feeder")] if saved.get("scope_feeder") else []))
            if saved_scope != selected:
                coverage = {}

    s = net.summary() if net is not None else {}
    conn = topo.connectivity.summary() if topo is not None else {}
    if selected is not None and topo is not None:
        active_nodes = set().union(*(set(t.nodes) for t in traces)) if traces else set()
        conn_obj = getattr(topo, "connectivity", None)
        energized_by_feeder = getattr(conn_obj, "energized_by_feeder", {}) or {}
        conn = dict(conn)
        if energized_by_feeder:
            conn["energized_nodes"] = len(set().union(*(
                set(energized_by_feeder.get(k, set())) for k in active_keys)))
        else:
            energized = set(getattr(conn_obj, "energized_nodes", set()) or set())
            conn["energized_nodes"] = len(active_nodes & energized)
        graph_nodes = getattr(getattr(topo, "graph", None), "nodes", {})
        scoped_dead = {nid for nid in (getattr(conn_obj, "deenergized_nodes", set()) or set())
                       if nid in graph_nodes and
                       (getattr(graph_nodes[nid], "feeder_hint", "") or "").strip().upper()
                       in active_keys}
        conn["deenergized_nodes"] = len(scoped_dead)
    graph = getattr(topo, "graph", None) if topo is not None else None
    if selected is not None and graph is not None:
        used_nodes = set().union(*(set(t.nodes) for t in traces)) if traces else set()
        used_edges = set().union(*(set(t.edges) for t in traces)) if traces else set()
        switch_ids = {sid for node in used_nodes
                      for sid in graph.switch_ids_at.get(node, ())}
        s = dict(s)
        s.update({"nodes": len(used_nodes), "branches": len({
                    graph.edges[eid].branch_id for eid in used_edges
                    if eid in graph.edges}), "switches": len(switch_ids),
                  "transformers": len(set().union(*(set(t.transformer_ids) for t in traces))
                                       if traces else set()),
                  "loads": len(set().union(*(set(t.load_ids) for t in traces))
                                if traces else set())})
    issues = snap.get("issues") or []
    sev = {"Error": 0, "Warning": 0, "Information": 0}
    for i in issues:
        sev[i["severity"]] = sev.get(i["severity"], 0) + 1

    kpis = {
        "project": s.get("project", ""),
        "db_path": db_path,
        "scope": scope_label,
        "nodes": s.get("nodes", 0),
        "branches": s.get("branches", 0),
        "switches": s.get("switches", 0),
        "transformers": s.get("transformers", 0),
        "loads": s.get("loads", 0),
        "feeders": len(traces),
        "length_km": round(sum(r["km"] for r in rows), 1),
        "zones": len(zones_payload),
        "zones_with_load": sum(1 for z in zones_payload
                                if z.get("load_kw") is not None
                                and z.get("load_kw") > 0),
        "zone_total_length_m": round(sum(z.get("length_m", 0.0) for z in zones_payload), 1),
        "boundaries": (sum(1 for b in topo.zones.boundaries
                           if selected is None or any(
                               z.id in b.zones and z.feeder in active_keys
                               for z in topo.zones.zones))
                       if topo is not None else 0),
        "tie_candidates": (sum(1 for t in topo.ties
                               if selected is None or
                               (t.feeder_a in active_keys and
                                t.feeder_b in active_keys))
                           if topo is not None else 0),
        "energized_nodes": conn.get("energized_nodes", 0),
        "deenergized_nodes": conn.get("deenergized_nodes", 0),
        "total_load_kw": round(sum(r["total_load_kw"] or 0.0
                                   for r in rows), 1),
        "total_lambda": round(sum(r["lambda_per_year"] for r in rows), 2),
        "worst_feeder": next((r["feeder_key"] for r in rows
                              if r.get("rank") == 1), ""),
        "proposed_switches": sum(r["n_switches"] or 0 for r in rows),
        "selected_schemes": sum(1 for c in snap.get("table18_comparison")
                                or [] if c.get("selected")),
        "issues": sev,
        # نیاز ۱۰ — طرح‌ها بدون اجبار
        "plans_accepted": sum(1 for r in rows
                              if r.get("plan_status") == "accepted"),
        "plans_need_capacity": sum(1 for r in rows
                                   if r.get("plan_status") ==
                                   "needs_capacity_confirmation"),
        "plans_not_justified": sum(1 for r in rows
                                   if r.get("plan_status") ==
                                   "no_justification"),
        # نیاز ۹ — ظرفیت
        "capacities_known": sum(1 for c in cap_map.values()
                                if c.get("status") == "ok"),
        "capacities_missing": sum(1 for c in cap_map.values()
                                  if c.get("status") != "ok"),
    }

    return {
        "kpis": kpis,
        "feeders": rows,
        "zones": zones_payload,
        "gis_transformers": gis_tr,
        "reconciliation": reconciliation_rows(rows, gis_tr),
        "ranking": snap.get("ranking") or [],
        "economics": snap.get("table18_comparison") or [],
        "schemes": [{"kind": sc.get("kind"), "feeders": sc.get("feeders"),
                     "n_switches": len(sc.get("switches") or []),
                     "note": sc.get("note")}
                    for sc in snap.get("schemes") or []],
        "outage": summarize_outage(outage, active_keys if selected is not None else None)
                  if outage is not None else {"available": False, "lambda_r": lam_rows},
        "coverage": coverage,          # نیاز ۸ — پوشش داده/ماه‌های فاقد داده
        "lambda_source": lambda_source or ("outage data" if outage is not None
                                           else "no outage data (λ = 0)"),
        "issues": issues,
        "has_placement": placement is not None,
        "has_topology": topo is not None,
    }
