# -*- coding: utf-8 -*-
"""SectionalizerService — اجرای موتور بهینه‌سازی سکشنالایزر روی یک پروژه.

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
from dataclasses import dataclass, field as dc_field
from pathlib import Path

from .. import APP_NAME, __version__
from ..persistence.store import ProjectStore
from ..reliability.load_model import LoadModelSettings, build_node_loads
from ..reliability.sectionalizer import (SectionalizerEngine,
                                         SectionalizerSettings,
                                         SectionalizerStudy)
from ..topology.tracing import feeder_key as normalize_feeder_key
from ..validation.issues import IssueLog

#: کلید ``project_kv`` برای نتیجهٔ آخرین اجرا
KV_KEY = "sectionalizer_study"


@dataclass
class SectionalizerAppSettings:
    """تنظیمات سطح کاربر (تب «بهینه‌سازی سکشنالایزر و کاهش EENS»)."""

    user: str = "unknown"
    persist: bool = True
    #: کلیدهای موتور
    engine: SectionalizerSettings = dc_field(default_factory=SectionalizerSettings)
    #: مدل بار ورودی (همان dict ذخیره‌شده در پروژه/GUI)
    load_model: dict = dc_field(default_factory=dict)
    #: منبع λ: ``outage`` (ماتریس λ/r واقعی) یا ``configured`` (پیش‌فرض)
    failure_rate_source: str = "outage"
    #: نرخ جایگزین هر فیدر وقتی ماتریس λ/r موجود نباشد
    failure_rates: dict = dc_field(default_factory=dict)
    #: سقف ظرفیت پشتیبان هر فیدر (kW) — خالی = نامحدود (فرض کد مرجع)
    backup_kw: dict = dc_field(default_factory=dict)
    #: فیدرهای مطالعه (خالی = همهٔ فیدرهای ردیابی‌شده)
    feeder_keys: tuple = ()
    #: گزارش در این پوشه نوشته شود
    report_dir: str | None = None


@dataclass
class SectionalizerAppResult:
    study: SectionalizerStudy
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


class SectionalizerService:
    """ورودی پروژه → موتور → نتیجه + گزارش + ذخیره‌سازی."""

    def __init__(self, settings: SectionalizerAppSettings | None = None):
        self.settings = settings or SectionalizerAppSettings()

    # ------------------------------------------------------------------
    def run(self, db_path: str, *, net=None, topo=None,
            outage_lambda: dict | None = None) -> SectionalizerAppResult:
        st = self.settings
        store = ProjectStore(db_path) if net is None else None
        warnings: list[str] = []
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
            result = SectionalizerAppResult(
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
            "failure_rate_source": st.failure_rate_source,
            "failure_rates_input": dict(st.failure_rates or {}),
            "backup_kw": dict(st.backup_kw or {}),
            "feeder_keys": list(st.feeder_keys or ()),
            "load_model": dict(st.load_model or {}),
            "engine": st.engine.as_dict(),
        }

    # ------------------------------------------------------------------
    def _build_study(self, net, topo, store: ProjectStore | None,
                     outage_lambda: dict | None,
                     warnings: list) -> SectionalizerStudy:
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

        # ---- λ هر فیدر ------------------------------------------------
        rates: dict[str, float] = {}
        source = st.failure_rate_source
        outage_rates = dict(outage_lambda or {})
        if not outage_rates and store is not None:
            try:
                persisted = store.load_outages()
                for row in persisted.get("lambda_r", []):
                    key = normalize_feeder_key(row.get("feeder_key"))
                    value = row.get("lambda_per_year")
                    if key and value is not None:
                        outage_rates[key] = float(value)
            except Exception as exc:                    # noqa: BLE001
                warnings.append(f"ماتریس λ/r خاموشی خوانده نشد: {exc}")
        if source == "outage":
            rates = outage_rates
            missing = [k for k in self._feeder_keys(net, topo)
                       if k not in outage_rates]
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

        engine = SectionalizerEngine(st.engine)
        study = engine.run(
            topo.graph, topo.traces, node_load_kw, net=net,
            failure_rates=rates,
            failure_rate_source=source,
            backup_kw=dict(st.backup_kw or {}) or None,
            feeders=st.feeder_keys or None,
            zone_of_node=topo.zones.zone_of_node,
            branch_labels=_branch_labels(net))
        study.settings["failure_rates"] = {k: round(v, 6)
                                           for k, v in rates.items()}
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
