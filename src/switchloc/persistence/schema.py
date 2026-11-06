# -*- coding: utf-8 -*-
"""SQLite DDL — tables generated 1:1 from docs/DATA_MODEL.md (Phase 1).

Schema versioning (``PRAGMA user_version``)
-------------------------------------------
* ``SCHEMA_VERSION`` is the structure version this build understands.
* Version 1 is the baseline: every project created by v1.0–v1.8 (they
  carry ``user_version = 0`` and are identical in structure because new
  tables were always added with ``CREATE TABLE IF NOT EXISTS``).
* To change an existing table in a future release: bump
  ``SCHEMA_VERSION`` and add ``MIGRATIONS[<new version>] = "<SQL>"``
  (the SQL upgrades version N-1 → N).  ``ProjectStore`` backs the file
  up, applies the steps in one transaction each, and refuses to open a
  project written by a NEWER build instead of corrupting it.
"""
SCHEMA_VERSION = 2

#: target version -> SQL script upgrading (target - 1) -> target
MIGRATIONS: dict[int, str] = {
    2: "ALTER TABLE outage_lambda_r ADD COLUMN r_reducible_minutes REAL NOT NULL DEFAULT 0;",
}

SCHEMA_SQL = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS study_run (
    id              TEXT PRIMARY KEY,
    project         TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    user            TEXT NOT NULL,
    algo_version    TEXT NOT NULL,
    tav_revision    TEXT NOT NULL,
    settings_json   TEXT NOT NULL,
    input_hashes_json TEXT NOT NULL,
    summary_json    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_record (
    id          TEXT PRIMARY KEY,
    run_id      TEXT NOT NULL,
    file_path   TEXT NOT NULL,
    file_sha256 TEXT NOT NULL,
    layer       TEXT NOT NULL,
    record_ref  TEXT NOT NULL,
    geometry_ref TEXT
);

CREATE TABLE IF NOT EXISTS layer_mapping (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT NOT NULL,
    slot_key    TEXT NOT NULL,
    file_path   TEXT NOT NULL,
    layer_name  TEXT NOT NULL,
    field_map_json TEXT NOT NULL,
    enabled     INTEGER NOT NULL,
    confirmed_by TEXT NOT NULL,
    confirmed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS crs_definition (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT NOT NULL,
    layer       TEXT NOT NULL,
    crs_original TEXT NOT NULL,
    crs_analysis TEXT NOT NULL,
    epsg        INTEGER,
    transformed INTEGER NOT NULL,
    transform_note TEXT
);

CREATE TABLE IF NOT EXISTS validation_issue (
    issue_id    TEXT NOT NULL,
    run_id      TEXT NOT NULL,
    code        TEXT NOT NULL,
    severity    TEXT NOT NULL,
    message_fa  TEXT NOT NULL,
    source_file TEXT,
    layer       TEXT,
    record_id   TEXT,
    field       TEXT,
    current_value TEXT,
    suggestion_fa TEXT,
    impact_fa   TEXT,
    status      TEXT NOT NULL,
    meta_json   TEXT,
    PRIMARY KEY (run_id, issue_id)
);

CREATE TABLE IF NOT EXISTS feeder (
    id      TEXT PRIMARY KEY,
    run_id  TEXT NOT NULL,
    name    TEXT NOT NULL,
    raw_name TEXT,
    substation_hint TEXT
);

CREATE TABLE IF NOT EXISTS node (
    id      TEXT PRIMARY KEY,
    run_id  TEXT NOT NULL,
    kind    TEXT NOT NULL,
    x_orig  REAL, y_orig REAL,
    x_snap  REAL, y_snap REAL,
    feeder_name TEXT,
    cluster_key TEXT,
    excluded_with_issue INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS branch (
    id      TEXT PRIMARY KEY,
    run_id  TEXT NOT NULL,
    kind    TEXT NOT NULL,
    node_a  TEXT NOT NULL,
    node_b  TEXT NOT NULL,
    length_registered_m REAL,
    length_geometric_m REAL,
    feeder_name TEXT,
    conductor   TEXT,
    section_mm2 REAL,
    installation TEXT,
    excluded_with_issue INTEGER NOT NULL DEFAULT 0,
    source_id TEXT
);
CREATE INDEX IF NOT EXISTS ix_branch_nodes ON branch(run_id, node_a, node_b);

CREATE TABLE IF NOT EXISTS branch_segment (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id  TEXT NOT NULL,
    branch_id TEXT NOT NULL,
    seq     INTEGER NOT NULL,
    ax REAL NOT NULL, ay REAL NOT NULL,
    bx REAL NOT NULL, by REAL NOT NULL,
    length_m REAL NOT NULL,
    node_a  TEXT, node_b TEXT
);

CREATE TABLE IF NOT EXISTS switch_dev (
    id      TEXT PRIMARY KEY,
    run_id  TEXT NOT NULL,
    family  TEXT NOT NULL,
    node_id TEXT NOT NULL,
    switch_type_raw TEXT,
    normally_state TEXT,
    current_state TEXT,
    rating_a REAL,
    remote_controlled TEXT,
    local_name TEXT,
    feeder_name TEXT,
    layer   TEXT,
    source_id TEXT
);

CREATE TABLE IF NOT EXISTS transformer (
    id      TEXT PRIMARY KEY,
    run_id  TEXT NOT NULL,
    node_id TEXT NOT NULL,
    capacity_kva REAL,
    kind_raw TEXT,
    feeder_name TEXT,
    local_name TEXT,
    source_id TEXT
);

CREATE TABLE IF NOT EXISTS load_pt (
    id      TEXT PRIMARY KEY,
    run_id  TEXT NOT NULL,
    node_id TEXT NOT NULL,
    transformer_id TEXT,
    p_kw    REAL, q_kvar REAL,
    category TEXT,
    priority_weight REAL,
    data_source TEXT,
    source_id TEXT
);

CREATE TABLE IF NOT EXISTS substation (
    id      TEXT PRIMARY KEY,
    run_id  TEXT NOT NULL,
    name    TEXT NOT NULL,
    code    TEXT
);

CREATE TABLE IF NOT EXISTS tie_connection (
    id      TEXT PRIMARY KEY,
    run_id  TEXT NOT NULL,
    feeder_a TEXT NOT NULL,
    feeder_b TEXT NOT NULL,
    switch_id TEXT,
    automation_capable INTEGER NOT NULL,
    status  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings_log (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id  TEXT NOT NULL,
    key     TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT NOT NULL,
    user    TEXT NOT NULL,
    at      TEXT NOT NULL
);

-- ------------------------------------------------------------- Phase 2 ----
CREATE TABLE IF NOT EXISTS topo_run (
    id              TEXT PRIMARY KEY,
    run_id          TEXT NOT NULL,          -- originating import run
    created_at      TEXT NOT NULL,
    user            TEXT NOT NULL,
    algo_version    TEXT NOT NULL,
    settings_json   TEXT NOT NULL,
    summary_json    TEXT NOT NULL,
    verdict         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS topo_zone (
    id              TEXT PRIMARY KEY,
    topo_run_id     TEXT NOT NULL,
    feeder          TEXT NOT NULL,
    zone_no         INTEGER NOT NULL,
    kind            TEXT NOT NULL,
    source_node     TEXT,
    node_count      INTEGER NOT NULL,
    length_m        REAL NOT NULL,
    transformer_count INTEGER NOT NULL,
    load_count      INTEGER NOT NULL,
    boundary_switch_ids_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_topo_zone_run ON topo_zone(topo_run_id, feeder, zone_no);

CREATE TABLE IF NOT EXISTS topo_zone_node (
    topo_run_id     TEXT NOT NULL,
    zone_id         TEXT NOT NULL,
    node_id         TEXT NOT NULL,
    PRIMARY KEY (topo_run_id, zone_id, node_id)
);

CREATE TABLE IF NOT EXISTS topo_zone_edge (
    topo_run_id     TEXT NOT NULL,
    zone_id         TEXT NOT NULL,
    edge_id         TEXT NOT NULL,
    branch_id       TEXT NOT NULL,
    PRIMARY KEY (topo_run_id, zone_id, edge_id)
);

CREATE TABLE IF NOT EXISTS topo_boundary (
    topo_run_id     TEXT NOT NULL,
    switch_id       TEXT NOT NULL,
    node_id         TEXT NOT NULL,
    open_normal     INTEGER NOT NULL,
    branchy         INTEGER NOT NULL,
    zones_json      TEXT NOT NULL,
    PRIMARY KEY (topo_run_id, switch_id)
);

CREATE TABLE IF NOT EXISTS scenario_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    topo_run_id     TEXT NOT NULL,
    name            TEXT NOT NULL,
    note            TEXT,
    actions_json    TEXT NOT NULL,
    summary_json    TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    user            TEXT NOT NULL
);

-- ------------------------------------------------------------- Phase 3 ----
CREATE TABLE IF NOT EXISTS outage_run (
    id              TEXT PRIMARY KEY,
    created_at      TEXT NOT NULL,
    user            TEXT NOT NULL,
    algo_version    TEXT NOT NULL,
    settings_json   TEXT NOT NULL,
    summary_json    TEXT NOT NULL,
    verdict         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS outage_event (
    id              TEXT PRIMARY KEY,
    outage_run_id   TEXT NOT NULL,
    sheet           TEXT NOT NULL,
    row_ref         INTEGER NOT NULL,
    event_no        TEXT,
    substation      TEXT,
    feeder_raw      TEXT,
    feeder_key      TEXT,
    in_model        INTEGER NOT NULL DEFAULT 0,
    date_j          TEXT,
    year            INTEGER,
    month           INTEGER,
    duration_min    REAL,
    restore_delay_min REAL,
    cause_raw       TEXT,
    cause_group     TEXT,
    device_raw      TEXT,
    energy_kwh      REAL,
    trip_current_raw TEXT,
    notes           TEXT,
    outage_class    TEXT NOT NULL,
    rule_id         TEXT NOT NULL,
    review_status   TEXT NOT NULL DEFAULT 'auto'
);
CREATE INDEX IF NOT EXISTS ix_outage_event_run
    ON outage_event(outage_run_id, feeder_key, year);

CREATE TABLE IF NOT EXISTS outage_lambda_r (
    outage_run_id   TEXT NOT NULL,
    feeder_key      TEXT NOT NULL,
    feeder_raw      TEXT,
    events_total    INTEGER NOT NULL,
    events_random   INTEGER NOT NULL,
    events_planned  INTEGER NOT NULL,
    events_reducible INTEGER NOT NULL DEFAULT 0,
    years_covered   INTEGER NOT NULL,
    lambda_per_year REAL NOT NULL,
    lambda_reducible_per_year REAL NOT NULL DEFAULT 0,
    r_minutes       REAL NOT NULL,
    r_reducible_minutes REAL NOT NULL DEFAULT 0,
    r_minutes_nonzero REAL,
    energy_kwh      REAL NOT NULL,
    class_counts_json TEXT NOT NULL,
    PRIMARY KEY (outage_run_id, feeder_key)
);

-- ---------------------------------------------------------------------------
-- Phase 4 — placement & ranking (گام‌های ۴-۸)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS placement_run (
    id              TEXT PRIMARY KEY,
    created_at      TEXT NOT NULL,
    user            TEXT NOT NULL,
    algo_version    TEXT NOT NULL,
    settings_json   TEXT NOT NULL,
    summary_json    TEXT NOT NULL,
    verdict         TEXT NOT NULL,
    source_run_id   TEXT,
    topo_run_id     TEXT,
    outage_run_id   TEXT
);

CREATE TABLE IF NOT EXISTS placement_rank (
    placement_run_id TEXT NOT NULL,
    feeder_key      TEXT NOT NULL,
    rank            INTEGER NOT NULL,
    score           REAL NOT NULL,
    raw_json        TEXT NOT NULL,
    norm_json       TEXT NOT NULL,
    weighted_json   TEXT NOT NULL,
    ties_count      INTEGER,
    ep_percent      REAL,
    tl_percent      REAL,
    load_priority_sum REAL,
    lambda_per_year REAL,
    lambda_reducible REAL,
    r_minutes       REAL,
    PRIMARY KEY (placement_run_id, feeder_key)
);

CREATE TABLE IF NOT EXISTS placement_eptl (
    placement_run_id TEXT NOT NULL,
    feeder_key      TEXT NOT NULL,
    ep_percent      REAL NOT NULL,
    tl_percent      REAL NOT NULL,
    worst_zone      TEXT,
    total_load_kw   REAL,
    zone_count      INTEGER,
    PRIMARY KEY (placement_run_id, feeder_key)
);

CREATE TABLE IF NOT EXISTS placement_scheme (
    placement_run_id TEXT NOT NULL,
    scheme_id       TEXT NOT NULL,
    kind            TEXT NOT NULL,
    feeders_json    TEXT NOT NULL,
    switches_json   TEXT NOT NULL,
    relations_json  TEXT NOT NULL,
    note            TEXT,
    extra_json      TEXT,
    PRIMARY KEY (placement_run_id, scheme_id)
);

CREATE TABLE IF NOT EXISTS placement_compare (
    placement_run_id TEXT NOT NULL,
    scheme_id       TEXT NOT NULL,
    kind            TEXT NOT NULL,
    feeders_json    TEXT NOT NULL,
    n_switches      INTEGER NOT NULL,
    e2_before_kwh   REAL NOT NULL,
    e1_after_kwh    REAL NOT NULL,
    ce_rials        REAL NOT NULL,
    cn_rials        REAL NOT NULL,
    ce_over_cn      REAL,
    selected        INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (placement_run_id, scheme_id)
);

-- ---------------------------------------------------------------------------
-- نیاز ۹ — ظرفیت فیدرها (نامی/پیک/اضطراری + منشأ هر مقدار)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS feeder_capacity (
    feeder_key      TEXT PRIMARY KEY,
    nominal_kw      REAL,
    peak_kw         REAL,
    emergency_kw    REAL,
    nominal_source  TEXT NOT NULL DEFAULT 'unknown',
    peak_source     TEXT NOT NULL DEFAULT 'unknown',
    emergency_source TEXT NOT NULL DEFAULT 'unknown',
    note            TEXT,
    updated_at      TEXT NOT NULL,
    updated_by      TEXT NOT NULL
);

-- ---------------------------------------------------------------------------
-- نیاز ۱۲ — گردش کار مطالعات: بازبینی کاندیدهای NO و تأیید طرح‌ها
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tie_review (
    tie_id          TEXT NOT NULL,
    node            TEXT,
    feeder_a        TEXT,
    feeder_b        TEXT,
    switch_id       TEXT,
    status          TEXT NOT NULL DEFAULT 'proposed',   -- proposed|confirmed|rejected
    note            TEXT,
    updated_at      TEXT NOT NULL,
    updated_by      TEXT NOT NULL,
    PRIMARY KEY (tie_id)
);

CREATE TABLE IF NOT EXISTS plan_review (
    feeder_key      TEXT NOT NULL,
    placement_run_id TEXT,
    scheme_id       TEXT,
    status          TEXT NOT NULL,            -- accepted|needs_capacity|no_justification|approved|rejected
    reasons_json    TEXT,
    updated_at      TEXT NOT NULL,
    updated_by      TEXT NOT NULL,
    PRIMARY KEY (feeder_key)
);

-- ---------------------------------------------------------------------------
-- تنظیمات نمایشی/عمومی پروژه — چند استایل نقشه (MapStyle) + نام گزارش + …
-- (درخواست کاربر: تعریف چند استایل و ماندگاری تنظیمات پس از بستن پروژه)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS project_kv (
    key             TEXT PRIMARY KEY,
    value_json      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    updated_by      TEXT NOT NULL
);
"""
