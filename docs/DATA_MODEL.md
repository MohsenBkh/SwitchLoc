# DATA_MODEL.md — مدل داده Canonical شبکه (خروجی فاز صفر)

| مورد | مقدار |
|---|---|
| سند | موجودیت‌های داخلی SwitchLoc مستقل از GIS/DGS (بند ۶ پرامپت مادر) |
| اصل | هر موجودیت: شناسه یکتا + شناسه منبع (SourceRecord) + منشأ داده + وضعیت؛ هیچ مقدار فرضی پنهان |
| پیاده‌سازی فیزیکی | SQLite (فاز ۱) — جدول‌ها عیناً از این سند تولید می‌شوند |

## ۱. گروه پروژه مطالعاتی

| موجودیت | فیلدهای کلیدی | یادداشت |
|---|---|---|
| **StudyProject** | id, name, utility, province, study_type (جدول ۹: نوع ۱-۴), horizon, crs_analysis, settings_json, created_at, updated_at | study_type مطابق جدول ۹ دستورالعمل |
| **StudyRun** | id, project_id, started_at, user, algo_version, tav_revision, input_hashes, settings_snapshot, status | بازتولیدپذیری |
| **ValidationIssue** | id, run_id, severity(Error/Warning/Information), code, message_fa, source_file, layer, record_id, field, current_value, suggestion, impact, status(open/resolved/waived) | سه سطح بند ۱۹ |
| **SourceRecord** | id, file_path, file_sha256, layer, record_ref, geometry_ref | ردیابی تا رکورد |
| **LayerMapping** | id, project_id, slot_key, file_path, layer_name, field_map_json, enabled, confirmed_by, confirmed_at | نگاشت قطعی فقط با تأیید کاربر |
| **CRSDefinition** | id, project_id, layer, crs_original, crs_analysis, epsg, transform_note | جلوگیری از تبدیل تکراری |
| **CalculationResult** | id, run_id, target_entity, target_id, metric, value, unit, formula_ref (مثلاً «TAV122 رابطه ۱۰»), inputs_json | هر عدد خروجی با فرمول مرجع |

## ۲. گروه شبکه

| موجودیت | فیلدهای کلیدی | یادداشت |
|---|---|---|
| **Substation** | id, name, code, voltage_levels, geometry_ref | پست فوق‌توزیع/توزیع |
| **Feeder** | id, name (مثل «F5 - KHALKHAL»), substation_id, nominal_kv, source_node_id, status | نام از زنجیره fallback مستندشده |
| **Node** | id, feeder_id, kind(bus/junction/device_hv/device_lv), coord_original(x,y), coord_snapped(x,y), uknom, priority, load_kw | زون‌بندی روی این گراف |
| **Terminal** | id, node_id, element_id, side(0/1) | ساختار cubicle مطابق گراف الکتریکی |
| **Branch** | id, kind(line/cable/jumper/transformer_coupling), node_a, node_b, length_registered_m, length_geometric_m, type_id, feeder_id | length_registered از GIS؛ مقایسه دو طول → Issue |
| **Line / Cable** | فیلدهای Branch + conductor (T_jns_hadi)، section_mm2 (T_cod_sath)، installation (T_typ_shab)، is_covered | از فیلدهای واقعی GIS |
| **Transformer** | id, node_id, capacity_kva (T_strn), loss_class, insulation, year, feeder_id | کلاس تلفات از کلیدواژه‌ها + ثبت فرض |
| **Load** | id, node_id, transformer_id?, category(جدول ۱۲), priority_weight, p_kw, q_kvar, data_source(measured/estimated/...) | data_source اجباری — منبع واقعی یا تخمین اعلام‌شده |
| **Customer** | id, load_id, billing_ref, tariff | فاز ۳ در صورت ورود بیلینگ |
| **Switch** | id, node_id, switch_type(disconnector/manual|motorized|remote, breaker, recloser, sectionalizer, fuse, tie), normally_state(NO/NC), current_state, rating_a, breaking_capable, load_break_capable, remote_controlled, telecom_id?, coord, layer, record_ref | ترکیب نوع/قابلیت بند ۳-۲؛ `T_ctrl_otm` → remote_controlled؛ `T__outserv` → current_state |
| **Recloser** | Switch + max_fault_current (T_max_jrn_), settings_json | |
| **Sectionalizer** | Switch + | |
| **TieConnection** | id, feeder_a, feeder_b, switch_id?, automation_capable(bool), backup_capacity_kva, thermal_limit, voltage_limit, operational_limit, transferable_kw, status | **فقط اتصال با کلید اتوماسیون در EP/TL شمرده می‌شود** (جدول ۱۳) |
| **Capacitor** | id, node_id, q_kvar | |
| **DistributedGeneration** | id, node_id, type, capacity_kw/kvar, pcc_protections | |

## ۳. گروه داده‌های مطالعه

| موجودیت | فیلدهای کلیدی | یادداشت |
|---|---|---|
| **Outage** | id, event_no, feeder_ref, substation_ref, start_at, end_at, duration_min, cause_raw, cause_class, device_operated, protection_fn, affected_customers?(nullable), unserved_energy(واحد ثبت‌شده), location_hint, plan_type?(nullable), raw_row | ستون‌های مفقود nullable + Issue (A-08) — **فاز ۳ پیاده شد**: جداول `outage_run` / `outage_event` (با feeder_key/in_model/cause_group/rule_id/review_status) / `outage_lambda_r` (λ، r، U=λr/60، λ قابل کاهش)؛ مدل پایتونی `reliability/outages.py :: OutageRecord` |
| **MaintenanceRecord** | id, asset_ref, date, action, findings | سامانه نت — فاز ۳ اختیاری |
| **TelecomCoverage** | id, area/polygon یا node, coverage_status, bearer, quality, future_capable, cost_hint | بند ۱۱ |
| **ProtectionSetting** | id, device_ref, function, pickup, curves_json | گام پنجم جدول ۲ |
| **SwitchingScenario** | id, project_id, name, base_run_id, switch_actions_json (open/close/add/move), graph_state_ref | توپولوژی پایه تغییر نمی‌کند |
| **N1Scenario** | id, scenario_id, faulted_zone, shed_kw, restored_kw, restored_by_tie_id, within_30min(bool) | ردیف‌های جدول ۱۵ |
| **CandidateLocation** | id, node_id/branch_id, coord, proposed_type, rationale_code, up_value, ens_effect_kwh, telecom_status, install_constraint, score, rank, engineer_status | بند ۱۳-۳ |
| **CostItem** | id, scenario_id, kind(purchase/install/aux/telecom/relocation/network/opex), amount_rials, source | بند ۱۵؛ نبود داده → اعلام صریح |
| **Zone** | id, feeder_id, zone_index, node_ids, load_kw, lambda, r_min, u_hours, up_value | خروجی زون‌بندی؛ رابطه (۱۰) روی up_value |

## ۴. قواعد داده

1. **شناسه‌ها:** همه موجودیت‌ها `id` داخلی UUID/INTEGER دارند؛ `source_record_id` به SourceRecord وصل است؛ شناسه GIS (`T_MapID`/OBJECTID) عیناً ذخیره می‌شود تا شناسه نقشه = شناسه جدول باشد (بند ۱۶).
2. **هندسه:** `coord_original` همیشه حفظ می‌شود؛ `coord_snapped` مشتق است؛ هیچ موجودیتی «بی‌دلیل» حذف نمی‌شود (فقط flag `excluded_with_issue`).
3. **واحدها:** در همه فیلدهای کمّی suffix واحد الزامی است در نام ستون (`_kw`, `_kva`, `_m`, `_min`, `_hours`, `_rials`)؛ واحد انرژی توزیع‌نشده خاموشی تا تأیید A-08 با واحد خام ذخیره و برچسب `unit_unconfirmed` می‌گیرد.
4. **سیاست‌های مقرره‌ای:** وزن‌های جدول ۱۲/۱۶، آستانه ۳۰ دقیقه و inverse_zero در `StudyProject.settings_json` ذخیره می‌شوند؛ هر تغییر با (کاربر، تاریخ، مقدار قبل، مقدار جدید) ثبت می‌گردد.
5. **نامحدودبودن NULL:** فیلد مفقود ≠ مقدار صفر؛ صفر فقط داده واقعی است.

## ۵. نگاشت فیلدهای واقعی GIS (منشأ: Sample خلخال + config.json GeoGrid 4.2.0 — ثبت منشأ طبق بند ۵)

| مفهوم SwitchLoc | فیلد مشاهده‌شده | لایه‌ها | یادداشت |
|---|---|---|---|
| شناسه عارضه | `T_MapID`, `OBJECTID`, `GlobalID` | همه | fallback به ترتیب ذکر |
| نام فیدر | `Feeder` → `T_FeederNa` → `T_feader` → `T_name_fdr` | همه | زنجیره fallback |
| وضعیت سرویس | `T__outserv` | همه | «خارج از مدار/1/true»→out؛ خالی/«در مدار»→in |
| کنترل از راه دور | `T_ctrl_otm` (بلي/خير) | ELWDCS | remote_controlled |
| جنس/سطح مقطع خط | `T_jns_hadi`, `T_cod_sath`, `T_typ_shab` | خطوط | |
| طول | `Shape_STLe`, `T_FeatureL` | خطوط | مقایسه دو مقدار → Issue |
| ظرفیت ترانس | `T_strn` | ELWDTR | |
| جریان نامی فیوز/کلید | `T_jar_nami`, `T_jar_etsl` | ELWFCT/ELWDCS/ELWCBR | 0 = نامشخص → Issue |
| ظرفیت حرارتی بریکر | `T_jar_nami` (630) | ELWCBR | |
| تنظیمات ریکلوزر | `T_max_jrn_`, `T_tedad_gh`, `T_Tnzm_t*` | ELWREC | |
| نام محلی/سمت | `T_nam_ght`, `T_lname`, `Name` | تجهیزات | برچسب نمایشی |
| نوع کلید | `T_type`, `T_noe_sec`, `T_noe_kld` | ELWDCS/ELWCBR | LBS/کندسوز/SF6/روغنی/... |
| ولتاژ نامی | `T__uknom` | تجهیزات | 0/None → وراثت از فیدر (Issue) |
