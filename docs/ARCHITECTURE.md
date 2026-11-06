# ARCHITECTURE.md — معماری SwitchLoc (خروجی طراحی فاز صفر)

| مورد | مقدار |
|---|---|
| سند | طراحی معماری لایه‌ای، مرزهای استفاده مجدد GeoGrid، رابط GIS Adapter، موتور اعتبارسنجی و بازتولیدپذیری |
| مرجع | پرامپت مادر بندهای ۴، ۵، ۶، ۱۹، ۲۰ + `GEOGRID_REUSE_AUDIT.md` |
| وضعیت | پیش‌نویس تأییدی برای شروع فاز ۱ (طبق بند ۲۴: «پس از تأیید معماری، توسعه فاز اول آغاز شود») |

## ۱. اصل معماری

```
                    ┌────────────────────────────────────────────┐
                    │                  ui/ (PySide6)             │
                    │      Wizard مرحله‌به‌مرحله + نقشه + گزارش    │
                    └───────────────▲────────────────────────────┘
                                    │ فقط از طریق application/
┌──────────────┐   ┌───────────────┴────────────────────────────┐
│  فایل‌های GIS │──▶│              application/ (Services)       │
│  Excel/CSV   │   │  ImportService · TopologyService ·         │
│  DGS (اختیار)│   │  OutageService · StudyService · ReportSvc  │
└──────▲───────┘   └───────▲───────────────────────▲────────────┘
       │                   │                       │
┌──────┴───────┐   ┌───────┴────────┐   ┌──────────┴───────────┐
│   gis/       │   │   topology/    │   │  level1/ · placement │
│ GisReader    │   │  Graph Engine  │   │  scenarios/ · relia/ │
│ (Interface)  │   │ (Canonical →   │   │  (محاسبات TAV122)     │
│  ├─shp       │   │  NetworkGraph) │   └──────────▲───────────┘
│  ├─gpkg      │   └───────▲────────┘              │
│  ├─geojson   │           │                       │
│  ├─excel/csv │   ┌───────┴────────────────────────┴───────┐
│  └─dgs       │   │  domain/ (مدل Canonical + قواعد مهندسی) │
└──────────────┘   └───────▲────────────────────────────────┘
                           │
        ┌──────────────────┴───────────────────────┐
        │ persistence/ (SQLite + Snapshot + هش‌ها)  │
        └──────────────────▲───────────────────────┘
                           │
        ┌──────────────────┴───────────────────────┐
        │ integrations/geogrid (مرز Adapter، اختیاری)│
        │  · field_catalog (منشأ: config.json 4.2.0)│
        │  · dgs_export (فقط خروجی اختیاری، فاز ۵)   │
        └───────────────────────────────────────────┘
```

**قواعد انضباطی (قابل ممیزی):**
1. منطق مهندسی فقط در `domain/`, `topology/`, `level1/`, `placement/`, `scenarios/`, `reliability/`, `validation/` — هرگز در `ui/` (بند ۴-۱).
2. هر داده‌ای که وارد می‌شود، `SourceRecord` دارد (فایل، لایه، رکورد، فیلد) و تا گزارش نهایی ردیابی‌پذیر است.
3. مرز GeoGrid فقط دو چیز است: (الف) **دانش نگاشت** (کاتالوگ فیلد/لایه مستندشده در ممیزی — به‌صورت داده، نه کد کپی‌شده)؛ (ب) خروجی اختیاری DGS در فاز ۵. هیچ import مستقیمی از `shp2dgs` در SwitchLoc وجود ندارد و هرگز مجوز GeoGrid لمس نمی‌شود.
4. SwitchLoc بدون PowerFactory و بدون DGS کامل اجرا می‌شود (بند ۵-۶).

## ۲. رابط GIS Adapter (قرارداد رسمی — پیاده‌سازی فاز ۱)

```python
class GisReader(Protocol):
    """هر قالب ورودی باید خود را به این قرارداد برساند."""
    def discover(self, source: Path) -> list[LayerInfo]:
        """فهرست لایه‌ها: نام، نوع هندسه، تعداد عوارض، CRS، فیلدها، نمونه رکورد."""
    def read(self, layer: LayerInfo, mapping: LayerMapping) -> RawLayerData:
        """خواندن عوارض + هندسه به CRS تحلیلی + SourceRecord برای هر رکورد."""

class LayerMappingService:
    """پیشنهاد خودکار نگاشت لایه/فیلد → تأیید کاربر → ذخیره در پروژه."""
    def suggest(self, layers: list[LayerInfo]) -> list[MappingSuggestion]: ...
    def confirm(self, mapping: list[LayerMapping]) -> None: ...   # هیچ نگاشت خودکاری قطعی نیست

class CrsService:
    """شناسایی CRS هر لایه (.prj/EPSG)، تبدیل یک‌باره به CRS تحلیلی متری،
    نگهداری CRS اصلی، جلوگیری از تبدیل تکراری، اعتبارسنجی محدوده مختصات."""
    def resolve(self, layer: LayerInfo) -> CRSDefinition: ...
    def to_analysis_crs(self, data: RawLayerData) -> TransformedData: ...

class CanonicalAssembler:
    """RawLayerData → موجودیت‌های domain/ با اعمال تلورانس متری و ثبت Issue."""

class GeoGridDgsExporter:   # فاز ۵ — اختیاری، پشت Adapter
    def export(self, model: CanonicalNetwork) -> Path: ...
```

**تصمیم‌های کلیدی مصوب در فاز صفر (با استناد به ممیزی):**
- **Snap متری قابل تنظیم** (پیش‌فرض ۰٫۵ متر، از config) به‌جای `round(x,3)`؛ مختصات اصلی و snap‌شده جداگانه؛ اتصال مبهم (۲+ کاندید در تلورانس) → Issue با فهرست کاندیدها و نمایش برای تأیید مهندس.
- **قطعه‌بندی خطوط چندرأسی** با توزیع طول ثبت‌شده به‌تناسب فاصله رأس‌ها (منشأ: رفتار GeoGrid 4.2.0، پیاده‌سازی مستقل + آزمون GG-03).
- **عدم اتصال در تقاطع هندسی**؛ اتصال فقط سر-به-سر یا از طریق تجهیز نقطه‌ای.
- خطوط بدون طول/هندسه نامعتبر حذف نمی‌شوند؛ `Issue` می‌گیرند و از محاسبات کنار گذاشته می‌شوند با ثبت دلیل.

## ۳. موتور اعتبارسنجی (بند ۱۹)

سه سطح: `Error` (محاسبه معتبر نمی‌شود) / `Warning` (نتیجه مقید است) / `Information` (ثبت فرض). هر Issue دقیقاً این فیلدها را دارد (الزام ۵-۷):

`id, severity, code, message_fa, source_file, layer, record_id, field, current_value, suggestion, impact, status`

کدهای اولیه (از شواهد داده واقعی): `GIS-EMPTY-ID`, `GIS-DUP-ID`, `GIS-NULL-GEOM`, `GIS-INVALID-GEOM`, `GIS-NO-CRS`, `GIS-CRS-MIXED`, `GIS-COORD-OUT-OF-RANGE`, `GIS-ZERO-LENGTH`, `GIS-ORPHAN-DEVICE` (تجهیز دور از شبکه)، `GIS-XING-NO-CONNECT`، `GIS-DUP-LINE`، `GIS-FEEDER-NAME-CONFLICT`، `GIS-SWITCH-STATE-UNKNOWN`، `DATA-OUTAGE-MISSING-COL`، `DATA-OUTAGE-EMPTY-ROW`، `DATA-UNIT-UNCONFIRMED`، `CALC-POLICY-PENDING` (مثلاً inverse_zero).

## ۴. Snapshot و بازتولیدپذیری (بند ۱۹)

هر اجرای مطالعه یک `StudyRun` می‌سازد: هش SHA-256 همه فایل‌های ورودی، نگاشت لایه/فیلد نهایی، تنظیمات (شامل پارامترهای سیاستی مثل inverse_zero و وزن‌ها)، نسخه الگوریتم، نسخه مرجع دستورالعمل (TAV122-02/00)، زمان، کاربر، نتایج میانی/نهایی و Issueها. اجرای مجدد با ورودی و تنظیمات یکسان باید خروجی بایت‌به‌بایت معادل بدهد (تست Regression).

## ۵. نگاشت فازها به ماژول‌ها (بند ۲۲ پرامپت مادر)

| فاز | محتوا | ماژول‌ها | خروجی قابل قبول |
|---|---|---|---|
| ۰ (این تحویل) | ممیزی، Traceability، ابهامات، معماری، نمونه داده، آزمون‌های اولیه | docs/ + gis/reader پروتوتایپ + level1/formulas | همین سند + گزارش اعتبارسنجی + تست‌های سبز |
| ۱ | Canonical model کامل، Readerها (SHP/GPKG/GeoJSON/Excel/CSV)، نگاشت لایه/فیلد UI، CRS، SQLite، QC کامل | domain, gis, persistence, validation | ورود ۱۲ لایه خلخال با ۰ خطای رده Error حل‌نشده |
| ۲ | گراف، اتصال تجهیزات، فیدر/Tie/NO-NC، نمایش | topology, scenarios(پایه), ui | بازسازی ۷ فیدر + زون‌بندی |
| ۳ | بار/اولویت، خاموشی، مخابرات، شاخص‌ها | reliability, application | ماتریس‌های بار، λ/r فیدرها |
| ۴ | EP/TL، رتبه‌بندی، طرح‌ها، جایابی، مقایسه | level1, placement, scenarios | جدول‌های ۱۳-۱۸ + لنگرهای عددی V-01..V-05 |
| ۵ | گزارش Word/PDF/Excel، GeoPackage/Shapefile، نقشه، DGS اختیاری | reporting, gis.exporters, integrations | خروجی‌های بند ۳-۳ |
| ۶ | آزمون کامل، شبکه بزرگ، آفلاین، PyInstaller، راهنمای کاربر | tests, packaging | معیارهای پذیرش بند ۲۳ |

> **وضعیت اجرا:** فازهای ۰، ۱، ۲، ۳ و ۴ تکمیل و پذیرش‌شده (گزارش‌ها در `PHASE0/1/2/3/4_REPORT.md`)؛ ورودی‌های فاز ۴ (ماتریس λ/r فیدرها + اولویت جدول ۱۲ + Tieهای تأییدپذیر) از خروجی فازهای ۲-۳ تأمین شد و گام‌های ۴-۸ روش سطح اول (جداول ۱۳-۱۸ + قاعده طلایی U×P) در `level1/n_minus_1.py`, `level1/ranking.py` و `placement/` پیاده شد. فایل‌های BAT یک‌کلیکی (`RUN.bat`/`BUILD.bat`) و نقاط ورود PyInstaller در `build_tools/` نیز افزوده شدند. باقی‌مانده: فاز ۵ (گزارش Word/PDF/Excel + خروجی GIS) و تکمیل آزمون‌های فاز ۶.

## ۶. تصمیم‌های باز (برای تأیید کاربر پیش از فاز ۱)

| # | موضوع | پیشنهاد پیش‌فرض |
|---|---|---|
| D-01 | CRS تحلیلی | همان CRS متری ورودی هر پروژه (اینجا UTM 38N) با قید «متر»؛ تبدیل جغرافیایی فقط برای خروجی/نمایش |
| D-02 | کتابخانه GIS | pyshp سبک برای SHP + GeoPandas/GDAL برای سایر قالب‌ها (آزمون عملکرد در فاز ۱) |
| D-03 | ذخیره پروژه | یک فایل SQLite per-project + پوشه snapshot |
| D-04 | نقشه داخلی | فاز ۱: رسم Matplotlib/PyQtGraph روی بستر Qt؛ فاز ۵: ارتقاء به WebEngine/QGIS در صورت نیاز |
| D-05 | نسخه Python | 3.11 یا 3.12 (تثبیت در فاز ۱ با PyInstaller) |
