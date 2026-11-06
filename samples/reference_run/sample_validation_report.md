# گزارش اعتبارسنجی نمونه داده واقعی — فاز صفر SwitchLoc

- پوشه ورودی: `/home/z/my-project/work/sample_shp/Export_1404_08_17_12_34_09`
- تعداد لایه‌های شناسایی‌شده: **12**
- آزمون GG-02 (عدم تغییر ورودی): رعایت شد — Reader فقط می‌خواند؛ هش سرآیند فایل‌ها در JSON ثبت است.

## آمار لایه‌ها

| لایه | نوع | تعداد | مورد انتظار | منطبق | فیلد | CRS |
|---|---|---|---|---|---|---|
| ELWABS | POINTZ | 1 | 1 | ✅ | 34 | دارد |
| ELWCBR | POINTZ | 25 | 25 | ✅ | 34 | دارد |
| ELWDCS | POINTZ | 70 | 70 | ✅ | 37 | دارد |
| ELWDTR | POINTZ | 627 | 627 | ✅ | 41 | دارد |
| ELWFCT | POINTZ | 692 | 692 | ✅ | 28 | دارد |
| ELWFWT | POINTZ | 7 | 7 | ✅ | 35 | دارد |
| ELWJUP | POLYLINEZ | 126 | 126 | ✅ | 28 | دارد |
| ELWMLN | POLYLINEZ | 111 | 111 | ✅ | 18 | دارد |
| ELWMSC | POLYLINEZ | 1 | 1 | ✅ | 30 | دارد |
| ELWOML | POLYLINEZ | 12095 | 12095 | ✅ | 31 | دارد |
| ELWREC | POINTZ | 1 | 1 | ✅ | 38 | دارد |
| ELWUML | POLYLINEZ | 151 | 151 | ✅ | 33 | دارد |

## توزیع فیدر (زنجیره fallback فیلدها)

- F1 - KHALKHAL: 1357
- F2 - KHALKHAL: 400
- F3 - KHALKHAL: 695
- F4 - HATCHTCHIN: 6282
- F5 - KHALKHAL: 4491
- F5 - KOLOOR: 1
- F6 - KHALKHAL: 13
- F7 - KHALKHAL: 627

- عوارض بدون هیچ فیلد فیدر (پس از زنجیره fallback چهارفیلدی): **41** → Issueهای `GIS-FEEDER-MISSING` (تخصیص فیدر با تصمیم کاربر)

## توزیع قابلیت کنترل از راه دور (T_ctrl_otm)

- yes: 38
- no: 8
- unknown: 13861

## وضعیت سرویس (T__outserv)

- in: 1363
- out: 4
- unknown: 12540

## خلاصه Issueها

- جمع کل: **41** (Error: 0، Warning: 0، Information: 41)
- `GIS-FEEDER-MISSING`: 41