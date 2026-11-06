# PHASE1_REPORT.md — گزارش تحویل فاز ۱ (ورود داده و کنترل کیفیت)

| مورد | مقدار |
|---|---|
| پروژه | SwitchLoc — Version 1.1.0 (روش سطح اول TAV122-02/00) |
| دامنه این تحویل | فاز ۱ طبق `ARCHITECTURE.md` §۵: مدل Canonical کامل، Readerهای چندقالب، سرویس نگاشت لایه/فیلد، CRS، Snap، قطعه‌بندی، SQLite، کنترل کیفیت کامل + صحت‌سنجی PDF رسمی |
| نتیجه پذیرش | ✅ **PASS** — ورود ۱۲ لایه واقعی خلخال با ۰ خطای رده Error؛ **۲۹ آزمون سبز** |

## ۱. آنچه تحویل شد (نسبت به ARCHITECTURE.md §۵)

| قلم دامنه فاز ۱ | ماژول | شرح |
|---|---|---|
| مدل Canonical کامل | `domain/` (entities, enums, ids) | موجودیت‌های Node/Branch/BranchSegment/Switch/Transformer/Load/Feeder/TieConnection/SourceRecord + ثابت‌های رسمی (`N1_RESTORE_LIMIT_MIN`، `OUTAGE_REVIEW_LEVELS`، `OUTAGE_CLASSES`) |
| Reader چندقالب | `gis/readers/` | Shapefile (pyshp با fallbackGeoPandas)، GeoJSON، GeoPackage، Tabular (Excel/CSV) + Registry کشف خودکار |
| سرویس نگاشت لایه/فیلد | `gis/mapping/` | کاتالوگ فیلد با زنجیره fallback مستند + پیشنهاد خودکار نگاشت + اسلات‌های تجهیز + `reports/phase1_mapping.json` |
| CRS Service | `gis/crs.py` | اولویت .prj→.cpg→پیش‌فرض (مطابق رفتار مستند GeoGrid geo.py)؛ این پروژه: EPSG:32638 (UTM 38N متری) |
| Snap متری | `gis/snap.py` | اتصال تک‌پیوند با تلورانس متری قابل تنظیم (۰٫۵ متر) — جایگزین رند اعشاری GeoGrid (تصمیم GG-06) |
| قطعه‌بندی خطوط | `gis/segmentation.py` | برش خطوط در گره‌های اتصال + splice تجهیزات نقطه‌ای + عدم اتصال در تقاطع (رفتار اثبات‌شده GeoGrid، بازپیاده‌سازی مستقل) |
| مونتاژ Canonical | `gis/assemble.py` | تولید مدل نهایی از لایه‌های نگاشت‌شده + قواعد Issue |
| پریستنس | `persistence/` (schema, store) | SQLite per-project با ۱۶ جدول + `study_run` (snapshot SHA-256 همه ورودی‌ها + پارامترها → بازتولیدپذیری) |
| کنترل کیفیت کامل | `validation/qc.py` | ۷ کد Issue فعلی در سه رده Error/Warning/Information با گزارش MD/JSON |
| سرویس ورود | `application/import_service.py` + `scripts/import_sample.py` | خط لوله کامل کشف→نگاشت→خواندن→snap→قطعه‌بندی→مونتاژ→QC→SQLite |

## ۲. اجرای پذیرش (معیار ARCHITECTURE §۵ فاز ۱)

```
python scripts/import_sample.py   →   reports/phase1_import_report.md : ✅ PASS
```

| سنجه | مقدار |
|---|---|
| لایه واردشده | ۱۲ از ۱۲ (ELWABS, ELWCBR, ELWDCS, ELWDTR, ELWFCT, ELWJUP, ELWMLN, ELWOML, ELWREC, ELWMSC, ELWUML, ELWFWT) |
| nodes / branches / branch_segments | ۱۲٬۶۸۹ / ۱۲٬۴۸۴ / ۱۳٬۱۶۰ |
| switches / transformers / loads / feeders | ۷۸۸ / ۶۲۷ / ۶۲۷ / ۸ |
| source_records | ۱۳٬۹۰۷ (منشأ هر رکورد حفظ شده) |
| Issueها | **Error: ۰** — Warning: ۸۶۰ — Information: ۴۲ |
| کدهای Warning | GIS-SWITCH-STATE-UNKNOWN (۶۲۳) · GIS-DUP-LINE (۲۰۱) · GIS-FEEDER-MISSING (۴۱) · GIS-ORPHAN-DEVICE (۳۲) · GIS-TRANSFORMER-NO-CAPACITY (۳) · GIS-SLOT-DEFERRED (۱) · GIS-AMBIGUOUS-SNAP (۱) |
| تکرارپذیری | دو اجرای متوالی با نتایج منطبق؛ هش SHA-256 تک‌تک فایل‌های ورودی در `study_run` |

هیچ فایل ورودی تغییری نکرده است (الزام بند ۵ پرامپت مادر — فقط خواندن).

## ۳. صحت‌سنجی PDF رسمی TAV122-02/00 (اقلام منتظر از فاز صفر)

PDF رسمی آپلودشده (۴۸ صفحه فیزیکی = صفحات منطقی ۱-۳۵) با استخراج متن + کنترل تصویری صفحات کلیدی صحت‌سنجی شد (جزئیات: `TAV122_TRACEABILITY.md` §۶ و §۸):

| ابهام | نتیجه | اثر بر موتور |
|---|---|---|
| **A-01** (CE/CN جدول ۱۸) | متن رسمی: CE = 1000×(E2−E1) مزیت انرژی، CN هزینه خرید/جابجایی، انتخاب با **بیشینه‌سازی** CE/CN — قرائت فاز صفر (کمینه‌سازی) **باطل شد** | `formulas.ce_cn()` اصلاح و جهت انتخاب با ۲ آزمون قفل شد (این اصلاح رتبه‌بندی طرح‌های کلیدگذاری فاز ۴ را از وارونگی نجات داد) |
| **A-02** (معکوس صفر=۱۰) | عیناً تأیید شد (بند ۷-۷-۵، صفحه ۳۳) | `inverse_zero_policy` پیش‌فرض «confirmed»؛ قفل pending برای بازصحت‌سنجی آینده باقی ماند |
| **A-11** (چهار سطح خاموشی) | شکل ۵ (صفحه ۳۰) از تصویر صفحه خوانده شد: علت اشکال / نوع اشکال / زمان رخداد / محدوده | ثابت `OUTAGE_REVIEW_LEVELS` + نگاشت به شش طبقه بند ۱۰ پرامپت مادر؛ طبقه‌بند خودکار در فاز ۳ |
| وزن‌های جدول ۱۲/۱۶ | منطبق با راهنما — بدون اختلاف | `OFFICIAL_CONFIRMATIONS` |
| یافته جدید | مثال عددی فرمول (۱) صفحه ۳۳ ناسازگاری حروف‌چینی RTL دارد (ورودی/خروجی معکوس‌چاپ)؛ **قاعده دوپهلو نیست** | تست V-01 ترتیب خودسازگار را پین می‌کند؛ ثبت در §۶-مورد ۲ |

## ۴. حساب استفاده مجدد GeoGrid (هدف اصلی پرامپت مادر)

«دانش، نه کد» — هیچ فایل‌ای از GeoGrid کپی نشده؛ دانش مستندسازی‌شده آن بازاستفاده شد:

| دانش GeoGrid | محل بازاستفاده در SwitchLoc | آزمون/شاهد |
|---|---|---|
| نام لایه‌ها با پیشوند EL + نام مستعار | `field_catalog.py` (رفتار `_w_prefix_alias`) | ۱۲ لایه واقعی شناسایی شدند |
| زنجیره fallback نام فیدر `Feeder→T_FeederNa→T_feader→T_name_fdr` | `field_catalog.FEEDER_FIELDS` | GIS-FEEDER-MISSING از ۲۷۰ به ۴۱ کاهش یافت |
| رفتار `T__outserv` (مقدارهای out) | `field_catalog.map_service_state` | ۶۲۳ کلید وضعیت‌نامشخص صریح (بدون فرض پنهان) |
| اسلات‌های تجهیز (الگوی EquipmentSlot) | `mapping/slots.py` | ۷۸۸ کلید + ۶۲۷ ترانس طبقه‌بندی شدند |
| اولویت CRS .prj→.cpg | `gis/crs.py` | EPSG:32638 برای ۱۲ لایه |
| قطعه‌بندی خط + splice + عدم اتصال در تقاطع | `gis/segmentation.py` | ۱۳٬۱۶۰ segment از ۱۲٬۴۸۴ branch |
| رند اعشاری GeoGrid | **جایگزین شد** با snap متری ۰٫۵م (`gis/snap.py`) — تصمیم مصوب GG-06 | GIS-AMBIGUOUS-SNAP فقط ۱ مورد |

جزئیات ممیزی: `docs/GEOGRID_REUSE_AUDIT.md` §۱۰ و §۱۲ (برنامه آزمون GG-01..GG-10).

## ۵. موارد باز برای فاز ۲

| # | مورد | مرجع |
|---|---|---|
| ۱ | گراف توپولوژی، اتصال تجهیزات، فیدر/Tie/NO-NC و زون‌بندی (بازسازی ۸ فیدر واقعی) | ARCHITECTURE §۵ فاز ۲ |
| ۲ | UI نگاشت لایه/فیلد (PySide6) — سرویس نگاشت آماده است، پوسته گرافیکی در فاز ۲ | D-04 |
| ۳ | A-09 (تشخیص NO/Tie) با ورودی کاربر + قاعده پیشنهادی | TRACEABILITY §۵ |
| ۴ | بازصحت‌سنجی پیوست‌های ب/ج در صورت دسترسی به نسخه کامل دستورالعمل | TRACEABILITY §۶-۴ |

## ۶. معیار پذیرش خوداظهاری (قابل آزمون)

```bash
python -m pytest tests/ -q          # → 29 passed
python scripts/import_sample.py     # → reports/phase1_import_report.md : PASS (0 Error)
```
