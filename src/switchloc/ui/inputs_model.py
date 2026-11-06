# -*- coding: utf-8 -*-
"""Placement-inputs confirmation model — جدول تأیید نهایی ورودی‌ها
(درخواست کاربر: «قبل از انجام فرایند placement … جدول همه داده‌های
ورودی که در منطق محاسبات استفاده می‌شود جهت تائید نهایی به کاربر نمایش
داده شود … در صورت تغییر هر کدام محاسبات با مقادیر جدید انجام گردد»).

The pure layer builds ONE flat editable table (گروه / پارامتر / فیدر /
مقدار) from the exact objects the pipeline consumes — the λ/r matrix,
the load model, the feeder capacities, the cost model, the acceptance
criteria, the coverage window and the ranking weights — and applies the
user's edits back onto those SAME objects, so the run after «تأیید» is
guaranteed to use the confirmed numbers.

Discipline: Qt-free and deterministic (unit-tested); the dialog glue
lives in ui/qt/inputs_confirm_dialog.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field

PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
                               "01234567890123456789")


def missing_load_scaling_inputs(feeder_keys, feeder_pq) -> list[str]:
    """Feeders lacking a non-zero total P or Q input for Load Scaling."""
    data = dict(feeder_pq or {})
    missing = []
    for key in feeder_keys or []:
        row = data.get(key) or {}
        # Both total P and Q must be explicitly supplied; an omitted Q is
        # not silently treated as unity power factor.
        if "p_kw" not in row or "q_kvar" not in row:
            missing.append(str(key))
            continue
        try:
            p = float(row.get("p_kw"))
            q = float(row.get("q_kvar"))
        except (TypeError, ValueError):
            missing.append(str(key))
            continue
        if p <= 0 or q < 0:
            missing.append(str(key))
    return missing


def scoped_feeder_keys(keys, scope: str | list | tuple | set | None = None) -> list[str]:
    """Return feeders requested by a study scope.

    ``scope`` may be one feeder (legacy single-feeder API) or an explicit
    iterable of feeders (multi-feeder study).  Selection order is normalized
    deterministically so calculations and persisted reports stay reproducible.
    """
    ordered = sorted({str(k).strip() for k in (keys or []) if str(k).strip()})
    if scope:
        if isinstance(scope, str):
            wanted = {scope.strip()}
        else:
            wanted = {str(k).strip() for k in scope if str(k).strip()}
        return [k for k in ordered if k in wanted]
    return ordered


def parse_number(text) -> float | None:
    """Cell text → float (Persian/Arabic digits, commas, % tolerated);
    None when not a number."""
    if text is None:
        return None
    s = str(text).translate(PERSIAN_DIGITS).strip().replace(",", "")
    if s.endswith("%"):
        s = s[:-1].strip()
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


@dataclass
class InputRow:
    """One editable row of the confirmation table."""
    group: str                    # گروه (خاموشی/بار/ظرفیت/هزینه/…)
    param: str                    # نام پارامتر
    feeder: str = ""              # فیدر ("" = عمومی)
    value: str = ""               # مقدار (فرم متنی قابل ویرایش)
    key: tuple = ()               # کلید بازنویسی (write-back)
    editable: bool = True
    note: str = ""                # توضیح منشأ مقدار (بند ۱۹)

    def as_list(self) -> list:
        return [self.group, self.param, self.feeder, self.value]


# ---------------------------------------------------------------------------
# build the table
# ---------------------------------------------------------------------------
def collect_placement_rows(*, lam_matrix=None, capacity_rows=None,
                           load_model=None, cost_model=None,
                           criteria=None, coverage=None,
                           weights=None, engine_info=None,
                           feeder_keys=None) -> list[InputRow]:
    """All inputs the placement/manual logic will consume → InputRows.

    ``lam_matrix``: FeederLambdaR-like objects or dicts (feeder_key,
    lambda_per_year, r_minutes).  ``capacity_rows``: نیاز ۹ dicts.
    The remaining dicts mirror the engineering-settings structure.
    """
    load_model = dict(load_model or {})
    cost_model = dict(cost_model or {})
    criteria = dict(criteria or {})
    coverage = dict(coverage or {})
    rows: list[InputRow] = []

    # 1) outage λ/r per feeder (نیاز ۸ — ورودی رتبه‌بندی و ENS) -----------
    for m in (lam_matrix or []):
        d = m if isinstance(m, dict) else getattr(m, "__dict__", {})
        fk = d.get("feeder_key", "")
        lam = d.get("lambda_per_year", 0.0)
        r = d.get("r_minutes", 0.0)
        rows.append(InputRow(
            "خاموشی", "λ نرخ خرابی (فالت/سال)", str(fk),
            _num_str(lam), ("lambda", str(fk)),
            note="رخدادهای تصادفی ÷ زمان مواجهه واقعی (فاز ۳)"))
        rows.append(InputRow(
            "خاموشی", "r متوسط مدت خاموشی (دقیقه)", str(fk),
            _num_str(r), ("r", str(fk)),
            note="میانگین مدت خاموشی‌های تصادفی (صفرها واقعی‌اند)"))
        ev = d.get("events_random", None)
        exp = d.get("exposure_years", None)
        if ev is not None:
            rows.append(InputRow(
                "خاموشی", "رخداد تصادفی / مواجهه (سال)", str(fk),
                f"{ev} / {exp if exp is not None else '—'}",
                (), editable=False,
                note="منشأ λ — غیرقابل ویرایش (از فایل خاموشی)"))

    # 2) load model (نیاز ۱۱) --------------------------------------------
    pq = dict(load_model.get("feeder_pq") or {})
    feeder_set = sorted(set(feeder_keys or ()) | {r.feeder for r in rows
                         if r.key and r.key[0] == "lambda"})
    for fk in feeder_set:
        p = (pq.get(fk) or {}).get("p_kw")
        q = (pq.get(fk) or {}).get("q_kvar")
        rows.append(InputRow(
            "بار (Load Scaling)", "P بار فیدر (kW)", fk,
            _num_str(p), ("pq_p", fk),
            note="ورودی کاربر — K = S_load/ΣS_rated از این مقدار"))
        rows.append(InputRow(
            "بار (Load Scaling)", "Q بار فیدر (kVAr)", fk,
            _num_str(q), ("pq_q", fk)))
    rows.append(InputRow(
        "بار", "سطح مدل بار", "",
        str(load_model.get("level") or "scaled"), ("load_level",),
        note="exact / estimated / substitute / scaled"))
    rows.append(InputRow(
        "بار", "ضریب بار (سطح تخمینی)", "",
        _num_str(load_model.get("loading_factor", 0.7)), ("loading_factor",)))
    rows.append(InputRow(
        "بار", "ضریب جانشین (kVA≈kW)", "",
        _num_str(load_model.get("substitute_factor", 1.0)),
        ("substitute_factor",)))

    # 3) feeder capacity (نیاز ۹) ----------------------------------------
    for c in (capacity_rows or []):
        fk = str(c.get("feeder_key", ""))
        rows.append(InputRow(
            "ظرفیت فیدر", "ظرفیت نامی (kW)", fk,
            _num_str(c.get("nominal_kw")), ("cap_nominal", fk)))
        rows.append(InputRow(
            "ظرفیت فیدر", "بار پیک (kW)", fk,
            _num_str(c.get("peak_kw")), ("cap_peak", fk)))
        rows.append(InputRow(
            "ظرفیت فیدر", "ظرفیت اضطراری (kW)", fk,
            _num_str(c.get("emergency_kw")), ("cap_emergency", fk)))

    # 4) cost model (جدول ۱۸) --------------------------------------------
    for key, label in (("nc_new_rials", "هزینه کلید NC جدید (ریال)"),
                       ("no_new_rials", "هزینه کلید NO جدید (ریال)"),
                       ("automation_upgrade_rials",
                        "هزینه ارتقای اتوماسیون (ریال)"),
                       ("rial_per_kwh", "نرخ انرژی (ریال/kWh)"),
                       ("switching_minutes", "زمان مانور (دقیقه)")):
        rows.append(InputRow("هزینه", label, "",
                             _num_str(cost_model.get(key)), ("cost", key)))

    # 5) acceptance criteria (نیاز ۱۰) -----------------------------------
    for key, label in (("min_ens_reduction_kwh", "حداقل کاهش ENS (kWh/سال)"),
                       ("min_ens_reduction_percent",
                        "حداقل کاهش ENS (٪)"),
                       ("max_switches_per_scheme",
                        "بیشینه کلید هر طرح (0=بدون سقف)"),
                       ("max_budget_rials",
                        "بودجه بیشینه طرح (ریال، 0=بدون سقف)")):
        rows.append(InputRow("معیار پذیرش", label, "",
                             _num_str(criteria.get(key)), ("criteria", key)))

    # 6) coverage window (نیاز ۸) ----------------------------------------
    rows.append(InputRow("پوشش داده", "شروع (YYYY/MM)", "",
                         str(coverage.get("start") or ""), ("cov_start",),
                         note="خالی = استنتاج از داده"))
    rows.append(InputRow("پوشش داده", "پایان (YYYY/MM)", "",
                         str(coverage.get("end") or ""), ("cov_end",)))
    rows.append(InputRow("پوشش داده", "ماه‌های پوشش‌دار تحمیلی", "",
                         ", ".join(coverage.get("force_cover_months") or []),
                         ("cov_force",)))
    rows.append(InputRow("پوشش داده", "ماه‌های حذف‌شده", "",
                         ", ".join(coverage.get("force_exclude_months") or []),
                         ("cov_excl",)))

    # 7) ranking weights (جدول ۱۶) + engine info -------------------------
    w = list(weights or [])
    for i, v in enumerate(w, start=1):
        rows.append(InputRow("رتبه‌بندی", f"وزن معیار {i} (جدول ۱۶)", "",
                             _num_str(v), ("weight", i)))
    for label, value in (engine_info or []):
        rows.append(InputRow("موتور (اطلاعی)", label, "", str(value),
                             (), editable=False))

    return rows


def _num_str(v) -> str:
    if v is None:
        return ""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return f"{f:g}"


# ---------------------------------------------------------------------------
# apply the edits back onto the pipeline inputs
# ---------------------------------------------------------------------------
def apply_row_edits(rows: list[InputRow]) -> dict:
    """Edited rows → write-back bundle for the caller.

    Returns ``{"lambda_overrides": {fk: (λ, r) | {"lam": …, "r": …} dict},
    "feeder_pq": {fk: {p_kw, q_kvar}}, "load_model": {...},
    "capacity_updates": {fk: {nominal_kw, peak_kw, emergency_kw}},
    "cost_model": {...}, "criteria": {...}, "coverage": {...},
    "weights": [...]}`` — only keys the user actually touched (or that
    parse cleanly) appear; unparseable edits are silently ignored (the
    original value stays) and reported in ``ignored``.
    """
    lam: dict[str, dict] = {}
    pq: dict[str, dict] = {}
    cap: dict[str, dict] = {}
    cost: dict = {}
    crit: dict = {}
    cov: dict = {}
    weights: dict[int, float] = {}
    load: dict = {}
    ignored: list[str] = []

    for r in rows:
        if not r.editable or not r.key:
            continue
        kind, sub = r.key[0], r.key[1] if len(r.key) > 1 else None
        if kind == "lambda":
            v = parse_number(r.value)
            if v is None:
                ignored.append(f"λ {sub}")
            else:
                lam.setdefault(str(sub), {})["lambda_per_year"] = v
        elif kind == "r":
            v = parse_number(r.value)
            if v is None:
                ignored.append(f"r {sub}")
            else:
                lam.setdefault(str(sub), {})["r_minutes"] = v
        elif kind in ("pq_p", "pq_q"):
            v = parse_number(r.value)
            if v is None:
                ignored.append(f"{kind} {sub}")
            else:
                pq.setdefault(str(sub), {})[
                    "p_kw" if kind == "pq_p" else "q_kvar"] = v
        elif kind == "load_level":
            v = str(r.value).strip().lower()
            if v:
                load["level"] = v
        elif kind == "loading_factor":
            v = parse_number(r.value)
            if v is not None:
                load["loading_factor"] = v
        elif kind == "substitute_factor":
            v = parse_number(r.value)
            if v is not None:
                load["substitute_factor"] = v
        elif kind.startswith("cap_"):
            v = parse_number(r.value)
            cap.setdefault(str(sub), {})[
                {"cap_nominal": "nominal_kw", "cap_peak": "peak_kw",
                 "cap_emergency": "emergency_kw"}[kind]] = v
        elif kind == "cost":
            v = parse_number(r.value)
            if v is not None:
                cost[str(sub)] = v
        elif kind == "criteria":
            v = parse_number(r.value)
            if v is not None:
                crit[str(sub)] = v
        elif kind == "cov_start":
            cov["start"] = str(r.value).strip() or None
        elif kind == "cov_end":
            cov["end"] = str(r.value).strip() or None
        elif kind == "cov_force":
            cov["force_cover_months"] = _months(r.value)
        elif kind == "cov_excl":
            cov["force_exclude_months"] = _months(r.value)
        elif kind == "weight":
            v = parse_number(r.value)
            if v is None:
                ignored.append(f"وزن {sub}")
            else:
                weights[int(sub)] = v

    return {"lambda_overrides": {k: v for k, v in lam.items()},
            "feeder_pq": pq, "load_model": load,
            "capacity_updates": cap, "cost_model": cost,
            "criteria": crit, "coverage": cov,
            "weights": [weights[i] for i in sorted(weights)],
            "ignored": ignored}


def _months(text: str) -> list[str]:
    return [p.strip() for p in str(text or "").split(",") if p.strip()]


def apply_lambda_overrides(lam_matrix, overrides: dict) -> list:
    """λ/r matrix (objects or dicts) with per-feeder edits applied.

    ``overrides``: feeder → {"lambda_per_year": x, "r_minutes": y}
    (partial dicts allowed).  Used by BOTH the ranked placement service
    and the manual evaluation, so the confirmed table rules over both.
    """
    if not overrides or lam_matrix is None:
        return lam_matrix
    out = []
    for m in lam_matrix:
        if isinstance(m, dict):
            d = dict(m)
            fk = str(d.get("feeder_key", ""))
            for k, v in (overrides.get(fk) or {}).items():
                d[k] = v
            out.append(d)
        else:
            o = overrides.get(getattr(m, "feeder_key", ""))
            if o:
                for k, v in o.items():
                    setattr(m, k, v)
            out.append(m)
    return out
