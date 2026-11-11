# -*- coding: utf-8 -*-
"""SwitchPlacementService — اجرای موتور «روش جایابی بهینهٔ کلید» روی یک پروژه.

سه روش محاسبهٔ EENS (به همین ترتیب در رابط کاربری):

1. ``directional`` — λ و r **واقعی خاموشی** + مدل شعاعی/جهت‌دار
   (فقط بار پایین‌دست قطع می‌شود).
2. ``uniform`` — λ و r **واقعی خاموشی** + مدل یکنواخت (هم‌ارز کد مرجع).
3. ``manual`` — ورودی‌های دستی (λ، r، زمان تعمیر/بازیابی و پارامترهای موتور).

در دو روش اول λ و r از ماتریس λ/r پروژه به‌صورت خودکار خوانده می‌شوند و
ورودی‌های دستی نادیده گرفته می‌شوند (با هشدار صریح).

این سرویس همان الگوی بقیهٔ سرویس‌های SwitchLoc را دارد (Import/Topology/
Outage/Placement): ورودی‌ها را از پایگاه پروژه می‌خواند، موتور را با
منشأِ صریح هر عدد اجرا می‌کند و نتیجه را در همان پروژه ذخیره می‌کند.

زنجیرهٔ داده
------------
1. شبکهٔ کانونی از آخرین ``study_run`` پروژه.
2. توپولوژی/ردیابی نرمال‌حالت — اگر در حافظه نباشد، در همین سرویس
   محاسبه می‌شود (بدون تغییر در پایگاه).
3. بار هر گره از **مدل بار** (Load Model). اگر مدل بار ورودی خالی باشد،
   سطح ``estimated`` (ظرفیت ترانس × ضریب بارگذاری) با هشدار صریح
   استفاده می‌شود؛ هیچ بار صفرِ پنهانی ساخته نمی‌شود.
4. λ هر فیدر: ترجیحاً ماتریس λ/r واقعی آخرین تحلیل خاموشی پروژه،
   وگرنه مقدار پیش‌فرض تنظیمات (با ثبت منبع).
5. موتور حریصانه → نتیجه + گزارش Markdown/JSON.

ذخیره‌سازی: خروجی کامل (JSON) در ``project_kv`` با کلید
``sectionalizer_study`` نوشته می‌شود تا با بستن/بازکردن پروژه برگردد.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field as dc_field, replace
from pathlib import Path

from .. import APP_NAME, __version__
from ..persistence.store import ProjectStore
from ..reliability.load_model import LoadModelSettings, build_node_loads
from ..reliability.switch_placement import (SWITCH_TYPE_FA,
                                            SWITCH_TYPES,
                                            SwitchPlacementEngine,
                                            SwitchPlacementSettings,
                                            SwitchPlacementStudy)
from ..topology.tracing import feeder_id as normalize_feeder_key
from ..validation.issues import IssueLog

#: کلاس‌های «خطای تصادفی» (هم‌ارز OutageRecord.is_random)
_RANDOM_CLASSES = ("قابل کاهش با کلیدگذاری", "نیازمند تعمیر یا تعویض تجهیز",
                   "ناشی از هماهنگی حفاظتی")

#: کلید ``project_kv`` برای نتیجهٔ آخرین اجرا
KV_KEY = "sectionalizer_study"

#: روش‌های محاسبهٔ EENS — ترتیب نمایش: دایرکشنال، یکنواخت، دستی
EENS_METHOD_DIRECTIONAL = "directional"
EENS_METHOD_UNIFORM = "uniform"
EENS_METHOD_MANUAL = "manual"
EENS_METHOD_ORDER = (EENS_METHOD_DIRECTIONAL, EENS_METHOD_UNIFORM,
                     EENS_METHOD_MANUAL)
#: نام قدیمی (سازگاری)
EENS_METHODS = EENS_METHOD_ORDER
EENS_METHOD_FA = {
    EENS_METHOD_DIRECTIONAL:
        "دایرکشنال (Directional) — λ و r واقعی خاموشی؛ فقط بار پایین‌دست "
        "قطعهٔ معیوب بی‌برق می‌شود",
    EENS_METHOD_UNIFORM:
        "یکنواخت (Uniform) — λ و r واقعی خاموشی؛ همهٔ بار سالم با زمان "
        "بازیابی برمی‌گردد (هم‌ارز روش مرجع)",
    EENS_METHOD_MANUAL:
        "دستی (Manual) — λ، r، زمان تعمیر و بازیابی را کاربر وارد می‌کند",
}
#: روش‌هایی که λ و r آن‌ها خودکار از خاموشی‌های واقعی می‌آید
EENS_METHOD_AUTO_RATES = (EENS_METHOD_DIRECTIONAL, EENS_METHOD_UNIFORM)


@dataclass
class SwitchPlacementAppSettings:
    """تنظیمات سطح کاربر (تب «روش جایابی بهینهٔ کلید و کاهش EENS»)."""

    user: str = "unknown"
    persist: bool = True
    #: روش محاسبهٔ EENS: directional | uniform | manual
    method: str = EENS_METHOD_UNIFORM
    #: کلیدهای موتور
    engine: SwitchPlacementSettings = dc_field(
        default_factory=SwitchPlacementSettings)
    #: مدل بار ورودی (همان dict ذخیره‌شده در پروژه/GUI)
    load_model: dict = dc_field(default_factory=dict)
    #: منبع λ: ``outage`` (ماتریس λ/r واقعی) یا ``configured`` (پیش‌فرض)
    failure_rate_source: str = "outage"
    #: نرخ جایگزین هر فیدر وقتی ماتریس λ/r موجود نباشد
    failure_rates: dict = dc_field(default_factory=dict)
    #: نرخ خطای گذرا هر فیدر (برای ریکلوزر) — خالی = محاسبه از خاموشی‌ها
    transient_rates: dict = dc_field(default_factory=dict)
    #: سقف ظرفیت پشتیبان هر فیدر (kW) — خالی = نامحدود (فرض کد مرجع)
    backup_kw: dict = dc_field(default_factory=dict)
    #: فیدرهای مطالعه (خالی = همهٔ فیدرهای ردیابی‌شده)
    feeder_keys: tuple = ()
    #: گزارش در این پوشه نوشته شود
    report_dir: str | None = None


@dataclass
class SwitchPlacementAppResult:
    study: SwitchPlacementStudy
    settings: dict
    network_summary: dict
    load_model: dict
    failure_rates: dict
    warnings: list = dc_field(default_factory=list)
    report_md: str | None = None

    @property
    def markdown(self) -> str:
        return self.study.to_markdown()

    def as_dict(self) -> dict:
        return {
            "algo_version": f"{APP_NAME} {__version__}",
            "settings": self.settings,
            "network_summary": self.network_summary,
            "load_model": self.load_model,
            "failure_rates": self.failure_rates,
            "warnings": list(self.warnings),
            "study": self.study.as_dict(),
        }


class SwitchPlacementService:
    """ورودی پروژه → موتور → نتیجه + گزارش + ذخیره‌سازی."""

    def __init__(self, settings: SwitchPlacementAppSettings | None = None):
        self.settings = settings or SwitchPlacementAppSettings()
        #: λ حل‌شدهٔ هر فیدر در آخرین اجرا (برای گزارش/بازبینی)
        self._resolved_rates: dict = {}
        self._resolved_repair_times: dict = {}

    # ------------------------------------------------------------------
    def run(self, db_path: str, *, net=None, topo=None,
            outage_lambda: dict | None = None) -> SwitchPlacementAppResult:
        st = self.settings
        warnings: list[str] = []
        # باگ v1.14: وقتی شبکه از حافظه (رابط کاربری) می‌آمد، store ساخته
        # نمی‌شد و در نتیجه ماتریس λ/r واقعیِ خاموشی هرگز خوانده نمی‌شد؛
        # موتور بی‌صدا با λ=۳۰ و r=۵۰ پیش‌فرض کار می‌کرد. اکنون store
        # مستقل از منبع شبکه باز می‌شود (فقط اگر فایل پروژه موجود باشد).
        store = None
        if db_path and Path(str(db_path)).is_file():
            try:
                store = ProjectStore(str(db_path))
            except Exception as exc:                    # noqa: BLE001
                warnings.append(f"پایگاه دادهٔ پروژه باز نشد: {exc}")
        try:
            if net is None:
                runs = store.runs()
                if not runs:
                    raise ValueError(
                        "پروژه هیچ اجرای ورودی ندارد؛ ابتدا GIS را وارد کنید.")
                net, issues = store.load_network(runs[-1]["id"])
            else:
                issues = IssueLog()
            if topo is None:
                from .topology_service import TopologyService, TopologySettings
                topo = TopologyService(TopologySettings(persist=False)).run(
                    net, issues=issues)
            study = self._build_study(net, topo, store, outage_lambda, warnings)
            if st.persist and db_path:
                ProjectStore(db_path).set_kv(
                    KV_KEY, {
                        "algo_version": f"{APP_NAME} {__version__}",
                        "settings": self._settings_snapshot(),
                        "failure_rates": study.settings.get("failure_rates", {}),
                        "markdown": study.to_markdown(),
                        "study": study.as_dict(),
                    }, user=st.user)
            result = SwitchPlacementAppResult(
                study=study, settings=self._settings_snapshot(),
                network_summary=_network_summary(net),
                load_model=dict(st.load_model or {}),
                failure_rates=dict(self._resolved_rates),
                warnings=warnings)
            if st.report_dir:
                result.report_md = self.write_report(result, st.report_dir)
            return result
        finally:
            if store is not None:
                store.close()

    # ------------------------------------------------------------------
    def _settings_snapshot(self) -> dict:
        st = self.settings
        return {
            "user": st.user,
            "method": st.method,
            "method_fa": EENS_METHOD_FA.get(st.method, st.method),
            "failure_rate_source": st.failure_rate_source,
            "failure_rates_input": dict(st.failure_rates or {}),
            "failure_rates_resolved": {k: round(v, 6) for k, v in
                                       (self._resolved_rates or {}).items()},
            "repair_times_resolved": {k: round(v, 3) for k, v in
                                      (self._resolved_repair_times or {}).items()},
            "backup_kw": dict(st.backup_kw or {}),
            "feeder_keys": list(st.feeder_keys or ()),
            "load_model": dict(st.load_model or {}),
            "engine": st.engine.as_dict(),
        }

    # ------------------------------------------------------------------
    def _build_study(self, net, topo, store: ProjectStore | None,
                     outage_lambda: dict | None,
                     warnings: list) -> SwitchPlacementStudy:
        st = self.settings

        # ---- بار هر گره از مدل بار ------------------------------------
        load_model = dict(st.load_model or {})
        level_used = load_model.get("level")
        if not level_used:
            level_used = "estimated"
            warnings.append(
                "مدل بار ورودی خالی بود؛ سطح «تخمینی» (ظرفیت ترانس × ضریب "
                "بارگذاری) با منشأ ثبت‌شده استفاده شد. برای نتیجهٔ رسمی، "
                "ورودی بار فیدرها (Load Model) را کامل کنید.")
        lm_settings = LoadModelSettings.from_dict({**load_model,
                                                   "level": level_used})
        lm = build_node_loads(topo.graph, net, lm_settings)
        node_load_kw = {k: float(v or 0.0) for k, v in lm.node_kw.items()}
        if sum(node_load_kw.values()) <= 0:
            warnings.append(
                "بار محاسبه‌شدهٔ شبکه صفر است؛ EENS صفر گزارش می‌شود.")

        # ---- روش محاسبهٔ EENS -> مدل بازیابی -----------------------------
        method = st.method if st.method in EENS_METHOD_ORDER else EENS_METHOD_UNIFORM
        auto_rates = method in EENS_METHOD_AUTO_RATES
        # کپی — تنظیمات موتورِ فراخوان نباید تغییر کند (باگ v1.12)
        engine_settings = replace(st.engine)
        if method == EENS_METHOD_DIRECTIONAL:
            engine_settings.restoration_model = "directional"
        elif method == EENS_METHOD_UNIFORM:
            engine_settings.restoration_model = "uniform"
        if auto_rates and st.failure_rates:
            warnings.append(
                "در روش «" + EENS_METHOD_FA[method].split(" — ")[0] +
                "» مقادیر λ و r خودکار از خاموشی‌های واقعی خوانده می‌شوند؛ "
                "λ دستیِ فیدرهایی که صریحاً وارد شده‌اند بر مقدار خودکار "
                "اولویت دارد (قابل ردیابی در settings.failure_rates).")

        # ---- λ هر فیدر ------------------------------------------------
        rates: dict[str, float] = {}
        r_by_feeder: dict[str, float] = {}
        source = "outage" if auto_rates else st.failure_rate_source
        outage_rates = dict(outage_lambda or {})
        persisted: dict = {}
        if store is not None:
            try:
                persisted = store.load_outages()
            except Exception as exc:                    # noqa: BLE001
                warnings.append(f"دادهٔ خاموشی پروژه خوانده نشد: {exc}")
        if not outage_rates:
            for row in (persisted.get("lambda_r") or []):
                key = normalize_feeder_key(row.get("feeder_key"))
                # ردیف λ که هیچ مواجهه/رخدادی ندارد یعنی «داده نداریم»، نه
                # «λ=۰»؛ وگرنه فیدر بدون فایل خاموشی بی‌صدا EENS صفر می‌گرفت.
                has_evidence = bool(row.get("events_random")) or float(
                    row.get("exposure_years") or 0.0) > 0.0
                value = row.get("lambda_per_year")
                if key and value is not None and has_evidence:
                    outage_rates[key] = float(value)
                r_val = row.get("r_minutes")
                if key and r_val is not None and float(r_val) > 0 \
                        and has_evidence:
                    r_by_feeder[key] = float(r_val)
        def _scoped_keys() -> list:
            all_keys = self._feeder_keys(net, topo)
            wanted = [str(k) for k in (st.feeder_keys or ())]
            if not wanted:
                return all_keys
            from ..topology.tracing import same_feeder
            return [k for k in all_keys
                    if any(same_feeder(k, w) for w in wanted)]

        if source == "outage":
            rates = dict(outage_rates)
            missing = [k for k in _scoped_keys() if k not in outage_rates]
            if missing:
                warnings.append(
                    "برای فیدر(های) " + ", ".join(missing) +
                    " ماتریس λ/r واقعی موجود نیست؛ λ پیش‌فرض تنظیمات "
                    f"({st.engine.total_failure_rate_per_year:g} خرابی/سال) "
                    "با منبع «configured-default» ثبت شد.")
            if not outage_rates:
                warnings.append(
                    "هیچ ماتریس λ/r واقعی در پروژه ذخیره نشده است؛ همهٔ "
                    "فیدرها با λ پیش‌فرض محاسبه شدند.")
        else:
            rates = {}
        # ورودی صریح کاربر بر همه‌چیز اولویت دارد (قابل ردیابی)
        for key, value in dict(st.failure_rates or {}).items():
            norm = normalize_feeder_key(key) or str(key).strip().upper()
            if norm and value is not None:
                rates[norm] = float(value)
        self._resolved_rates = dict(rates)
        self._resolved_repair_times = dict(r_by_feeder)

        # ---- نرخ خطای گذرا (فقط ریکلوزر) -------------------------------
        transient_rates: dict[str, float] = dict(st.transient_rates or {})
        if engine_settings.uses_transient_faults and not transient_rates:
            # λ مؤثرِ هر فیدر: ماتریس واقعی (روش‌های خودکار) یا λ دستی
            # تنظیمات (روش دستی). پیش‌تر در روش دستی مقدار صفر می‌شد و
            # EENS گذرای ریکلوزر بی‌صدا حذف می‌شد (باگ v1.12).
            effective_rates = dict(rates)
            if not effective_rates:
                default_lambda = float(
                    engine_settings.total_failure_rate_per_year)
                effective_rates = {k: default_lambda
                                   for k in self._feeder_keys(net, topo)}
            tmax = float(engine_settings.transient_max_duration_min)
            counts: dict[str, list] = {}
            for ev in (persisted.get("events") or []):
                try:
                    dur = float(ev.get("duration_min"))
                except (TypeError, ValueError):
                    continue
                if str(ev.get("outage_class") or "") not in _RANDOM_CLASSES:
                    continue
                key = normalize_feeder_key(ev.get("feeder_key"))
                if not key:
                    continue
                slot = counts.setdefault(key, [0, 0])
                slot[1] += 1
                if dur <= tmax:
                    slot[0] += 1
            for key, (n_tr, n_all) in counts.items():
                if n_all > 0 and key in effective_rates:
                    transient_rates[key] = (effective_rates[key]
                                            * (n_tr / n_all))
            if not counts:
                warnings.append(
                    "رخداد خاموشی با مدت معتبر برای تفکیک خطای گذرا/دائمی "
                    "پیدا نشد؛ سهم گذرا صفر فرض شد.")
            elif not transient_rates:
                warnings.append(
                    "سهم خطای گذرا برای هیچ فیدری قابل محاسبه نشد "
                    "(λ مؤثر یا دادهٔ مدت موجود نبود)؛ EENS گذرا صفر شد.")

        repair_times = dict(r_by_feeder) if auto_rates else {}
        if auto_rates:
            missing_r = [k for k in _scoped_keys() if k not in repair_times]
            if missing_r:
                warnings.append(
                    "برای فیدر(های) " + ", ".join(missing_r) +
                    " مقدار r واقعی موجود نیست؛ زمان تعمیر تنظیمات "
                    f"({engine_settings.repair_time_min:g} دقیقه) استفاده شد.")

        engine = SwitchPlacementEngine(engine_settings)
        study = engine.run(
            topo.graph, topo.traces, node_load_kw, net=net,
            failure_rates=rates,
            transient_rates=transient_rates,
            repair_times=repair_times,
            failure_rate_source=source,
            backup_kw=dict(st.backup_kw or {}) or None,
            feeders=st.feeder_keys or None,
            zone_of_node=topo.zones.zone_of_node,
            branch_labels=_branch_labels(net))
        # فیدرهایی که کاندید دارند ولی هیچ کلیدی پیشنهاد نشد — دلیل را
        # صریح بگویید تا کاربر آن را باگ تلقی نکند.
        for feeder in study.feeders or []:
            if not (feeder.candidates or []):
                continue
            if feeder.best is not None and feeder.best.selected:
                continue
            notes = " ".join(feeder.notes or [])
            if "زمان بازیابی بار سالم" in notes:
                why = ("زمان بازیابی بار سالم از زمان تعمیر کمتر نیست؛ "
                       "جداسازی خطا سودی در EENS ندارد")
            elif "بهبود محسوسی" in notes or "بهبود قابل" in notes:
                why = "بهبود EENS زیر آستانهٔ معنادار بود"
            else:
                why = "همهٔ کاندیدها با فیلترهای عمق/سهم بار/کلید موجود حذف شدند"
            warnings.append(
                f"{feeder.feeder_key}: هیچ کلید پیشنهادی ندارد — {why}.")

        study.settings["failure_rates"] = {k: round(v, 6)
                                           for k, v in rates.items()}
        study.settings["method"] = method
        study.settings["method_fa"] = EENS_METHOD_FA[method]
        study.settings["switch_type"] = engine_settings.switch_type
        study.settings["switch_type_fa"] = SWITCH_TYPE_FA[engine_settings.switch_type]
        study.settings["repair_time_by_feeder"] = {
            k: round(v, 3) for k, v in repair_times.items()}
        study.settings["transient_rates"] = {
            k: round(v, 6) for k, v in transient_rates.items()}
        all_keys = self._feeder_keys(net, topo)
        studied = [f.feeder_key for f in (study.feeders or [])]
        if not studied:
            scope = "none"
        elif len(studied) <= 1:
            scope = "single"
        elif set(studied) >= set(all_keys):
            scope = "all"
        else:
            scope = "multi"
        study.settings["study_scope"] = scope
        study.settings["studied_feeders"] = list(studied)
        study.settings["all_feeders"] = list(all_keys)
        study.settings["load_model_level"] = level_used
        study.settings["load_model_total_kw"] = round(
            sum(node_load_kw.values()), 3)
        if lm_settings.level != level_used:              # pragma: no cover
            warnings.append("سطح مدل بار بازنویسی شد.")
        if not study.feeders:
            warnings.append("هیچ فیدری برای بهینه‌سازی انتخاب نشد.")
        study.notes.extend(warnings)
        return study

    @staticmethod
    def _feeder_keys(net, topo) -> list:
        return sorted({normalize_feeder_key(t.feeder_key) for t in topo.traces
                       if t.feeder_key})

    # ------------------------------------------------------------------
    def write_report(self, res: SectionalizerAppResult, report_dir: str) -> str:
        rd = Path(report_dir)
        rd.mkdir(parents=True, exist_ok=True)
        md_path = rd / "sectionalizer_eens_report.md"
        md_path.write_text(res.markdown, encoding="utf-8")
        (rd / "sectionalizer_eens_report.json").write_text(
            json.dumps(res.as_dict(), ensure_ascii=False, indent=2,
                       default=str), encoding="utf-8")
        return str(md_path)


# ---------------------------------------------------------------------------
def _network_summary(net) -> dict:
    try:
        return net.summary()
    except Exception:                                   # noqa: BLE001
        return {}


def _branch_labels(net) -> dict:
    """branch_id → برچسب GIS (اگر منشأ رکورد موجود باشد)."""
    out: dict[str, str] = {}
    for br in getattr(net, "branches", None) or []:
        src = getattr(br, "source", None)
        if src is None:
            continue
        ref = str(getattr(src, "record_ref", "") or "").strip()
        if ref:
            out[str(br.id)] = f"{ref} ({getattr(src, 'layer', '')})"
    return out


def load_persisted_study(db_path: str) -> dict | None:
    """نتیجهٔ ذخیره‌شده در ``project_kv`` را برمی‌گرداند (یا None)."""
    store = ProjectStore(db_path)
    try:
        return store.get_kv(KV_KEY)
    finally:
        store.close()


def clear_persisted_study(db_path: str) -> None:
    """Remove only the saved EENS study; leave inputs and other runs intact."""
    store = ProjectStore(db_path)
    try:
        store.delete_kv(KV_KEY)
    finally:
        store.close()


# ---------------------------------------------------------------------------
# نام‌های قدیمی (سازگاری)
# ---------------------------------------------------------------------------
SectionalizerAppSettings = SwitchPlacementAppSettings
SectionalizerAppResult = SwitchPlacementAppResult
SectionalizerService = SwitchPlacementService
