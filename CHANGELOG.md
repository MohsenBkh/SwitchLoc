# CHANGELOG


## v1.10.2 — اصلاح مدل بازپُل (جزیره‌سازی) و رتبه‌بندی مشترک

### محاسبات n-1 / ENS / EP / TL — انتقال بار از فیدر پشتیبان
- **اصلاح بزرگ (رابطه ۸ و ۱۱ پیوست ب):** برای خطای زون/قطعهٔ i، مدل قبلی فقط «زیرمجموعهٔ پشت کلید Tie» را قابل بازپُل می‌شمرد؛ رابطه (۸) الگو می‌گوید با جداسازی عضو معیوب، **کل شاخهٔ پایین‌دست تا مرز جداسازی** از سمت پشتیبان برقدار می‌شود. مدل به «جزیره‌سازی» بازنویسی شد (`level1/transfer.py`): اعضای پایین‌دست در مؤلفه‌های همبندی از طریق گره‌های مرزیِ رسانا گروه می‌شوند؛ هر جزیره تا min(بار جزیره، Σ ظرفیت Tieهای همان جزیره) بازپُل می‌شود.
- **سازگاری زون/قطعه:** جدول ۱۵ (درخت زون) و حسابداری ENS (درخت قطعه‌های `build_seg_tree`) اکنون یک مدل واحد دارند — جداسازی در تنه با یک کلید tee یک قطعه/جزیره می‌سازد و هر دو حساب یکسان تولید می‌کنند.
- **گرهٔ مانع:** گرهٔ مرزی که هیچ تجهیز رسانایی ندارد (همه NO غیراتوماسیون یا از سرویس خارج) جزیره‌ها را جدا می‌کند؛ پل‌زدن توان از چنین نقطه‌ای طبق جدول ۱۳ پذیرفته نیست (اتوماسیون‌پذیرها با طرح بسته می‌شوند و NC/نامعلوم رسانا تلقی می‌شوند).
- **قاعدهٔ تجمیع ظرفیت:** ظرفیت هر فیدر پشتیبان فقط برای همان جزیره شمرده می‌شود؛ جمع Tieهای یک جزیره اعتبار دارد؛ بار هیچ عضو دوبار بازپُل نمی‌شود (یکتاسازی قبلی فقط برای Tieهای عمیق‌تر اعمال می‌شد و شمارش مضاعف داشت). **محدودیت ثبت‌شده (بند ۱۹):** دو Tie از یک فیدر پشتیبانِ واحد در یک جزیره جمع می‌شوند؛ سقف واقعی آن جزیره، رزرو همان فیدر است.
- خطای عضو معیوب هرگز بازپُل نمی‌شود؛ بالادست هرگز در مجموعه خروجی نیست.

- **اصلاح TL در کرنل `compute_ep_tl`:** TL اکنون بیشینهٔ مستقلِ درصد بار قابل انتقال روی همهٔ سناریوهای خطا است — هم‌خوان با docstring خود تابع و «TL = ماکزیمم درصد بار قابل انتقال» در جدول ۱۴ (TAV122_TRACEABILITY). کد قبلی restorableِ همان بدترین خطای EP را گزارش می‌کرد و برای ردیف‌های واگرا TL را کوچک‌نمایی می‌کرد. لنگر official V-02 (۷۲٪/۲۸٪) بدون تغییر می‌ماند.

### رتبه‌بندی فیدرها (جدول ۱۶)
- رتبه‌بندی مشترک (competition ranking) برای امتیازهای برابر: امتیازهای مساوی رتبهٔ یکسان می‌گیرند و رتبهٔ بعدی به تعداد هم‌راهکی‌ها جلو می‌افتد (۱، ۲، ۲، ۴) — قبل می‌توانست دو فیدر هم‌امتیاز رتبه‌های متوالی متفاوت بگیرد.

### پیام‌ها و مستندات
- پیام «ظرفیت انتقال پشتیبان نامحدود فرض شد» در `placement/service.py` با سیاست واقعی v1.9.1 (صفر + هشدار صریح) هم‌راستا شد.
- docstringهای `transfer_capacity_kw`، `_spare_map` و `ens_of_configuration` معناشناسی واقعی را می‌گویند (صفر محافظه‌کارانه؛ جزیره‌سازی) — قبلاً «بی‌نهایت/زیرمجموعه» می‌گفتند.
- مقادیر EP/TL/ENS/CE/CN طرح‌ها نسبت به v1.10.1 **تغییر می‌کند** (بازیابی واقعی‌تر)؛ خروجی‌های نمونه/مرجع ذخیره‌شده (از جمله `samples/reference_run`) که مستقیم خوانده می‌شوند استال شده‌اند؛ تولید مجدد آن‌ها به GIS نمونهٔ واقعی خلخال نیاز دارد که در این محیط موجود نیست.

### آزمون
- فایل جدید `tests/unit/test_transfer_restoration.py` (۱۰ آزمون): بازپُل سرتاسری شاخه، انشعاب‌های جانبی، سقف پشتیبان، جزیره‌سازی tee، جداسازی مانع، جزیره‌های مستقل با سقف مستقل، و ردیف‌های ENS/EP/TL برابر کرنل.
- `297 passed, 45 skipped, 0 failed`.

---

## v1.10.1 — اصلاحات بار، برچسب زون و مکان‌یابی خاموشی

- Drag اختصاصی کادرهای زون با حفظ نقطه اتصال و خط راهنما؛ انتخاب زون فقط پس از رهاکردن ماوس انجام می‌شود.
- حسابرسی بار ترانس‌های فاقد اتصال به گراف و ترانس‌های خارج از زون؛ بار خارج از زون پنهان یا بازتوزیع نمی‌شود.
- ورود ۱٬۰۰۶ سکونتگاه دارای تطبیق با اطمینان بالا از بانک بازبینی اردبیل به گازیتیر آفلاین برنامه.
- استفاده از «نام پست» به‌عنوان ورودی اصلی پیشنهاد مکان خاموشی و نمایش مختصات پیشنهادها.

## v1.10.0 — بازطراحی سه‌لایه موتور، داده و محیط Placement/Map

### ۱) موتور محاسبات و مدل داده مهندسی
- خروجی Placement اکنون علاوه بر جداول قبلی، یک `zone_register` ساخت‌یافته دارد: فیدر، شناسه و شماره زون، نوع، طول، بار تخصیص‌یافته، تعداد ترانس/بار/گره/یال. این ثبت از همان درخت strict n-1 و تخصیص بار موتور ساخته می‌شود.
- طول زون در نمایش داشبورد و گزارش برای مقدار کمتر از ۱۰۰۰ متر به متر و از ۱۰۰۰ متر به بالا به کیلومتر قالب‌بندی می‌شود؛ مقدار خام متری نیز برای ممیزی حفظ شده است.
- ظرفیت نامی پیش‌فرض در فرم مهندسی برای هر فیدر ۷۰۰۰ kW است؛ بار پیک و ظرفیت اضطراری همچنان نامشخص می‌مانند و حدس زده نمی‌شوند. منشأ مقدار پیش‌فرض از مقدار اندازه‌گیری/ورودی مهندس تفکیک شده است.
- در داشبورد پیش از اجرای مدل بار، بار زون به‌صورت «محاسبه‌نشده» نمایش داده می‌شود، نه صفر ساختگی. پس از اجرای Placement، تخصیص بار زون‌های n-1 مرجع بار فیدر داشبورد است.

### ۲) یکپارچگی داده، داشبورد و گزارش
- شناسنامه زون‌ها به داشبورد، گزارش Word/PDF و یک Sheet مستقل «زون‌ها» در Excel اضافه شد.
- جدول فیدر داشبورد منبع بار و اختلاف بار را نیز نمایش می‌دهد؛ بار کل از جمع تخصیص زون‌های همان اجرای n-1 گرفته می‌شود.
- `zone_register` و ردیف‌های جدول ۱۵ در Snapshot اجرای جایابی داخل SQLite ذخیره می‌شوند؛ نیازی به تغییر schema نیست و پروژه‌های قدیمی نیز قابل خواندن می‌مانند.
- کنترل PHASE5-CROSSCHECK تقویت شد: رتبه‌بندی، طرح‌های منتخب، بار فیدر، تعداد زون، ردیف‌های خطای زون و شناسنامه زون با اجرای ذخیره‌شده مقایسه می‌شوند. برای اجرای قدیمی فاقد شناسنامه زون، پیام صریحِ تطبیق جزئی داده می‌شود.
- توضیح مدل بار در گزارش از سطح واقعی همان اجرا خوانده می‌شود؛ متن ثابت و نادرست قبلی حذف شد.

### ۳) بازطراحی Placement و Map
- ستون ابزار Placement داخل ناحیه پیمایش‌پذیر قرار گرفت و بخش جایابی دستی به یک گروه مستقل تبدیل شد؛ جدول مختصات فضای بزرگ‌تر، ارتفاع ردیف مناسب و نتیجه قبل/بعد فضای جداگانه دارد.
- اتصال بین‌فیدری دو نقطه‌ای دو دکمه مستقل و آشکار دارد: «تعریف اتصال بین‌فیدری» و «ارزیابی اتصال بین‌فیدری». انتخاب دو ردیف کامل از دو فیدر متفاوت اعتبارسنجی می‌شود؛ داده‌های اضافی کاربر به‌صورت خودکار حذف نمی‌شوند.
- کادرهای توضیح زون روی نقشه با ماوس قابل جابه‌جایی‌اند؛ خط راهنما به نقطه مرجع زون متصل می‌ماند و موقعیت کادرها در بازترسیم‌های همان نشست حفظ می‌شود.
- کشیدن کادر زون از جابه‌جایی خود نقشه تفکیک شده است؛ کلیک روی کادر همچنان امکان انتخاب/برجسته‌سازی زون را حفظ می‌کند.

### آزمون و محدودیت اعتبارسنجی
- `281 passed, 45 skipped, 0 failed`؛ `compileall` موفق.
- ۴۵ مورد Skip به‌علت نبود PySide6، نبود پایگاه نمونه خلخال، نبود خروجی نمونه Shapefile یا نبود افزونه‌های اختیاری PDF است. بنابراین رابط واقعی Qt و EXE ویندوز در این محیط اجرا/ساخته نشده‌اند و باید با `BUILD.bat` روی Windows نهایی‌سازی شوند.
- اتصال بین‌فیدری همچنان غربالگری سطح اول TAV122 است و جایگزین پخش بار، کنترل حرارتی، افت ولتاژ، اتصال کوتاه، هماهنگی حفاظتی و طراحی مسیر فیزیکی نیست.

---

## v1.9.7 — گردش‌کار بازبینی مکانی خاموشی و محاسبه شاخص زون
- دکمه «Review outage places / zones» به تب ورود داده اضافه شد؛ پس از ورود رخدادها و اجرای توپولوژی، جدول بازبینی رخدادها در دسترس است.
- نام آبادی از متن توضیحات/تجهیز با جست‌وجوی آفلاین Gazetteer پیشنهاد می‌شود؛ پیشنهاد صرفاً راهنماست و انتساب خودکار ایجاد نمی‌کند.
- مهندس برای هر رخداد مکان و زون متاثر را جداگانه انتخاب و وضعیت «تأیید» یا «رد» را ثبت می‌کند؛ رخدادهای pending یا بدون زون وارد محاسبه نمی‌شوند.
- تصمیم‌ها در جدول `outage_event_review` پایگاه SQLite پروژه ذخیره و در بازکردن دوباره پنجره بازبینی بازیابی می‌شوند.
- پس از تأیید، با زمان مواجهه واقعی و بار زونِ مدل جاری، مدت خاموشی سالانه و U×P محاسبه و به لیبل زون نقشه منتقل می‌شود. اگر بار زون یا پوشش زمانی معتبر نباشد، شاخص همچنان نامشخص می‌ماند.
- تست‌های جدید برای پیشنهاد مکان و ذخیره/بازیابی تصمیم مهندس افزوده شد.


## v1.9.0
### رابط کاربری
- نوار ابزار با آیکون (SVG داخلی، بدون فایل تصویری)، منوهای File/Study/View/Help، ناوبری کناری، نوار وضعیت، میانبرهای صفحه‌کلید.
- تم روشن/تیره، فونت Vazirmatn، دو زبان EN/فا (RTL)، پروژه‌های اخیر، Drag & Drop پروژه.
- **کارهای سنگین در نخ پس‌زمینه** (`ui/qt/worker.py`): ورود GIS (با دیالوگ نگاشت روی نخ GUI)، خاموشی، توپولوژی، جایابی، خروجی‌ها.
### پایداری و صحت
- رفع باگ enum در `widgets.py` (`QEvent.KeyPress`, `QKeySequence.Copy/Paste` → enumهای کامل) — همان خانوادهٔ کرش‌های قبلی.
- لاگ مرکزی چرخشی (`logging_setup.py`) به‌جای فایل لاگ داخل پوشهٔ کاری؛ `excepthook` سراسری؛ حذف `except` بی‌صدا (تبدیل خطای مختصات رأس خط به Issue «GIS-VERTEX-TRANSFORM-FAILED»، ثبت ازدست‌رفتن ظرفیت فیدرها).
- نسخه‌بندی schema پروژه (`PRAGMA user_version`) + پشتیبان قبل از مهاجرت + امتناع از باز کردن پروژهٔ جدیدتر.
- CRS از داده خوانده می‌شود (حذف پیش‌فرض ثابت EPSG:32639).
- خواندن سرستون‌های خاموشی مقاوم به ی/ک و نیم‌فاصله + `outage_columns.json` + هشدار سرستون ناشناخته/گم‌شده.
- مسیر `projects/` و `reports/` نسبت به پوشهٔ قابل‌نوشتن (`SWITCHLOC_HOME`).
### بسته‌بندی
- وابستگی‌های واقعی (numpy، Pillow، python-docx) اعلام شد؛ geopandas/pandas از هسته حذف و اختیاری شد (`requirements-gpkg.txt`)؛ حدود نسخه؛ `requirements-dev.txt`؛ `pyproject.toml`؛ CI.
- `BUILD.bat` (نصب مستقیم در پایتون سیستم، بدون venv) + smoke test GUI؛ حذف فایل لاگ و خروجی‌های تولیدشده از بستهٔ سورس (`samples/reference_run/`).

## v1.8.1 / v1.8.0 (تاریخچه)
**v1.8.1 — رفع کرش جدول تأیید ورودی‌ها** — روی PySide6 سخت‌گیر، رنگ پس‌زمینه ردیف‌های اطلاعی از `Qt.GlobalColor.alternateBaseColor` (نامعتبر) به `QPalette.ColorRole.AlternateBase` تم‌محور تغییر کرد (کرش هنگام باز شدن دیالوگ تأیید ورودی‌ها)؛ همچنین باندل ویرایش‌ها فقط شامل ردیف‌های واقعاً ویرایش‌شده است (مقدار دست‌نخورده دیگر به‌عنوان override ثبت نمی‌شود). تست `test_make_required_label_uses_textformat_enum` حالا فیکسچر `app` دارد (مستقل از ترتیب اجرا). ۲۵۶ تست پاس — ۰ شکست. — v1.8.0: اصلاحات درخواستی کاربر (محور نهایی) — ۱) **Map Style**: رنگ پیش‌فرض هر فیدر در دیالوگ استایل دقیقاً همان رنگ اولیه رندرر است (کد یکسان برای همه فیدرها برطرف شد)؛ رنگ/ضخامت فیدرها و سایز/نماد/رنگ کلیدها، سورس، open point، ترانس، کلید پیشنهادی و کلید دستی همه قابل تنظیم ۲) **چند استایل نام‌گذاری‌شده** با ثبت/ذخیره با نام جدید/حذف و **ماندگاری داخل فایل پروژه** (project_kv) — پس از بستن/بازکردن پروژه همان تنظیمات برمی‌گردد ۳) رفع کرش دکمه **Engineering settings** (setTextFormat(int) → Qt.TextFormat enum — لاگ پیوست کاربر) ۴) **نام پروژه در گزارش از کاربر پرسیده** و در پروژه ذخیره می‌شود ۵) **جدول تأیید نهایی همه ورودی‌های محاسبات** قبل از هر جایابی (رنک یا دستی): λ/r هر فیدر، بار P/Q، ظرفیت‌ها، هزینه‌ها، معیارهای پذیرش، پنجره پوشش داده و وزن‌های جدول ۱۶ — قابل ویرایش، محاسبات با مقادیر تأییدشده انجام می‌شود ۶) **نتایج جایابی دستی در گزارش نهایی** (بخش ۱۰ + کاربرگ مختصات) و نمایش نقاط پیک‌شده/ارزیابی‌شده با علامت آبی روی نقشه ۷) رفع باگ «ردیف کامل وجود ندارد» در جایابی دستی (استنتاج خودکار فیدر + پُرشدن کمبوها پس از توپولوژی) ۸) نقشه دوباره کل کادر را پر می‌کند (aspect equal با adjustable datalim) ۹) پنجره اولیه ۷۵٪ صفحه ۱۰) مستند کامل منطق پالایش فایل خاموشی‌ها: `docs/OUTAGE_PIPELINE_FA.md`

## v1.9.1 — اصلاحات ضروری هسته محاسباتی روش سطح ۱
### قابلیت اطمینان و خاموشی
- λ/r فقط از رخدادهای معتبرِ درون‌دامنه (قابل کاهش، تعمیر/تعویض، هماهنگی حفاظتی) محاسبه می‌شود؛ داده ناکافی و خارج از دامنه دیگر وارد نرخ تصادفی نمی‌شوند.
- زمان مواجهه و پوشش ماهانه به‌صورت مستقل برای هر فیدر محاسبه می‌شود؛ پوشش فیدر دیگر به فیدر فاقد داده قرض داده نمی‌شود.
- میانگین مدت رخدادهای قابل کاهش با کلیدگذاری جداگانه محاسبه و در ENS ذخیره/بازیابی می‌شود؛ ENS فقط از λ و r قابل کاهش اعتبار می‌گیرد.
- کات‌اوت/فیوز سرخط به‌طور خودکار هماهنگی حفاظتی پایین‌دست فرض نمی‌شود و برای بازبینی مهندس در طبقه داده ناکافی می‌ماند.
### توپولوژی، N-1 و کنترل ظرفیت
- نرمال‌سازی نام فیدر، جداکننده‌های خط تیره و فاصله را یکسان می‌کند (مانند F4-KOSAR و F4 - KOSAR → F4).
- ظرفیت نامعلوم فیدر پشتیبان دیگر بی‌نهایت فرض نمی‌شود؛ انتقال تأییدنشده تا ورود ظرفیت معتبر، صفر منظور می‌شود.
- N-1 از تخصیص بار ترانس‌های مشتق‌شده از همان مدل بار انتخابی مطالعه استفاده می‌کند.
- وضعیت پذیرش سه‌حالته شد: PASS / CONDITIONAL / FAIL؛ هشدارها دیگر به‌صورت PASS ذخیره نمی‌شوند.
### پایگاه داده و سازگاری
- schema پروژه به v2 ارتقا یافت؛ ستون r_reducible_minutes با مهاجرت افزایشی اضافه شده و پیش از مهاجرت از فایل‌های قدیمی پشتیبان گرفته می‌شود.
- رابط کاربری و ساختار کلی v1.9.0 حفظ شده است.
### آزمون
- 239 آزمون موفق، 45 آزمون Skip؛ صفر شکست در مجموعه آزمون.


## v1.9.2 — اصلاحات گردش‌کار تک‌فیدر، نقشه و جایابی دستی
- دامنه تک‌فیدر در ورود خاموشی، جدول فایل‌های خاموشی، تنظیمات بار/ظرفیت و جدول تأیید ورودی‌ها اعمال می‌شود؛ فایل جمعی نیز پیش از طبقه‌بندی به فیدر انتخابی محدود می‌شود. توپولوژی کامل برای کشف مسیر پشتیبان حفظ می‌شود، اما نبود ظرفیت پشتیبان صریحاً به‌عنوان محدودیت گزارش می‌شود.
- رتبه‌بندی تک‌فیدر فقط با همان فیدر نرمال‌سازی می‌شود؛ خروجی دیگر وابسته به داده سایر فیدرها نیست.
- پیش‌فرض مدل بار به Load Scaling تغییر کرد؛ اجرای محاسبه تا ورود هر دو مقدار P و Q برای تمام فیدرهای دامنه متوقف می‌شود؛ بار صفر یا مقدار حدسی پنهان تولید نمی‌شود.
- نماد و لجند مستقل برای FCT، DCS، CBR، REC و SEC؛ حالت NO/OOS نیز با نشانگر مجزا مشخص است.
- تجهیزات متصل مستقیم به ترمینال ترانس توزیع از مرز زون، کاندید Tie و کاندید نصب/ارتقای کلید فیدر کنار گذاشته می‌شوند؛ در مدل و نقشه به‌عنوان تجهیز موجود حفظ می‌شوند.
- جایابی دستی: ورود مختصات UTM با انتخاب Zone 38N/39N، تبدیل به CRS پروژه، نمایش دقیق نقطه و snap جداگانه به نزدیک‌ترین گره.
- پنجره Map Style دارای دکمه maximize و ناحیه قابل پیمایش شد تا کنترل‌ها در نمایشگرهای کوچک خارج از دسترس نمانند.


## v1.9.3 — دامنه چندفیدری، نمایش زون‌ها و رفع باگ‌های رابط
- دامنه مطالعه سه‌حالته شد: کل شبکه، تک‌فیدری و چندفیدری با انتخاب چند فیدر دلخواه؛ انتخاب خالی در حالت چندفیدری دیگر به‌اشتباه به‌عنوان کل شبکه تفسیر نمی‌شود.
- داشبورد در دامنه محدود، تعداد فیدر/گره/شاخه/کلید/ترانس/بار، طول، زون، Tie، ظرفیت، رتبه‌بندی، طرح‌ها و ردیف‌های خاموشی را به فیدرهای انتخاب‌شده محدود می‌کند؛ خلاصه‌های قدیمیِ فاقد جزئیات فیدر به‌عنوان آمار کل دامنه نمایش داده نمی‌شوند.
- بار هر زون از تخصیص واقعی N-1 (ساختار تو‌در‌توی feeder → zone) به نقشه منتقل می‌شود؛ با کلیک روی لیبل زون، محدوده شبکه آن برجسته و مجموع بار وصل‌شده، تعداد ترانس/نقاط بار و طول زون نمایش داده می‌شود.
- گزینه‌های تیک‌دار نمایش/عدم نمایش مستقل هر کلید GIS در کنار نقشه حفظ و مسیر رندر از مدل محاسباتی جدا نگه داشته شد؛ خاموش‌کردن نماد کلید هیچ تغییری در توپولوژی و نتایج ندارد.
- تنظیمات نمایشی زون‌ها در Map Style شامل نمایش لیبل، رنگ و اندازه متن، زمینه و شفافیت، و رنگ/ضخامت/شفافیت محدوده انتخاب‌شده است؛ وضعیت ذخیره‌شده در پروژه به چک‌باکس نقشه همگام می‌شود و خاموش‌کردن دستی واقعاً نمایش را متوقف می‌کند.
- رفع اشکال آمار اتصال داشبورد در دامنه محدود، فیلتر خلاصه خاموشی، نمایش مقدار ناموجود در خلاصه‌های فشرده، و بار زون در صورت وجود خروجی N-1.
- آزمون‌های رگرسیون جدید برای دامنه انتخابی/خالی، خلاصه خاموشی scoped، بار زون N-1 و لیبل قابل کلیک اضافه شد.
- آزمون نهایی محیط ساخت: **۲۶۰ موفق، ۴۵ Skip، صفر شکست**. ۴۵ آزمون وابسته به GUI به علت نبود PySide6 در محیط Linux اجرا نشدند؛ `BUILD.bat` در Windows وابستگی Qt را نصب و آزمون GUI را اجرا می‌کند.

## 1.9.4 — Project lifecycle and safe exit

- Added New Project, Save, Save As, and Open Project commands with standard shortcuts.
- Save As creates an independent SQLite copy using SQLite's online backup API and switches the active project to the new path.
- New Project creates a clean project database and lets the next GIS import populate that selected file.
- Opening or creating another project prompts to save, discard, or cancel when the current project has unsaved changes.
- Closing the application prompts to save, discard, or cancel; cancel keeps the application open.
- Added dirty-state tracking for GIS import, outage analysis, topology, placement, and project map-style changes.
- Save checkpoints the SQLite WAL and clears the dirty state only after a successful operation.

## 1.9.5 — Map UI and interaction fixes

- Switch Visibility is collapsible and switch symbols are grouped in a checkable tree by device type; parent categories support bulk type selection.
- Feeder selector is checkable and supports simultaneous multi-feeder display; rendering, device filtering, zone labels, and legend honor the selected set.
- Right-click on the map opens image export (PNG/JPEG/PDF/SVG, 300 dpi for raster exports).
- Map zoom/pan limits and current view are preserved across style, visibility, and zone-label redraws; the full-extent zoom reference is retained instead of being reset to the current zoom window.
- Zone-label deactivation clears selected-zone highlighting and its information panel.
- Map navigation controls use compact icon/glyph buttons with tooltips.
- Map Style is reorganized into Feeder, Network Equipment, and Zones & Legend tabs; default dialog dimensions are reduced by 20%.
- Manual coordinate marker can be cleared independently or is synchronized with the remaining coordinate rows when a row is removed.

## 1.9.6
- Zone map labels now expose annual outage hours and U×P, explicitly marked unknown when no validated zone metric exists.
- Added auditable confirmed-event zone outage aggregation.
- Added offline SQLite gazetteer, Persian place-name normalization, CSV/GeoJSON import, boundary clipping and place-text matching.
- Added Ardabil gazetteer import utility and documented the pending authoritative settlement dataset requirement.

## 1.9.8 — Feeder selector empty-state regression
- Fixed the map feeder selector being empty before a network is loaded and when a renderer contains no feeder traces.
- Added the display-only `All feeders` empty-state row. Its `None` feeder key is ignored by filtering, so it cannot be mistaken for a real feeder ID or suppress map content.
- Regression coverage remains in `test_map_tab_has_control_strip` and `test_map_tab_feeder_combo_rebuild_keeps_selection`.


## 1.9.9 — Help-first UI, selective map layers, and manual switching recalculation
- Replaced always-visible explanatory blocks with compact per-section Help controls; full Persian guidance opens in a resizable/maximizable dialog.
- Outage review now includes the substation column, filters each event's zone choices to its known feeder, and supports maximizing the review window.
- Map feeder selection now supports a true empty selection (zero feeders shown), adds a feeder visibility checklist to Map Style, and synchronizes/persists the selection across both interfaces.
- Replaced fragile map toolbar glyphs with built-in SVG icons; normalized control widths and added a selectable zone filter that follows the selected feeder set.
- Manual placement now uses the active project's load model, cost model and feeder-capacity inputs; refuses to return ENS when λ/r, active load, line length or valid placement location is missing. A zero is no longer silently reported as a successful calculation.
- Manual NC switches are overlaid on a copied network model and ZoneBuilder rebuilds the affected feeder's after-state zones; a failed zone rebuild invalidates the result. Transformer-terminal points are refused as new sectionalizing locations.
- Added two-point manual inter-feeder tie evaluation: one selected endpoint per feeder, per-feeder zone rebuild, reserve-capacity gating for automated restoration, straight-line distance note, and dashed map overlay. No reserve data means no transfer credit; non-automated ties receive no automatic restoration credit.
- Manual tie screening remains a TAV122 Level-1 model; it does not perform load-flow, protection coordination, voltage-drop, thermal/ampacity, short-circuit, or physical route design. Those remain required before engineering approval.
- Regression suite: 274 passed, 45 skipped; Python compileall successful. PySide6 was unavailable in the build container, so GUI-dependent tests remain skipped and must be exercised by the Windows `BUILD.bat`.
