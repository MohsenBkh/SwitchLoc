# گزارش توپولوژی فاز ۲ — گراف، فیدرها، Tie و زون‌بندی

| مورد | مقدار |
|---|---|
| پروژه | topology |
| اجرای مبنای ورود داده | `daf69273-b0b…` |
| اجرای توپولوژی | `e2ff1e57-65d…` |
| نتیجه پذیرش | ✅ PASS — هیچ Issue از رده Error حل‌نشده وجود ندارد؛ مدل canonical وارد فاز توپولوژی می‌شود. |

## ۱. گراف و اتصال تجهیزات

| سنجه | مقدار |
|---|---|
| گره‌های گراف | 12,689 |
| یال‌ها (شاخه‌های برش‌خورده در رأس تجهیزات) | 12,671 |
| شاخه‌های واردشده | 12,044 (حذف‌شده excluded: 0) |
| رأس‌های ادغام‌شده (snap همسایه) | 489 |
| کلید/ترانس/بار متصل | 788 / 627 / 627 |
| منابع متصل (ELWFWT) | 7 |

## ۲. بازسازی فیدرها (وضعیت عادی، TOPO-POL-01/02)

| فیدر | نام کامل GIS | گره | یال | طول (km) | ترانس | گره کلیددار | هم‌پوشانی |
|---|---|---|---|---|---|---|---|
| F1 | F1 - KHALKHAL | 1,195 | 1,196 | 59.86 | 69 | 84 | 0 |
| F2 | F2 - KHALKHAL | 10,421 | 10,440 | 528.24 | 492 | 653 | 52100 |
| F3 | F3 - KHALKHAL | 10,421 | 10,440 | 528.24 | 492 | 653 | 52100 |
| F4 | F4 - HATCHTCHIN | 10,421 | 10,440 | 528.24 | 492 | 653 | 52100 |
| F5 | F5 - KHALKHAL | 10,421 | 10,440 | 528.24 | 492 | 653 | 52100 |
| F6 | F6 - KHALKHAL | 10,421 | 10,440 | 528.24 | 492 | 653 | 52100 |
| F7 | F7 - KHALKHAL | 10,421 | 10,440 | 528.24 | 492 | 653 | 52100 |

### ۲-۱. هسته قطعی فیدرها (سنجه کمکی A-09 — کلیدهای با وضعیت نامشخص = باز)

| فیدر | گره هسته | طول (km) |
|---|---|---|
| F1 | 80 | 2.91 |
| F2 | 229 | 6.24 |
| F3 | 451 | 15.02 |
| F4 | 1,124 | 55.67 |
| F5 | 884 | 27.79 |
| F6 | 17 | 0.94 |
| F7 | 451 | 15.02 |

> تا زمانی که نقاط NO واقعی (A-09) تأیید نشده‌اند، ردیابی عادی با عبور از
> کلیدهای نامشخص، ورود فیدرها به قلمرو یکدیگر را نشان می‌دهد (بند ۲).
> جدول بالا «هسته بدون ابهام» هر فیدر است و مبنای خوبی برای تصمیم مهندس.

## ۳. زون‌بندی (تعریف ۵-۲۱ — محدود به کلیدها)

{
  "zone_count": 513,
  "zones_per_feeder": {
    "(island)": 1,
    "F1": 8,
    "F2": 84,
    "F3": 84,
    "F4": 84,
    "F5": 84,
    "F6": 84,
    "F7": 84
  },
  "boundary_switches": 97,
  "open_boundaries": 1,
  "branchy_boundaries": 10
}

| فیدر | شماره زون | نوع | گره | یال | طول (km) | ترانس |
|---|---|---|---|---|---|---|
| (جزیره) | 0 | island | 1,035 | 1,035 | 79.24 | 34 |
| F1 | 0 | head | 1,133 | 1,133 | 57.19 | 64 |
| F1 | 1 | section | 2 | 1 | 0.00 | 0 |
| F1 | 2 | section | 6 | 5 | 0.01 | 0 |
| F1 | 3 | section | 2 | 1 | 0.00 | 0 |
| F1 | 4 | section | 13 | 12 | 0.07 | 0 |
| F1 | 5 | section | 42 | 42 | 2.57 | 4 |
| F1 | 6 | section | 2 | 1 | 0.00 | 0 |
| F1 | 7 | section | 2 | 1 | 0.00 | 1 |
| F2 | 0 | head | 128 | 127 | 3.37 | 5 |
| F2 | 1 | section | 109 | 109 | 2.96 | 5 |
| F2 | 2 | section | 6 | 5 | 0.01 | 0 |
| F2 | 3 | section | 6 | 5 | 0.01 | 0 |
| F2 | 4 | section | 4 | 3 | 0.00 | 0 |
| F2 | 5 | section | 4 | 3 | 0.00 | 0 |
| F2 | 6 | section | 5 | 4 | 0.01 | 0 |
| F2 | 7 | section | 5 | 4 | 0.01 | 0 |
| F2 | 8 | section | 2 | 1 | 0.00 | 0 |
| F2 | 9 | section | 2 | 1 | 0.00 | 0 |
| F2 | 10 | section | 17 | 16 | 0.58 | 0 |
| F2 | 11 | section | 2 | 1 | 0.00 | 0 |
| F2 | 12 | section | 3 | 2 | 0.00 | 0 |
| F2 | 13 | section | 2 | 1 | 0.00 | 0 |
| F2 | 14 | section | 2,033 | 2,035 | 102.64 | 85 |
| F2 | 15 | section | 2 | 1 | 0.00 | 1 |
| F2 | 16 | section | 2 | 1 | 0.00 | 0 |
| F2 | 17 | section | 2 | 1 | 0.00 | 1 |
| F2 | 18 | section | 12 | 11 | 0.29 | 0 |
| F2 | 19 | section | 7 | 6 | 0.01 | 0 |
| F2 | 20 | section | 2 | 1 | 0.00 | 1 |
| F2 | 21 | section | 2 | 1 | 0.00 | 1 |
| F2 | 22 | section | 5 | 4 | 0.00 | 0 |
| F2 | 23 | section | 6 | 5 | 0.01 | 0 |
| F2 | 24 | section | 2 | 1 | 0.00 | 0 |
| F2 | 25 | section | 4 | 3 | 0.00 | 0 |
| F2 | 26 | section | 3 | 2 | 0.00 | 0 |
| F2 | 27 | section | 2 | 1 | 0.00 | 1 |
| F2 | 28 | section | 6 | 5 | 0.01 | 0 |
| F2 | 29 | section | 14 | 13 | 0.61 | 0 |
| F2 | 30 | section | 2 | 1 | 0.00 | 0 |
| F2 | 31 | section | 2 | 1 | 0.00 | 1 |
| F2 | 32 | section | 2 | 1 | 0.00 | 0 |
| F2 | 33 | section | 13 | 12 | 0.47 | 0 |
| F2 | 34 | section | 2 | 1 | 0.00 | 0 |
| F2 | 35 | section | 4 | 3 | 0.01 | 0 |
| F2 | 36 | section | 2 | 1 | 0.00 | 1 |
| F2 | 37 | section | 3,826 | 3,826 | 242.41 | 161 |
| F2 | 38 | section | 475 | 475 | 15.18 | 27 |
| F2 | 39 | section | 2 | 1 | 0.00 | 1 |
| F2 | 40 | section | 2 | 1 | 0.00 | 0 |
| F2 | 41 | section | 14 | 13 | 0.93 | 0 |
| F2 | 42 | section | 156 | 155 | 6.55 | 6 |
| F2 | 43 | section | 2 | 1 | 0.00 | 0 |
| F2 | 44 | section | 27 | 26 | 1.16 | 0 |
| F2 | 45 | section | 5 | 4 | 0.01 | 0 |
| F2 | 46 | section | 5 | 4 | 0.00 | 0 |
| F2 | 47 | section | 4 | 3 | 0.00 | 0 |
| F2 | 48 | section | 2 | 1 | 0.00 | 0 |
| F2 | 49 | section | 7 | 6 | 0.01 | 0 |
| F2 | 50 | section | 2 | 1 | 0.00 | 0 |
| F2 | 51 | section | 2 | 1 | 0.00 | 0 |
| F2 | 52 | section | 2 | 1 | 0.00 | 1 |
| F2 | 53 | section | 2 | 1 | 0.00 | 0 |
| F2 | 54 | section | 2 | 1 | 0.00 | 1 |
| F2 | 55 | section | 3 | 2 | 0.00 | 0 |
| F2 | 56 | section | 2 | 1 | 0.00 | 0 |
| F2 | 57 | section | 2 | 1 | 0.00 | 0 |
| F2 | 58 | section | 2 | 1 | 0.00 | 1 |
| F2 | 59 | section | 2 | 1 | 0.00 | 0 |
| F2 | 60 | section | 2 | 1 | 0.00 | 0 |
| F2 | 61 | section | 2 | 1 | 0.00 | 1 |
| F2 | 62 | section | 1,843 | 1,847 | 62.54 | 99 |
| F2 | 63 | section | 7 | 6 | 0.02 | 0 |
| F2 | 64 | section | 6 | 5 | 0.01 | 1 |
| F2 | 65 | section | 2 | 1 | 0.00 | 1 |
| F2 | 66 | section | 169 | 168 | 7.83 | 8 |
| F2 | 67 | section | 8 | 7 | 0.01 | 1 |
| F2 | 68 | section | 2 | 1 | 0.00 | 0 |
| F2 | 69 | section | 5 | 4 | 0.01 | 0 |
| F2 | 70 | section | 2 | 1 | 0.00 | 0 |
| F2 | 71 | section | 2 | 1 | 0.00 | 0 |
| F2 | 72 | section | 58 | 57 | 1.85 | 3 |
| F2 | 73 | section | 17 | 16 | 0.56 | 0 |
| F2 | 74 | section | 2 | 1 | 0.00 | 0 |
| F2 | 75 | section | 2 | 1 | 0.00 | 0 |
| F2 | 76 | section | 2 | 1 | 0.00 | 0 |
| F2 | 77 | section | 4 | 3 | 0.01 | 0 |
| F2 | 78 | section | 3 | 2 | 0.00 | 0 |
| F2 | 79 | section | 341 | 341 | 16.88 | 22 |
| F2 | 80 | section | 2 | 1 | 0.00 | 0 |
| F2 | 81 | section | 7 | 6 | 0.08 | 1 |
| F2 | 82 | section | 2 | 1 | 0.00 | 1 |
| F2 | 83 | section | 1,047 | 1,047 | 61.16 | 54 |
| F3 | 0 | head | 475 | 475 | 15.18 | 27 |
| F3 | 1 | section | 156 | 155 | 6.55 | 6 |
| F3 | 2 | section | 2 | 1 | 0.00 | 0 |
| F3 | 3 | section | 27 | 26 | 1.16 | 0 |
| F3 | 4 | section | 5 | 4 | 0.01 | 0 |
| F3 | 5 | section | 5 | 4 | 0.00 | 0 |
| F3 | 6 | section | 13 | 12 | 0.47 | 0 |
| F3 | 7 | section | 4 | 3 | 0.00 | 0 |
| F3 | 8 | section | 2 | 1 | 0.00 | 0 |
| F3 | 9 | section | 7 | 6 | 0.01 | 0 |
| F3 | 10 | section | 2 | 1 | 0.00 | 0 |
| F3 | 11 | section | 2 | 1 | 0.00 | 0 |
| F3 | 12 | section | 2 | 1 | 0.00 | 1 |
| F3 | 13 | section | 2 | 1 | 0.00 | 0 |
| F3 | 14 | section | 3 | 2 | 0.00 | 0 |
| F3 | 15 | section | 2 | 1 | 0.00 | 0 |
| F3 | 16 | section | 6 | 5 | 0.01 | 0 |
| F3 | 17 | section | 2 | 1 | 0.00 | 0 |
| F3 | 18 | section | 2 | 1 | 0.00 | 1 |
| F3 | 19 | section | 2 | 1 | 0.00 | 0 |
| F3 | 20 | section | 2 | 1 | 0.00 | 0 |
| F3 | 21 | section | 2 | 1 | 0.00 | 1 |
| F3 | 22 | section | 1,843 | 1,847 | 62.54 | 99 |
| F3 | 23 | section | 7 | 6 | 0.02 | 0 |
| F3 | 24 | section | 2 | 1 | 0.00 | 0 |
| F3 | 25 | section | 12 | 11 | 0.29 | 0 |
| F3 | 26 | section | 6 | 5 | 0.01 | 1 |
| F3 | 27 | section | 2 | 1 | 0.00 | 1 |
| F3 | 28 | section | 169 | 168 | 7.83 | 8 |
| F3 | 29 | section | 8 | 7 | 0.01 | 1 |
| F3 | 30 | section | 2 | 1 | 0.00 | 0 |
| F3 | 31 | section | 5 | 4 | 0.01 | 0 |
| F3 | 32 | section | 2 | 1 | 0.00 | 0 |
| F3 | 33 | section | 2 | 1 | 0.00 | 0 |
| F3 | 34 | section | 2 | 1 | 0.00 | 1 |
| F3 | 35 | section | 2 | 1 | 0.00 | 0 |
| F3 | 36 | section | 58 | 57 | 1.85 | 3 |
| F3 | 37 | section | 17 | 16 | 0.56 | 0 |
| F3 | 38 | section | 2 | 1 | 0.00 | 0 |
| F3 | 39 | section | 2 | 1 | 0.00 | 0 |
| F3 | 40 | section | 6 | 5 | 0.01 | 0 |
| F3 | 41 | section | 2 | 1 | 0.00 | 0 |
| F3 | 42 | section | 4 | 3 | 0.01 | 0 |
| F3 | 43 | section | 3 | 2 | 0.00 | 0 |
| F3 | 44 | section | 128 | 127 | 3.37 | 5 |
| F3 | 45 | section | 109 | 109 | 2.96 | 5 |
| F3 | 46 | section | 2 | 1 | 0.00 | 0 |
| F3 | 47 | section | 341 | 341 | 16.88 | 22 |
| F3 | 48 | section | 2 | 1 | 0.00 | 0 |
| F3 | 49 | section | 6 | 5 | 0.01 | 0 |
| F3 | 50 | section | 4 | 3 | 0.00 | 0 |
| F3 | 51 | section | 4 | 3 | 0.00 | 0 |
| F3 | 52 | section | 5 | 4 | 0.01 | 0 |
| F3 | 53 | section | 5 | 4 | 0.01 | 0 |
| F3 | 54 | section | 2 | 1 | 0.00 | 1 |
| F3 | 55 | section | 7 | 6 | 0.08 | 1 |
| F3 | 56 | section | 2 | 1 | 0.00 | 1 |
| F3 | 57 | section | 17 | 16 | 0.58 | 0 |
| F3 | 58 | section | 2 | 1 | 0.00 | 0 |
| F3 | 59 | section | 3 | 2 | 0.00 | 0 |
| F3 | 60 | section | 2 | 1 | 0.00 | 0 |
| F3 | 61 | section | 2,033 | 2,035 | 102.64 | 85 |
| F3 | 62 | section | 2 | 1 | 0.00 | 1 |
| F3 | 63 | section | 2 | 1 | 0.00 | 0 |
| F3 | 64 | section | 1,047 | 1,047 | 61.16 | 54 |
| F3 | 65 | section | 7 | 6 | 0.01 | 0 |
| F3 | 66 | section | 2 | 1 | 0.00 | 1 |
| F3 | 67 | section | 2 | 1 | 0.00 | 1 |
| F3 | 68 | section | 5 | 4 | 0.00 | 0 |
| F3 | 69 | section | 6 | 5 | 0.01 | 0 |
| F3 | 70 | section | 2 | 1 | 0.00 | 0 |
| F3 | 71 | section | 4 | 3 | 0.00 | 0 |
| F3 | 72 | section | 3 | 2 | 0.00 | 0 |
| F3 | 73 | section | 2 | 1 | 0.00 | 1 |
| F3 | 74 | section | 14 | 13 | 0.61 | 0 |
| F3 | 75 | section | 2 | 1 | 0.00 | 0 |
| F3 | 76 | section | 2 | 1 | 0.00 | 1 |
| F3 | 77 | section | 2 | 1 | 0.00 | 0 |
| F3 | 78 | section | 4 | 3 | 0.01 | 0 |
| F3 | 79 | section | 2 | 1 | 0.00 | 1 |
| F3 | 80 | section | 3,826 | 3,826 | 242.41 | 161 |
| F3 | 81 | section | 2 | 1 | 0.00 | 0 |
| F3 | 82 | section | 14 | 13 | 0.93 | 0 |
| F3 | 83 | section | 2 | 1 | 0.00 | 1 |
| F4 | 0 | head | 2,033 | 2,035 | 102.64 | 85 |
| F4 | 1 | section | 5 | 4 | 0.00 | 0 |
| F4 | 2 | section | 6 | 5 | 0.01 | 0 |
| F4 | 3 | section | 2 | 1 | 0.00 | 0 |
| F4 | 4 | section | 5 | 4 | 0.01 | 0 |
| F4 | 5 | section | 4 | 3 | 0.00 | 0 |
| F4 | 6 | section | 3 | 2 | 0.00 | 0 |
| F4 | 7 | section | 2 | 1 | 0.00 | 1 |
| F4 | 8 | section | 2 | 1 | 0.00 | 0 |
| F4 | 9 | section | 109 | 109 | 2.96 | 5 |
| F4 | 10 | section | 2 | 1 | 0.00 | 1 |
| F4 | 11 | section | 3,826 | 3,826 | 242.41 | 161 |
| F4 | 12 | section | 128 | 127 | 3.37 | 5 |
| F4 | 13 | section | 4 | 3 | 0.00 | 0 |
| F4 | 14 | section | 6 | 5 | 0.01 | 0 |
| F4 | 15 | section | 5 | 4 | 0.01 | 0 |
| F4 | 16 | section | 6 | 5 | 0.01 | 0 |
| F4 | 17 | section | 4 | 3 | 0.00 | 0 |
| F4 | 18 | section | 2 | 1 | 0.00 | 0 |
| F4 | 19 | section | 2 | 1 | 0.00 | 0 |
| F4 | 20 | section | 2 | 1 | 0.00 | 0 |
| F4 | 21 | section | 2 | 1 | 0.00 | 0 |
| F4 | 22 | section | 17 | 16 | 0.58 | 0 |
| F4 | 23 | section | 2 | 1 | 0.00 | 0 |
| F4 | 24 | section | 3 | 2 | 0.00 | 0 |
| F4 | 25 | section | 2 | 1 | 0.00 | 1 |
| F4 | 26 | section | 2 | 1 | 0.00 | 1 |
| F4 | 27 | section | 12 | 11 | 0.29 | 0 |
| F4 | 28 | section | 2 | 1 | 0.00 | 1 |
| F4 | 29 | section | 7 | 6 | 0.01 | 0 |
| F4 | 30 | section | 2 | 1 | 0.00 | 1 |
| F4 | 31 | section | 6 | 5 | 0.01 | 0 |
| F4 | 32 | section | 14 | 13 | 0.61 | 0 |
| F4 | 33 | section | 2 | 1 | 0.00 | 0 |
| F4 | 34 | section | 13 | 12 | 0.47 | 0 |
| F4 | 35 | section | 2 | 1 | 0.00 | 0 |
| F4 | 36 | section | 4 | 3 | 0.01 | 0 |
| F4 | 37 | section | 2 | 1 | 0.00 | 1 |
| F4 | 38 | section | 475 | 475 | 15.18 | 27 |
| F4 | 39 | section | 2 | 1 | 0.00 | 1 |
| F4 | 40 | section | 2 | 1 | 0.00 | 0 |
| F4 | 41 | section | 14 | 13 | 0.93 | 0 |
| F4 | 42 | section | 156 | 155 | 6.55 | 6 |
| F4 | 43 | section | 2 | 1 | 0.00 | 0 |
| F4 | 44 | section | 27 | 26 | 1.16 | 0 |
| F4 | 45 | section | 5 | 4 | 0.01 | 0 |
| F4 | 46 | section | 5 | 4 | 0.00 | 0 |
| F4 | 47 | section | 4 | 3 | 0.00 | 0 |
| F4 | 48 | section | 2 | 1 | 0.00 | 0 |
| F4 | 49 | section | 7 | 6 | 0.01 | 0 |
| F4 | 50 | section | 2 | 1 | 0.00 | 0 |
| F4 | 51 | section | 2 | 1 | 0.00 | 0 |
| F4 | 52 | section | 2 | 1 | 0.00 | 1 |
| F4 | 53 | section | 2 | 1 | 0.00 | 0 |
| F4 | 54 | section | 2 | 1 | 0.00 | 1 |
| F4 | 55 | section | 3 | 2 | 0.00 | 0 |
| F4 | 56 | section | 2 | 1 | 0.00 | 0 |
| F4 | 57 | section | 2 | 1 | 0.00 | 0 |
| F4 | 58 | section | 2 | 1 | 0.00 | 1 |
| F4 | 59 | section | 2 | 1 | 0.00 | 0 |
| F4 | 60 | section | 2 | 1 | 0.00 | 0 |
| F4 | 61 | section | 2 | 1 | 0.00 | 1 |
| F4 | 62 | section | 1,843 | 1,847 | 62.54 | 99 |
| F4 | 63 | section | 7 | 6 | 0.02 | 0 |
| F4 | 64 | section | 6 | 5 | 0.01 | 1 |
| F4 | 65 | section | 2 | 1 | 0.00 | 1 |
| F4 | 66 | section | 169 | 168 | 7.83 | 8 |
| F4 | 67 | section | 8 | 7 | 0.01 | 1 |
| F4 | 68 | section | 2 | 1 | 0.00 | 0 |
| F4 | 69 | section | 5 | 4 | 0.01 | 0 |
| F4 | 70 | section | 2 | 1 | 0.00 | 0 |
| F4 | 71 | section | 2 | 1 | 0.00 | 0 |
| F4 | 72 | section | 58 | 57 | 1.85 | 3 |
| F4 | 73 | section | 17 | 16 | 0.56 | 0 |
| F4 | 74 | section | 2 | 1 | 0.00 | 0 |
| F4 | 75 | section | 2 | 1 | 0.00 | 0 |
| F4 | 76 | section | 2 | 1 | 0.00 | 0 |
| F4 | 77 | section | 4 | 3 | 0.01 | 0 |
| F4 | 78 | section | 3 | 2 | 0.00 | 0 |
| F4 | 79 | section | 341 | 341 | 16.88 | 22 |
| F4 | 80 | section | 2 | 1 | 0.00 | 0 |
| F4 | 81 | section | 7 | 6 | 0.08 | 1 |
| F4 | 82 | section | 2 | 1 | 0.00 | 1 |
| F4 | 83 | section | 1,047 | 1,047 | 61.16 | 54 |
| F5 | 0 | head | 1,843 | 1,847 | 62.54 | 99 |
| F5 | 1 | section | 169 | 168 | 7.83 | 8 |
| F5 | 2 | section | 8 | 7 | 0.01 | 1 |
| F5 | 3 | section | 2 | 1 | 0.00 | 0 |
| F5 | 4 | section | 3 | 2 | 0.00 | 0 |
| F5 | 5 | section | 5 | 4 | 0.01 | 0 |
| F5 | 6 | section | 2 | 1 | 0.00 | 0 |
| F5 | 7 | section | 2 | 1 | 0.00 | 0 |
| F5 | 8 | section | 58 | 57 | 1.85 | 3 |
| F5 | 9 | section | 17 | 16 | 0.56 | 0 |
| F5 | 10 | section | 2 | 1 | 0.00 | 0 |
| F5 | 11 | section | 27 | 26 | 1.16 | 0 |
| F5 | 12 | section | 2 | 1 | 0.00 | 0 |
| F5 | 13 | section | 2 | 1 | 0.00 | 0 |
| F5 | 14 | section | 4 | 3 | 0.01 | 0 |
| F5 | 15 | section | 475 | 475 | 15.18 | 27 |
| F5 | 16 | section | 3 | 2 | 0.00 | 0 |
| F5 | 17 | section | 341 | 341 | 16.88 | 22 |
| F5 | 18 | section | 2 | 1 | 0.00 | 0 |
| F5 | 19 | section | 156 | 155 | 6.55 | 6 |
| F5 | 20 | section | 2 | 1 | 0.00 | 0 |
| F5 | 21 | section | 5 | 4 | 0.01 | 0 |
| F5 | 22 | section | 5 | 4 | 0.00 | 0 |
| F5 | 23 | section | 13 | 12 | 0.47 | 0 |
| F5 | 24 | section | 4 | 3 | 0.00 | 0 |
| F5 | 25 | section | 2 | 1 | 0.00 | 0 |
| F5 | 26 | section | 7 | 6 | 0.01 | 0 |
| F5 | 27 | section | 2 | 1 | 0.00 | 0 |
| F5 | 28 | section | 2 | 1 | 0.00 | 0 |
| F5 | 29 | section | 2 | 1 | 0.00 | 1 |
| F5 | 30 | section | 2 | 1 | 0.00 | 0 |
| F5 | 31 | section | 7 | 6 | 0.08 | 1 |
| F5 | 32 | section | 2 | 1 | 0.00 | 1 |
| F5 | 33 | section | 2 | 1 | 0.00 | 0 |
| F5 | 34 | section | 6 | 5 | 0.01 | 0 |
| F5 | 35 | section | 2 | 1 | 0.00 | 0 |
| F5 | 36 | section | 2 | 1 | 0.00 | 1 |
| F5 | 37 | section | 2 | 1 | 0.00 | 0 |
| F5 | 38 | section | 2 | 1 | 0.00 | 0 |
| F5 | 39 | section | 2 | 1 | 0.00 | 1 |
| F5 | 40 | section | 1,047 | 1,047 | 61.16 | 54 |
| F5 | 41 | section | 7 | 6 | 0.02 | 0 |
| F5 | 42 | section | 2 | 1 | 0.00 | 0 |
| F5 | 43 | section | 12 | 11 | 0.29 | 0 |
| F5 | 44 | section | 6 | 5 | 0.01 | 1 |
| F5 | 45 | section | 2 | 1 | 0.00 | 1 |
| F5 | 46 | section | 2 | 1 | 0.00 | 1 |
| F5 | 47 | section | 2 | 1 | 0.00 | 0 |
| F5 | 48 | section | 6 | 5 | 0.01 | 0 |
| F5 | 49 | section | 128 | 127 | 3.37 | 5 |
| F5 | 50 | section | 109 | 109 | 2.96 | 5 |
| F5 | 51 | section | 2 | 1 | 0.00 | 0 |
| F5 | 52 | section | 6 | 5 | 0.01 | 0 |
| F5 | 53 | section | 4 | 3 | 0.00 | 0 |
| F5 | 54 | section | 4 | 3 | 0.00 | 0 |
| F5 | 55 | section | 5 | 4 | 0.01 | 0 |
| F5 | 56 | section | 5 | 4 | 0.01 | 0 |
| F5 | 57 | section | 2 | 1 | 0.00 | 1 |
| F5 | 58 | section | 17 | 16 | 0.58 | 0 |
| F5 | 59 | section | 2 | 1 | 0.00 | 0 |
| F5 | 60 | section | 3 | 2 | 0.00 | 0 |
| F5 | 61 | section | 2 | 1 | 0.00 | 0 |
| F5 | 62 | section | 2,033 | 2,035 | 102.64 | 85 |
| F5 | 63 | section | 2 | 1 | 0.00 | 1 |
| F5 | 64 | section | 2 | 1 | 0.00 | 0 |
| F5 | 65 | section | 7 | 6 | 0.01 | 0 |
| F5 | 66 | section | 2 | 1 | 0.00 | 1 |
| F5 | 67 | section | 2 | 1 | 0.00 | 1 |
| F5 | 68 | section | 5 | 4 | 0.00 | 0 |
| F5 | 69 | section | 6 | 5 | 0.01 | 0 |
| F5 | 70 | section | 2 | 1 | 0.00 | 0 |
| F5 | 71 | section | 4 | 3 | 0.00 | 0 |
| F5 | 72 | section | 3 | 2 | 0.00 | 0 |
| F5 | 73 | section | 2 | 1 | 0.00 | 1 |
| F5 | 74 | section | 14 | 13 | 0.61 | 0 |
| F5 | 75 | section | 2 | 1 | 0.00 | 0 |
| F5 | 76 | section | 2 | 1 | 0.00 | 1 |
| F5 | 77 | section | 2 | 1 | 0.00 | 0 |
| F5 | 78 | section | 4 | 3 | 0.01 | 0 |
| F5 | 79 | section | 2 | 1 | 0.00 | 1 |
| F5 | 80 | section | 3,826 | 3,826 | 242.41 | 161 |
| F5 | 81 | section | 2 | 1 | 0.00 | 0 |
| F5 | 82 | section | 14 | 13 | 0.93 | 0 |
| F5 | 83 | section | 2 | 1 | 0.00 | 1 |
| F6 | 0 | head | 14 | 13 | 0.93 | 0 |
| F6 | 1 | section | 4 | 3 | 0.01 | 0 |
| F6 | 2 | section | 14 | 13 | 0.61 | 0 |
| F6 | 3 | section | 2 | 1 | 0.00 | 0 |
| F6 | 4 | section | 7 | 6 | 0.01 | 0 |
| F6 | 5 | section | 2 | 1 | 0.00 | 1 |
| F6 | 6 | section | 17 | 16 | 0.58 | 0 |
| F6 | 7 | section | 2 | 1 | 0.00 | 0 |
| F6 | 8 | section | 6 | 5 | 0.01 | 0 |
| F6 | 9 | section | 2 | 1 | 0.00 | 1 |
| F6 | 10 | section | 128 | 127 | 3.37 | 5 |
| F6 | 11 | section | 2 | 1 | 0.00 | 0 |
| F6 | 12 | section | 109 | 109 | 2.96 | 5 |
| F6 | 13 | section | 6 | 5 | 0.01 | 0 |
| F6 | 14 | section | 4 | 3 | 0.00 | 0 |
| F6 | 15 | section | 2 | 1 | 0.00 | 1 |
| F6 | 16 | section | 4 | 3 | 0.00 | 0 |
| F6 | 17 | section | 5 | 4 | 0.01 | 0 |
| F6 | 18 | section | 5 | 4 | 0.01 | 0 |
| F6 | 19 | section | 2 | 1 | 0.00 | 0 |
| F6 | 20 | section | 2 | 1 | 0.00 | 0 |
| F6 | 21 | section | 3 | 2 | 0.00 | 0 |
| F6 | 22 | section | 2 | 1 | 0.00 | 0 |
| F6 | 23 | section | 2,033 | 2,035 | 102.64 | 85 |
| F6 | 24 | section | 2 | 1 | 0.00 | 1 |
| F6 | 25 | section | 2 | 1 | 0.00 | 0 |
| F6 | 26 | section | 2 | 1 | 0.00 | 1 |
| F6 | 27 | section | 12 | 11 | 0.29 | 0 |
| F6 | 28 | section | 2 | 1 | 0.00 | 1 |
| F6 | 29 | section | 5 | 4 | 0.00 | 0 |
| F6 | 30 | section | 6 | 5 | 0.01 | 0 |
| F6 | 31 | section | 2 | 1 | 0.00 | 0 |
| F6 | 32 | section | 4 | 3 | 0.00 | 0 |
| F6 | 33 | section | 3 | 2 | 0.00 | 0 |
| F6 | 34 | section | 2 | 1 | 0.00 | 1 |
| F6 | 35 | section | 6 | 5 | 0.01 | 0 |
| F6 | 36 | section | 2 | 1 | 0.00 | 1 |
| F6 | 37 | section | 2 | 1 | 0.00 | 0 |
| F6 | 38 | section | 13 | 12 | 0.47 | 0 |
| F6 | 39 | section | 2 | 1 | 0.00 | 0 |
| F6 | 40 | section | 3,826 | 3,826 | 242.41 | 161 |
| F6 | 41 | section | 475 | 475 | 15.18 | 27 |
| F6 | 42 | section | 2 | 1 | 0.00 | 1 |
| F6 | 43 | section | 156 | 155 | 6.55 | 6 |
| F6 | 44 | section | 2 | 1 | 0.00 | 0 |
| F6 | 45 | section | 27 | 26 | 1.16 | 0 |
| F6 | 46 | section | 5 | 4 | 0.01 | 0 |
| F6 | 47 | section | 5 | 4 | 0.00 | 0 |
| F6 | 48 | section | 4 | 3 | 0.00 | 0 |
| F6 | 49 | section | 2 | 1 | 0.00 | 0 |
| F6 | 50 | section | 7 | 6 | 0.01 | 0 |
| F6 | 51 | section | 2 | 1 | 0.00 | 0 |
| F6 | 52 | section | 2 | 1 | 0.00 | 0 |
| F6 | 53 | section | 2 | 1 | 0.00 | 1 |
| F6 | 54 | section | 2 | 1 | 0.00 | 0 |
| F6 | 55 | section | 3 | 2 | 0.00 | 0 |
| F6 | 56 | section | 2 | 1 | 0.00 | 0 |
| F6 | 57 | section | 2 | 1 | 0.00 | 0 |
| F6 | 58 | section | 2 | 1 | 0.00 | 1 |
| F6 | 59 | section | 2 | 1 | 0.00 | 0 |
| F6 | 60 | section | 2 | 1 | 0.00 | 0 |
| F6 | 61 | section | 2 | 1 | 0.00 | 1 |
| F6 | 62 | section | 1,843 | 1,847 | 62.54 | 99 |
| F6 | 63 | section | 7 | 6 | 0.02 | 0 |
| F6 | 64 | section | 6 | 5 | 0.01 | 1 |
| F6 | 65 | section | 2 | 1 | 0.00 | 1 |
| F6 | 66 | section | 169 | 168 | 7.83 | 8 |
| F6 | 67 | section | 8 | 7 | 0.01 | 1 |
| F6 | 68 | section | 2 | 1 | 0.00 | 0 |
| F6 | 69 | section | 5 | 4 | 0.01 | 0 |
| F6 | 70 | section | 2 | 1 | 0.00 | 0 |
| F6 | 71 | section | 2 | 1 | 0.00 | 0 |
| F6 | 72 | section | 58 | 57 | 1.85 | 3 |
| F6 | 73 | section | 17 | 16 | 0.56 | 0 |
| F6 | 74 | section | 2 | 1 | 0.00 | 0 |
| F6 | 75 | section | 2 | 1 | 0.00 | 0 |
| F6 | 76 | section | 2 | 1 | 0.00 | 0 |
| F6 | 77 | section | 4 | 3 | 0.01 | 0 |
| F6 | 78 | section | 3 | 2 | 0.00 | 0 |
| F6 | 79 | section | 341 | 341 | 16.88 | 22 |
| F6 | 80 | section | 2 | 1 | 0.00 | 0 |
| F6 | 81 | section | 7 | 6 | 0.08 | 1 |
| F6 | 82 | section | 2 | 1 | 0.00 | 1 |
| F6 | 83 | section | 1,047 | 1,047 | 61.16 | 54 |
| F7 | 0 | head | 475 | 475 | 15.18 | 27 |
| F7 | 1 | section | 156 | 155 | 6.55 | 6 |
| F7 | 2 | section | 2 | 1 | 0.00 | 0 |
| F7 | 3 | section | 27 | 26 | 1.16 | 0 |
| F7 | 4 | section | 5 | 4 | 0.01 | 0 |
| F7 | 5 | section | 5 | 4 | 0.00 | 0 |
| F7 | 6 | section | 13 | 12 | 0.47 | 0 |
| F7 | 7 | section | 4 | 3 | 0.00 | 0 |
| F7 | 8 | section | 2 | 1 | 0.00 | 0 |
| F7 | 9 | section | 7 | 6 | 0.01 | 0 |
| F7 | 10 | section | 2 | 1 | 0.00 | 0 |
| F7 | 11 | section | 2 | 1 | 0.00 | 0 |
| F7 | 12 | section | 2 | 1 | 0.00 | 1 |
| F7 | 13 | section | 2 | 1 | 0.00 | 0 |
| F7 | 14 | section | 3 | 2 | 0.00 | 0 |
| F7 | 15 | section | 2 | 1 | 0.00 | 0 |
| F7 | 16 | section | 6 | 5 | 0.01 | 0 |
| F7 | 17 | section | 2 | 1 | 0.00 | 0 |
| F7 | 18 | section | 2 | 1 | 0.00 | 1 |
| F7 | 19 | section | 2 | 1 | 0.00 | 0 |
| F7 | 20 | section | 2 | 1 | 0.00 | 0 |
| F7 | 21 | section | 2 | 1 | 0.00 | 1 |
| F7 | 22 | section | 1,843 | 1,847 | 62.54 | 99 |
| F7 | 23 | section | 7 | 6 | 0.02 | 0 |
| F7 | 24 | section | 2 | 1 | 0.00 | 0 |
| F7 | 25 | section | 12 | 11 | 0.29 | 0 |
| F7 | 26 | section | 6 | 5 | 0.01 | 1 |
| F7 | 27 | section | 2 | 1 | 0.00 | 1 |
| F7 | 28 | section | 169 | 168 | 7.83 | 8 |
| F7 | 29 | section | 8 | 7 | 0.01 | 1 |
| F7 | 30 | section | 2 | 1 | 0.00 | 0 |
| F7 | 31 | section | 5 | 4 | 0.01 | 0 |
| F7 | 32 | section | 2 | 1 | 0.00 | 0 |
| F7 | 33 | section | 2 | 1 | 0.00 | 0 |
| F7 | 34 | section | 2 | 1 | 0.00 | 1 |
| F7 | 35 | section | 2 | 1 | 0.00 | 0 |
| F7 | 36 | section | 58 | 57 | 1.85 | 3 |
| F7 | 37 | section | 17 | 16 | 0.56 | 0 |
| F7 | 38 | section | 2 | 1 | 0.00 | 0 |
| F7 | 39 | section | 2 | 1 | 0.00 | 0 |
| F7 | 40 | section | 6 | 5 | 0.01 | 0 |
| F7 | 41 | section | 2 | 1 | 0.00 | 0 |
| F7 | 42 | section | 4 | 3 | 0.01 | 0 |
| F7 | 43 | section | 3 | 2 | 0.00 | 0 |
| F7 | 44 | section | 128 | 127 | 3.37 | 5 |
| F7 | 45 | section | 109 | 109 | 2.96 | 5 |
| F7 | 46 | section | 2 | 1 | 0.00 | 0 |
| F7 | 47 | section | 341 | 341 | 16.88 | 22 |
| F7 | 48 | section | 2 | 1 | 0.00 | 0 |
| F7 | 49 | section | 6 | 5 | 0.01 | 0 |
| F7 | 50 | section | 4 | 3 | 0.00 | 0 |
| F7 | 51 | section | 4 | 3 | 0.00 | 0 |
| F7 | 52 | section | 5 | 4 | 0.01 | 0 |
| F7 | 53 | section | 5 | 4 | 0.01 | 0 |
| F7 | 54 | section | 2 | 1 | 0.00 | 1 |
| F7 | 55 | section | 7 | 6 | 0.08 | 1 |
| F7 | 56 | section | 2 | 1 | 0.00 | 1 |
| F7 | 57 | section | 17 | 16 | 0.58 | 0 |
| F7 | 58 | section | 2 | 1 | 0.00 | 0 |
| F7 | 59 | section | 3 | 2 | 0.00 | 0 |
| F7 | 60 | section | 2 | 1 | 0.00 | 0 |
| F7 | 61 | section | 2,033 | 2,035 | 102.64 | 85 |
| F7 | 62 | section | 2 | 1 | 0.00 | 1 |
| F7 | 63 | section | 2 | 1 | 0.00 | 0 |
| F7 | 64 | section | 1,047 | 1,047 | 61.16 | 54 |
| F7 | 65 | section | 7 | 6 | 0.01 | 0 |
| F7 | 66 | section | 2 | 1 | 0.00 | 1 |
| F7 | 67 | section | 2 | 1 | 0.00 | 1 |
| F7 | 68 | section | 5 | 4 | 0.00 | 0 |
| F7 | 69 | section | 6 | 5 | 0.01 | 0 |
| F7 | 70 | section | 2 | 1 | 0.00 | 0 |
| F7 | 71 | section | 4 | 3 | 0.00 | 0 |
| F7 | 72 | section | 3 | 2 | 0.00 | 0 |
| F7 | 73 | section | 2 | 1 | 0.00 | 1 |
| F7 | 74 | section | 14 | 13 | 0.61 | 0 |
| F7 | 75 | section | 2 | 1 | 0.00 | 0 |
| F7 | 76 | section | 2 | 1 | 0.00 | 1 |
| F7 | 77 | section | 2 | 1 | 0.00 | 0 |
| F7 | 78 | section | 4 | 3 | 0.01 | 0 |
| F7 | 79 | section | 2 | 1 | 0.00 | 1 |
| F7 | 80 | section | 3,826 | 3,826 | 242.41 | 161 |
| F7 | 81 | section | 2 | 1 | 0.00 | 0 |
| F7 | 82 | section | 14 | 13 | 0.93 | 0 |
| F7 | 83 | section | 2 | 1 | 0.00 | 1 |

## ۴. کاندیدهای NO/Tie (A-09 — قاعده پیشنهادی R1/R2، نیازمند تأیید مهندس)

| فیدرها | قاعده | کلید کاندید | اتوماسیون (T_ctrl_otm) | وضعیت |
|---|---|---|---|---|
| F2 ↔ F3 | R1-overlap | کلید 70fc7b01… | بله | candidate |
| F2 ↔ F3 | R1-overlap | کلید 78327900… | بله | candidate |
| F2 ↔ F3 | R1-overlap | کلید 23016d0d… | بله | candidate |
| F2 ↔ F3 | R1-overlap | کلید 8d9db8c5… | بله | candidate |
| F2 ↔ F3 | R1-overlap | کلید b03751a9… | بله | candidate |
| F2 ↔ F3 | R1-overlap | کلید 73933bad… | بله | candidate |
| F2 ↔ F3 | R1-overlap | کلید 4d4fc278… | بله | candidate |
| F2 ↔ F3 | R1-overlap | کلید 7dbb8e68… | بله | candidate |
| F2 ↔ F3 | R1-overlap | کلید 01c9d76f… | بله | candidate |
| F2 ↔ F3 | R1-overlap | کلید b2e94588… | بله | candidate |
| F2 ↔ F3 | R1-overlap | کلید e32cbcc5… | بله | candidate |
| F2 ↔ F3 | R1-overlap | کلید 4595bd2f… | بله | candidate |
| F2 ↔ F3 | R1-overlap | کلید e2234af7… | بله | candidate |
| F2 ↔ F3 | R1-overlap | کلید 3ac7da0c… | بله | candidate |
| F2 ↔ F3 | R1-overlap | کلید 98a567db… | بله | candidate |
| F2 ↔ F3 | R1-overlap | کلید b20059b3… | بله | candidate |
| F2 ↔ F3 | R1-overlap | کلید f675739a… | بله | candidate |
| F2 ↔ F3 | R1-overlap | کلید 0253fb08… | بله | candidate |
| F2 ↔ F3 | R1-overlap | کلید dede249a… | بله | candidate |
| F2 ↔ F3 | R1-overlap | کلید 1745a74b… | بله | candidate |
| F2 ↔ F3 | R1-overlap | کلید f013f19b… | بله | candidate |
| F2 ↔ F3 | R1-overlap | کلید da04a20f… | بله | candidate |
| F2 ↔ F3 | R1-overlap | کلید 33a443a0… | بله | candidate |
| F2 ↔ F3 | R1-overlap | کلید eead8f7e… | بله | candidate |
| F2 ↔ F3 | R1-overlap | کلید cc2b5cdf… | بله | candidate |
| F2 ↔ F3 | R1-overlap | کلید 700f398b… | بله | candidate |
| F2 ↔ F3 | R1-overlap | کلید f39c1e1a… | بله | candidate |
| F2 ↔ F3 | R1-overlap | کلید b4efc070… | بله | candidate |
| F2 ↔ F3 | R1-overlap | کلید d1f37dea… | بله | candidate |
| F2 ↔ F3 | R1-overlap | کلید 5e3dc8b7… | بله | candidate |
| F2 ↔ F3 | R1-overlap | کلید e65ca9bd… | بله | candidate |
| F2 ↔ F3 | R1-overlap | کلید bb41a31d… | بله | candidate |
| F2 ↔ F3 | R1-overlap | کلید 79acd18c… | بله | candidate |
| F2 ↔ F4 | R1-overlap | کلید 70fc7b01… | بله | candidate |
| F2 ↔ F4 | R1-overlap | کلید 78327900… | بله | candidate |
| F2 ↔ F4 | R1-overlap | کلید 23016d0d… | بله | candidate |
| F2 ↔ F4 | R1-overlap | کلید 8d9db8c5… | بله | candidate |
| F2 ↔ F4 | R1-overlap | کلید b03751a9… | بله | candidate |
| F2 ↔ F4 | R1-overlap | کلید 73933bad… | بله | candidate |
| F2 ↔ F4 | R1-overlap | کلید 4d4fc278… | بله | candidate |
| F2 ↔ F5 | R2-label | کلید 56b58a87… | خیر | candidate |

## ۵. سناریوی پایه و برق‌داری

```json
{
  "scenario": "وضعیت عادی (از GIS)",
  "energized_nodes": 11616,
  "energized_edges": 11636,
  "deenergized_nodes": 1034,
  "deenergized_edges": 1035,
  "by_feeder": {
    "F1": 1195,
    "F2": 10421
  },
  "isolated_zones": 1
}
```

## ۶. شمارش Issueهای توپولوژی

| کد | تعداد |
|---|---|
| GIS-SWITCH-STATE-UNKNOWN | 623 |
| TOPO-BRANCH-DEGENERATE | 440 |
| GIS-DUP-LINE | 201 |
| GIS-FEEDER-MISSING | 41 |
| GIS-ORPHAN-DEVICE | 32 |
| TOPO-FEEDER-MISMATCH | 30 |
| TOPO-SWITCH-NODE-BRANCHY | 10 |
| GIS-TRANSFORMER-NO-CAPACITY | 3 |
| GIS-SLOT-DEFERRED | 1 |
| GIS-AMBIGUOUS-SNAP | 1 |
| TOPO-UNTRACED-AREA | 1 |
| TOPO-STRICT-CORE | 1 |
| TOPO-TIE-CANDIDATES | 1 |
| TOPO-FEEDER-INTERCONNECTED | 1 |
| TOPO-ZONE-SHARED-EDGE | 1 |
