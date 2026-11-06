# گزارش کنترل کیفیت ورود داده — خلخال — نمونه واقعی ۱۲ لایه (فاز ۱)

**نتیجه پذیرش: ✅ PASS** — هیچ Issue از رده Error حل‌نشده وجود ندارد؛ مدل canonical وارد فاز توپولوژی می‌شود.

## خلاصه مدل canonical

- project: خلخال — نمونه واقعی ۱۲ لایه (فاز ۱)
- nodes: 12689
- branches: 12484
- branches_excluded: 0
- switches: 788
- transformers: 627
- loads: 627
- feeders: 8
- source_records: 13907
- stats: {'line_features': 12484, 'device_features': 1423, 'endpoint_points': 25644, 'clusters': 12650}

## شمارش اهمیت Issueها

- Error: 0
- Warning: 860
- Information: 42

## Issueها بر اساس کد

| کد | تعداد |
|---|---|
| GIS-SWITCH-STATE-UNKNOWN | 623 |
| GIS-DUP-LINE | 201 |
| GIS-FEEDER-MISSING | 41 |
| GIS-ORPHAN-DEVICE | 32 |
| GIS-TRANSFORMER-NO-CAPACITY | 3 |
| GIS-SLOT-DEFERRED | 1 |
| GIS-AMBIGUOUS-SNAP | 1 |

## Issueها بر اساس لایه و اهمیت

| لایه | Error | Warning | Information |
|---|---|---|---|
| ELWABS | 0 | 0 | 1 |
| ELWCBR | 0 | 25 | 0 |
| ELWDCS | 0 | 65 | 0 |
| ELWDTR | 0 | 35 | 3 |
| ELWFCT | 0 | 533 | 1 |
| ELWJUP | 0 | 4 | 0 |
| ELWMLN | 0 | 0 | 1 |
| ELWOML | 0 | 197 | 36 |
| ELWREC | 0 | 1 | 0 |
