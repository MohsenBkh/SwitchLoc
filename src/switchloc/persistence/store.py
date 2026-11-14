# -*- coding: utf-8 -*-
"""SQLite project store (main prompt §۱۶ — ذخیره/بازگشایی + بازتولیدپذیری).

Save/load is deterministic: entities are written in sorted-id order, so
two identical imports produce byte-identical databases (regression
test test_persistence.py).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ..domain.entities import (Branch, CanonicalNetwork, CRSDefinition,
                               LayerMapping, LineSegment, Node, SourceRecord,
                               StudyRunMeta, Substation, SwitchDev, Transformer,
                               LoadPt)
from ..domain.ids import stable_id
from ..validation.issues import IssueLog, ValidationIssue
from ..logging_setup import get_logger
from .schema import MIGRATIONS, SCHEMA_SQL, SCHEMA_VERSION

_log = get_logger("persistence")


class SchemaTooNewError(RuntimeError):
    """The project file was written by a newer SwitchLoc build."""


def _num(v):
    return None if v is None else float(v)


class ProjectStore:
    """One SQLite file per project (D-03)."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        # one connection per thread of use: workers open their own store
        self.conn = sqlite3.connect(str(self.path), timeout=15.0)
        try:
            self._ensure_schema()
        except Exception:
            self.conn.close()
            raise

    # -- schema versioning (see persistence/schema.py) ---------------------
    def schema_version(self) -> int:
        return int(self.conn.execute("PRAGMA user_version").fetchone()[0])

    def _ensure_schema(self) -> None:
        cur = self.schema_version()
        if cur > SCHEMA_VERSION:
            raise SchemaTooNewError(
                f"Project '{self.path.name}' uses schema v{cur} but this "
                f"SwitchLoc build only understands up to v{SCHEMA_VERSION}. "
                "Update the application — opening it with this build "
                "could corrupt the project.")
        pending = [v for v in sorted(MIGRATIONS) if cur < v <= SCHEMA_VERSION]
        if pending and cur > 0 and self.path.exists() \
                and self.path.stat().st_size > 0:
            self._backup(f"v{cur}")
        # baseline tables (IF NOT EXISTS: also tops up older projects)
        self.conn.executescript(SCHEMA_SQL)
        for v in pending:
            _log.info("migrating %s: schema v%d -> v%d", self.path.name,
                      v - 1, v)
            try:
                migration_sql = MIGRATIONS[v]
                if v == 2 and "r_reducible_minutes" in migration_sql:
                    columns = {row[1] for row in self.conn.execute(
                        "PRAGMA table_info(outage_lambda_r)")}
                    if "r_reducible_minutes" in columns:
                        migration_sql = ""  # fresh DB already has the column
                self.conn.executescript(
                    "BEGIN;\n" + migration_sql
                    + f"\nPRAGMA user_version = {int(v)};\nCOMMIT;")
            except Exception:
                self.conn.rollback()
                raise
        if self.schema_version() < SCHEMA_VERSION:
            self.conn.execute(f"PRAGMA user_version = {int(SCHEMA_VERSION)}")
        self.conn.commit()

    def _backup(self, tag: str) -> None:
        """Copy the project next to itself before a destructive upgrade."""
        import shutil
        try:
            self.conn.commit()
            dst = self.path.with_name(f"{self.path.stem}.pre-migration-{tag}"
                                      f"{self.path.suffix}")
            if not dst.exists():
                shutil.copy2(self.path, dst)
        except OSError as exc:
            _log.warning("could not back up %s: %s", self.path, exc)

    def close(self):
        self.conn.commit()
        self.conn.close()

    # ------------------------------------------------------------------
    def save_network(self, net: CanonicalNetwork, issues: IssueLog,
                     run: StudyRunMeta) -> str:
        run_id = run.algo_version + "-" + run.started_at.replace(":", "").replace("-", "")
        import uuid as _u
        run_id = _u.uuid5(_u.NAMESPACE_URL, run_id + "|" + net.project_name +
                          "|" + json.dumps(run.input_hashes, sort_keys=True))
        run_id = str(run_id)
        c = self.conn
        c.execute(
            "INSERT INTO study_run VALUES (?,?,?,?,?,?,?,?,?)",
            (run_id, run.project_name, run.started_at, run.user, run.algo_version,
             run.tav_revision, json.dumps(run.settings_snapshot, ensure_ascii=False),
             json.dumps(run.input_hashes, ensure_ascii=False),
             json.dumps(net.summary(), ensure_ascii=False, default=str)))

        # entities sorted by id → deterministic file bytes
        for src in sorted(net.source_records, key=lambda s: s.record_ref + s.layer):
            c.execute("INSERT OR IGNORE INTO source_record VALUES (?,?,?,?,?,?,?)",
                      (f"{run_id}:{src.layer}:{src.record_ref}", run_id,
                       src.file_path, src.file_sha256, src.layer, src.record_ref,
                       src.geometry_ref))
        src_id_of = {(s.layer, s.record_ref):
                     f"{run_id}:{s.layer}:{s.record_ref}"
                     for s in net.source_records}

        for ent in sorted(net.layer_mappings, key=lambda m: m.layer_name):
            c.execute("INSERT INTO layer_mapping (run_id, slot_key, file_path,"
                      " layer_name, field_map_json, enabled, confirmed_by,"
                      " confirmed_at) VALUES (?,?,?,?,?,?,?,?)",
                      (run_id, ent.slot_key, ent.file_path, ent.layer_name,
                       json.dumps(ent.field_map, ensure_ascii=False),
                       int(ent.enabled), ent.confirmed_by, ent.confirmed_at))
        for d in sorted(net.crs_definitions, key=lambda d: d.layer):
            c.execute("INSERT INTO crs_definition (run_id, layer, crs_original,"
                      " crs_analysis, epsg, transformed, transform_note)"
                      " VALUES (?,?,?,?,?,?,?)",
                      (run_id, d.layer, d.crs_original, d.crs_analysis,
                       d.epsg, int(d.transformed), d.transform_note))

        for fd in sorted(net.feeders, key=lambda f: f.name):
            c.execute("INSERT OR IGNORE INTO feeder VALUES (?,?,?,?,?)",
                      (fd.id, run_id, fd.name, fd.raw_name, fd.substation_hint))
        for st in sorted(net.substations, key=lambda s: s.name):
            c.execute("INSERT OR IGNORE INTO substation VALUES (?,?,?,?)",
                      (st.id, run_id, st.name, st.code))
        for nd in sorted(net.nodes, key=lambda n: n.id):
            xo, yo = (nd.coord_original or (None, None))[:2] if nd.coord_original else (None, None)
            xs, ys = (nd.coord_snapped or (None, None))[:2] if nd.coord_snapped else (None, None)
            c.execute("INSERT OR IGNORE INTO node VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (nd.id, run_id, nd.kind.value, _num(xo), _num(yo),
                       _num(xs), _num(ys), nd.feeder_name, nd.cluster_key,
                       int(nd.excluded_with_issue)))
        for br in sorted(net.branches, key=lambda b: b.id):
            c.execute("INSERT OR REPLACE INTO branch VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (br.id, run_id, br.kind.value, br.node_a or "", br.node_b or "",
                       _num(br.length_registered_m), _num(br.length_geometric_m),
                       br.feeder_name, br.conductor,
                       _num(br.section_mm2), br.installation,
                       int(br.excluded_with_issue),
                       src_id_of.get((br.source.layer, br.source.record_ref))
                       if br.source else None))
            for seq, seg in enumerate(br.segments):
                c.execute("INSERT INTO branch_segment (run_id, branch_id, seq,"
                          " ax, ay, bx, by, length_m, node_a, node_b)"
                          " VALUES (?,?,?,?,?,?,?,?,?,?)",
                          (run_id, br.id, seq, seg.a[0], seg.a[1],
                           seg.b[0], seg.b[1], seg.length_m, "", ""))
        for sw in sorted(net.switches, key=lambda s: s.id):
            c.execute("INSERT OR REPLACE INTO switch_dev VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (sw.id, run_id, sw.family.value, sw.node_id,
                       sw.switch_type_raw, sw.normally_state,
                       sw.current_state.value, _num(sw.rating_a),
                       sw.remote_controlled.value, sw.local_name,
                       sw.feeder_name, sw.layer,
                       src_id_of.get((sw.source.layer, sw.source.record_ref))
                       if sw.source else None))
        for tr in sorted(net.transformers, key=lambda t: t.id):
            c.execute("INSERT OR REPLACE INTO transformer VALUES (?,?,?,?,?,?,?,?)",
                      (tr.id, run_id, tr.node_id, _num(tr.capacity_kva),
                       tr.kind_raw, tr.feeder_name, tr.local_name,
                       src_id_of.get((tr.source.layer, tr.source.record_ref))
                       if tr.source else None))
        for ld in sorted(net.loads, key=lambda l: l.id):
            c.execute("INSERT OR REPLACE INTO load_pt VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (ld.id, run_id, ld.node_id, ld.transformer_id,
                       _num(ld.p_kw), _num(ld.q_kvar), ld.category,
                       _num(ld.priority_weight), ld.data_source,
                       src_id_of.get((ld.source.layer, ld.source.record_ref))
                       if ld.source else None))
        for isu in issues.items():
            c.execute("INSERT OR REPLACE INTO validation_issue VALUES "
                      "(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (isu.meta.get("issue_id", ""), run_id, isu.code,
                       isu.severity, isu.message_fa, isu.source_file, isu.layer,
                       isu.record_id, isu.field, isu.current_value,
                       isu.suggestion_fa, isu.impact_fa, isu.status,
                       json.dumps(isu.meta, ensure_ascii=False, default=str)))
        self.conn.commit()
        return run_id

    # ------------------------------------------------------------------
    def load_network(self, run_id: str | None = None):
        """Rebuild a CanonicalNetwork + issues from the newest/selected run."""
        cur = self.conn
        if run_id is None:
            row = cur.execute(
                "SELECT id FROM study_run ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
            run_id = row[0] if row else None
            if run_id is None:
                raise ValueError("پروژه حاوی هیچ اجرایی نیست.")
        net = CanonicalNetwork()
        issues = IssueLog()
        for (layer, ref, fp, sha, geo) in cur.execute(
                "SELECT layer, record_ref, file_path, file_sha256, geometry_ref"
                " FROM source_record WHERE run_id=?", (run_id,)):
            net.source_records.append(SourceRecord(fp, sha, layer, ref, geo or ""))
        for r in cur.execute("SELECT slot_key, file_path, layer_name,"
                             " field_map_json, enabled, confirmed_by, confirmed_at"
                             " FROM layer_mapping WHERE run_id=?", (run_id,)):
            net.layer_mappings.append(LayerMapping(
                r[0], r[1], r[2], json.loads(r[3]), bool(r[4]), r[5], r[6]))
        for r in cur.execute("SELECT layer, crs_original, crs_analysis, epsg,"
                             " transformed, transform_note FROM crs_definition"
                             " WHERE run_id=?", (run_id,)):
            net.crs_definitions.append(CRSDefinition(r[0], r[1], r[2], r[3],
                                                     bool(r[4]), r[5] or ""))
        for r in cur.execute("SELECT id, kind, x_orig, y_orig, x_snap, y_snap,"
                             " feeder_name, cluster_key, excluded_with_issue"
                             " FROM node WHERE run_id=?", (run_id,)):
            co = (r[2], r[3]) if r[2] is not None else None
            cs = (r[4], r[5]) if r[4] is not None else None
            net.nodes.append(Node(kind=__import__("switchloc.domain.enums",
                                                  fromlist=["NodeKind"]).NodeKind(r[1]),
                                  coord_original=co, coord_snapped=cs,
                                  feeder_name=r[6] or "", cluster_key=r[7] or "",
                                  excluded_with_issue=bool(r[8])))
            net.nodes[-1].id = r[0]
        for r in cur.execute("SELECT id, kind, node_a, node_b, length_registered_m,"
                             " length_geometric_m, feeder_name, conductor,"
                             " section_mm2, installation, excluded_with_issue"
                             " FROM branch WHERE run_id=?", (run_id,)):
            br = Branch(kind=__import__("switchloc.domain.enums",
                                        fromlist=["BranchKind"]).BranchKind(r[1]),
                        node_a=r[2], node_b=r[3], length_registered_m=r[4],
                        length_geometric_m=r[5] or 0.0, segments=[],
                        feeder_name=r[6] or "", conductor=r[7] or "",
                        section_mm2=r[8], installation=r[9] or "",
                        excluded_with_issue=bool(r[10]))
            br.id = r[0]
            net.branches.append(br)
        # branch segments are REQUIRED by the Phase-2 graph (edge splitting
        # at device vertices); loaded in deterministic (branch, seq) order.
        segs_by_branch: dict[str, list] = {}
        for (bid, seq, ax, ay, bx, by, lm) in cur.execute(
                "SELECT branch_id, seq, ax, ay, bx, by, length_m"
                " FROM branch_segment WHERE run_id=? ORDER BY branch_id, seq",
                (run_id,)):
            segs_by_branch.setdefault(bid, []).append(
                LineSegment(a=(ax, ay), b=(bx, by), length_m=lm or 0.0))
        for br in net.branches:
            br.segments = segs_by_branch.get(br.id, [])
        for r in cur.execute("SELECT id, family, node_id, switch_type_raw,"
                             " normally_state, current_state, rating_a,"
                             " remote_controlled, local_name, feeder_name, layer"
                             " FROM switch_dev WHERE run_id=?", (run_id,)):
            E = __import__("switchloc.domain.enums", fromlist=[
                "SwitchFamily", "SwitchState", "YesNoUnknown"])
            sw = SwitchDev(family=E.SwitchFamily(r[1]), node_id=r[2],
                           switch_type_raw=r[3] or "", normally_state=r[4] or "",
                           current_state=E.SwitchState(r[5]), rating_a=r[6],
                           remote_controlled=E.YesNoUnknown(r[7]),
                           local_name=r[8] or "", feeder_name=r[9] or "",
                           layer=r[10] or "")
            sw.id = r[0]
            net.switches.append(sw)
        for r in cur.execute("SELECT id, node_id, capacity_kva, kind_raw,"
                             " feeder_name, local_name FROM transformer"
                             " WHERE run_id=?", (run_id,)):
            tr = Transformer(node_id=r[1], capacity_kva=r[2], kind_raw=r[3] or "",
                             feeder_name=r[4] or "", local_name=r[5] or "")
            tr.id = r[0]
            net.transformers.append(tr)
        for r in cur.execute("SELECT id, node_id, transformer_id, p_kw, q_kvar,"
                             " category, priority_weight, data_source"
                             " FROM load_pt WHERE run_id=?", (run_id,)):
            ld = LoadPt(node_id=r[1], transformer_id=r[2], p_kw=r[3], q_kvar=r[4],
                        category=r[5] or "", priority_weight=r[6],
                        data_source=r[7] or "unassigned")
            ld.id = r[0]
            net.loads.append(ld)
        for r in cur.execute("SELECT id, name, raw_name, substation_hint"
                             " FROM feeder WHERE run_id=?", (run_id,)):
            from ..domain.entities import Feeder
            fd = Feeder(name=r[1], raw_name=r[2] or "", substation_hint=r[3] or "")
            fd.id = r[0]
            net.feeders.append(fd)
        for r in cur.execute("SELECT id, name, code FROM substation WHERE run_id=?",
                             (run_id,)):
            net.substations.append(Substation(r[1], r[2] or ""))
        for r in cur.execute("SELECT issue_id, code, severity, message_fa,"
                             " source_file, layer, record_id, field,"
                             " current_value, suggestion_fa, impact_fa, status,"
                             " meta_json FROM validation_issue WHERE run_id=?",
                             (run_id,)):
            isu = ValidationIssue(
                code=r[1], severity=r[2], message_fa=r[3],
                source_file=r[4] or "", layer=r[5] or "", record_id=r[6] or "",
                field=r[7] or "", current_value=r[8] or "",
                suggestion_fa=r[9] or "", impact_fa=r[10] or "", status=r[11],
                meta=json.loads(r[12]) if r[12] else {})
            isu.meta["issue_id"] = r[0]
            issues.add(isu)
        return net, issues

    def runs(self) -> list[dict]:
        out = []
        for r in self.conn.execute(
                "SELECT id, project, started_at, user, algo_version FROM"
                " study_run ORDER BY started_at"):
            out.append(dict(zip(("id", "project", "started_at", "user",
                                 "algo_version"), r)))
        return out

    # ------------------------------------------------------------------
    # Phase 2 — topology persistence
    # ------------------------------------------------------------------
    def save_topology(self, source_run_id: str, zones: list,
                      zone_of_edge: dict, zone_of_node: dict,
                      boundaries: list, traces: list, ties: list,
                      settings: dict, user: str, algo_version: str,
                      summary: dict, verdict: str,
                      scenarios: list | None = None) -> str:
        """Persist one topology execution (zones, boundaries, ties, traces).

        Deterministic id: identical inputs/settings → identical topo_run_id
        → identical database bytes (regression-test guarantee).
        """
        import json as _json
        settings_json = _json.dumps(settings, ensure_ascii=False, sort_keys=True)
        topo_run_id = str(stable_id("topo_run", source_run_id, algo_version,
                                    settings_json))
        created_at = self._now()
        c = self.conn
        c.execute("INSERT OR REPLACE INTO topo_run VALUES (?,?,?,?,?,?,?,?)",
                  (topo_run_id, source_run_id, created_at, user, algo_version,
                   settings_json,
                   _json.dumps(summary, ensure_ascii=False, default=str),
                   verdict))

        boundary_of_switch = {b.switch_id: b for b in boundaries}
        for z in sorted(zones, key=lambda z: (z.feeder, z.kind != "head",
                                              z.zone_no)):
            bs = sorted(sid for sid, b in boundary_of_switch.items()
                        if z.id in b.zones)
            c.execute("INSERT OR REPLACE INTO topo_zone VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                      (z.id, topo_run_id, z.feeder, z.zone_no, z.kind,
                       z.source_node, len(z.nodes), float(z.length_m),
                       len(z.transformer_ids), len(z.load_ids),
                       _json.dumps(bs, ensure_ascii=False)))
            for nid in sorted(z.nodes):
                c.execute("INSERT OR REPLACE INTO topo_zone_node VALUES (?,?,?)",
                          (topo_run_id, z.id, nid))
            for eid in sorted(z.edges):
                br_id = eid.rsplit("#", 1)[0]
                c.execute("INSERT OR REPLACE INTO topo_zone_edge VALUES (?,?,?,?)",
                          (topo_run_id, z.id, eid, br_id))
        for b in sorted(boundaries, key=lambda b: b.switch_id):
            c.execute("INSERT OR REPLACE INTO topo_boundary VALUES (?,?,?,?,?,?)",
                      (topo_run_id, b.switch_id, b.node, int(b.open_normal),
                       int(b.branchy),
                       _json.dumps(sorted(b.zones), ensure_ascii=False)))
        for t in ties:
            c.execute("INSERT OR REPLACE INTO tie_connection VALUES (?,?,?,?,?,?,?)",
                      (t.id, source_run_id, t.feeder_a, t.feeder_b,
                       t.switch_id, int(t.automation_capable), t.status))
        for sc in (scenarios or []):
            c.execute("INSERT INTO scenario_log (topo_run_id, name, note,"
                      " actions_json, summary_json, created_at, user)"
                      " VALUES (?,?,?,?,?,?,?)",
                      (topo_run_id, sc["name"], sc.get("note", ""),
                       _json.dumps(sc.get("actions", []), ensure_ascii=False),
                       _json.dumps(sc.get("summary", {}), ensure_ascii=False),
                       created_at, user))
        self.conn.commit()
        return topo_run_id

    def list_topo_runs(self) -> list[dict]:
        out = []
        for r in self.conn.execute(
                "SELECT id, run_id, created_at, user, algo_version, verdict"
                " FROM topo_run ORDER BY created_at"):
            out.append(dict(zip(("id", "run_id", "created_at", "user",
                                 "algo_version", "verdict"), r)))
        return out

    # ------------------------------------------------------------------
    # Phase 3 — outage / reliability persistence
    # ------------------------------------------------------------------
    def save_outages(self, records: list, lam: list, settings: dict,
                     user: str, algo_version: str, summary: dict,
                     verdict: str, input_file: str = "",
                     input_sha256: str = "") -> str:
        """Persist one outage-analysis execution (events + λ/r matrix).

        Deterministic id: identical inputs/settings → identical
        outage_run_id (same reproducibility guarantee as save_topology).
        """
        import json as _json
        settings_json = _json.dumps(
            {**settings, "input_file": input_file,
             "input_sha256": input_sha256},
            ensure_ascii=False, sort_keys=True)
        outage_run_id = str(stable_id("outage_run", algo_version,
                                      settings_json,
                                      tuple(sorted(r.id for r in records))))
        created_at = self._now()
        c = self.conn
        c.execute("INSERT OR REPLACE INTO outage_run VALUES (?,?,?,?,?,?,?)",
                  (outage_run_id, created_at, user, algo_version,
                   settings_json,
                   _json.dumps(summary, ensure_ascii=False, default=str),
                   verdict))
        for r in sorted(records, key=lambda x: (x.sheet, x.row_ref)):
            c.execute(
                "INSERT OR REPLACE INTO outage_event VALUES "
                "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (r.id, outage_run_id, r.sheet, r.row_ref, r.event_no,
                 r.substation, r.feeder_raw, r.feeder_key or None,
                 int(r.in_model), r.date_j or None, r.year, r.month,
                 r.duration_min, r.restore_delay_min, r.cause_raw,
                 r.cause_group or None, r.device_raw, r.energy_kwh,
                 r.trip_current_raw or None, r.notes or None,
                 r.outage_class, r.rule_id, r.review_status))
        for f in lam:
            c.execute(
                "INSERT OR REPLACE INTO outage_lambda_r VALUES "
                "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (outage_run_id, f.feeder_key, f.feeder_raw, f.events_total,
                 f.events_random, f.events_planned, f.events_reducible,
                 f.years_covered, f.lambda_per_year,
                 f.lambda_reducible_per_year, f.r_minutes,
                 getattr(f, "r_reducible_minutes", 0.0),
                 f.r_minutes_nonzero, f.energy_kwh,
                 _json.dumps(f.class_counts or {}, ensure_ascii=False)))
        self.conn.commit()
        return outage_run_id

    def list_outage_runs(self) -> list[dict]:
        out = []
        for r in self.conn.execute(
                "SELECT id, created_at, user, algo_version, verdict"
                " FROM outage_run ORDER BY created_at"):
            out.append(dict(zip(("id", "created_at", "user", "algo_version",
                                 "verdict"), r)))
        return out

    def load_outages(self, outage_run_id: str | None = None) -> dict:
        """Reload a persisted outage execution as plain dicts (UI/report)."""
        import json as _json
        if outage_run_id is None:
            row = self.conn.execute(
                "SELECT id FROM outage_run ORDER BY created_at DESC, rowid DESC LIMIT 1"
            ).fetchone()
            if row is None:
                raise ValueError("هیچ اجرای تحلیل خاموشی ذخیره نشده است.")
            outage_run_id = row[0]
        head = self.conn.execute(
            "SELECT id, created_at, user, algo_version, settings_json,"
            " summary_json, verdict FROM outage_run WHERE id=?",
            (outage_run_id,)).fetchone()
        if head is None:
            raise ValueError(f"outage_run یافت نشد: {outage_run_id}")
        events = [dict(zip(
            ("id", "sheet", "row_ref", "event_no", "substation",
             "feeder_raw", "feeder_key", "in_model", "date_j", "year",
             "month", "duration_min", "restore_delay_min", "cause_raw",
             "cause_group", "device_raw", "energy_kwh", "trip_current_raw",
             "notes", "outage_class", "rule_id", "review_status"), r))
            for r in self.conn.execute(
                "SELECT id, sheet, row_ref, event_no, substation,"
                " feeder_raw, feeder_key, in_model, date_j, year, month,"
                " duration_min, restore_delay_min, cause_raw, cause_group,"
                " device_raw, energy_kwh, trip_current_raw, notes,"
                " outage_class, rule_id, review_status FROM outage_event"
                " WHERE outage_run_id=? ORDER BY sheet, row_ref",
                (outage_run_id,))]
        lam = [dict(zip(
            ("feeder_key", "feeder_raw", "events_total", "events_random",
             "events_planned", "events_reducible", "years_covered",
             "lambda_per_year", "lambda_reducible_per_year", "r_minutes",
             "r_reducible_minutes", "r_minutes_nonzero", "energy_kwh", "class_counts"),
            (r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9],
             r[10], r[11], r[12], _json.loads(r[13]))))
            for r in self.conn.execute(
                "SELECT feeder_key, feeder_raw, events_total, events_random,"
                " events_planned, events_reducible, years_covered,"
                " lambda_per_year, lambda_reducible_per_year, r_minutes,"
                " r_reducible_minutes, r_minutes_nonzero, energy_kwh, class_counts_json"
                " FROM outage_lambda_r WHERE outage_run_id=?"
                " ORDER BY feeder_key", (outage_run_id,))]
        return {
            "outage_run_id": head[0], "created_at": head[1], "user": head[2],
            "algo_version": head[3], "settings": _json.loads(head[4]),
            "summary": _json.loads(head[5]), "verdict": head[6],
            "events": events, "lambda_r": lam,
        }

    def load_topology(self, topo_run_id: str | None = None) -> dict:
        """Reload a persisted topology execution as plain dicts (UI/report)."""
        if topo_run_id is None:
            row = self.conn.execute(
                "SELECT id FROM topo_run ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            if row is None:
                raise ValueError("هیچ اجرای توپولوژی ذخیره نشده است.")
            topo_run_id = row[0]
        head = self.conn.execute(
            "SELECT id, run_id, created_at, user, algo_version, settings_json,"
            " summary_json, verdict FROM topo_run WHERE id=?",
            (topo_run_id,)).fetchone()
        if head is None:
            raise ValueError(f"topo_run یافت نشد: {topo_run_id}")
        import json as _json
        zones = [dict(zip(("id", "feeder", "zone_no", "kind", "source_node",
                           "node_count", "length_m", "transformer_count",
                           "load_count", "boundary_switch_ids"),
                          (r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7],
                           r[8], _json.loads(r[9]))))
                 for r in self.conn.execute(
                     "SELECT id, feeder, zone_no, kind, source_node,"
                     " node_count, length_m, transformer_count, load_count,"
                     " boundary_switch_ids_json FROM topo_zone"
                     " WHERE topo_run_id=? ORDER BY feeder, zone_no",
                     (topo_run_id,))]
        boundaries = [dict(zip(("switch_id", "node_id", "open_normal",
                                "branchy", "zones"),
                               (r[0], r[1], bool(r[2]), bool(r[3]),
                                _json.loads(r[4]))))
                      for r in self.conn.execute(
                          "SELECT switch_id, node_id, open_normal, branchy,"
                          " zones_json FROM topo_boundary WHERE topo_run_id=?"
                          " ORDER BY switch_id", (topo_run_id,))]
        ties = [dict(zip(("id", "feeder_a", "feeder_b", "switch_id",
                          "automation_capable", "status"), r))
                for r in self.conn.execute(
                    "SELECT id, feeder_a, feeder_b, switch_id,"
                    " automation_capable, status FROM tie_connection"
                    " WHERE run_id=? ORDER BY feeder_a, feeder_b",
                    (head[1],))]
        return {
            "topo_run_id": head[0], "run_id": head[1],
            "created_at": head[2], "user": head[3], "algo_version": head[4],
            "settings": _json.loads(head[5]),
            "summary": _json.loads(head[6]), "verdict": head[7],
            "zones": zones, "boundaries": boundaries, "ties": ties,
        }

    # ------------------------------------------------------------------
    # Phase 4 — placement & ranking
    # ------------------------------------------------------------------
    def save_placement(self, snapshot: dict, settings: dict, user: str,
                       algo_version: str, source_run_id: str | None = None,
                       topo_run_id: str | None = None,
                       outage_run_id: str | None = None) -> str:
        """Persist one placement execution (فاز ۴) — deterministic id.

        ``snapshot`` is the JSON-safe dict of
        ``PlacementResult.to_dict()``; identical inputs → identical
        placement_run_id → identical database bytes.
        """
        import json as _json
        settings_json = _json.dumps(settings, ensure_ascii=False,
                                    sort_keys=True)
        summary_json = _json.dumps(
            {k: v for k, v in snapshot.items()
             if k in ("ranking", "table14_eptl", "table15_rows",
                      "zone_register", "table18_comparison",
                      "recommendation", "ens_before_kwh", "load_model")},
            ensure_ascii=False, sort_keys=True, default=str)
        placement_run_id = str(stable_id("placement_run", source_run_id or "",
                                         algo_version, settings_json,
                                         summary_json))
        severities = {str(i.get("severity", "")).lower()
                      for i in snapshot.get("issues", [])}
        verdict = ("FAIL" if "error" in severities else
                   "CONDITIONAL" if "warning" in severities else "PASS")
        created_at = self._now()
        c = self.conn
        c.execute(
            "INSERT OR REPLACE INTO placement_run VALUES (?,?,?,?,?,?,?,?,?,?)",
            (placement_run_id, created_at, user, algo_version, settings_json,
             summary_json, verdict, source_run_id, topo_run_id,
             outage_run_id))
        for r in snapshot.get("ranking", []):
            c.execute(
                "INSERT OR REPLACE INTO placement_rank VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (placement_run_id, r["feeder_key"], r["rank"], r["score"],
                 _json.dumps(r["raw"]), _json.dumps(r["norm"]),
                 _json.dumps(r["weighted"]), r["ties_count"],
                 r["ep_percent"], r["tl_percent"], r["load_priority_sum"],
                 r["lambda_per_year"], r["lambda_reducible"], r["r_minutes"]))
        for r in snapshot.get("table14_eptl", []):
            c.execute(
                "INSERT OR REPLACE INTO placement_eptl VALUES (?,?,?,?,?,?,?)",
                (placement_run_id, r["feeder_key"], r["ep_percent"],
                 r["tl_percent"], r["worst_zone"], r["total_load_kw"],
                 r["zone_count"]))
        for s in snapshot.get("schemes", []):
            c.execute(
                "INSERT OR REPLACE INTO placement_scheme VALUES (?,?,?,?,?,?,?,?)",
                (placement_run_id, s["id"], s["kind"],
                 _json.dumps(s["feeders"]),
                 _json.dumps(s["switches"], ensure_ascii=False),
                 _json.dumps(s["relations"], ensure_ascii=False),
                 s["note"], _json.dumps(s.get("extra", {}),
                                        ensure_ascii=False, default=str)))
        for r in snapshot.get("table18_comparison", []):
            c.execute(
                "INSERT OR REPLACE INTO placement_compare VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (placement_run_id, r["scheme_id"], r["kind"],
                 _json.dumps(r["feeders"]), r["n_switches"],
                 r["e2_before_kwh"], r["e1_after_kwh"], r["ce_rials"],
                 r["cn_rials"], r["ce_over_cn"], int(r["selected"])))
        self.conn.commit()
        return placement_run_id

    def list_placement_runs(self) -> list[dict]:
        out = []
        for r in self.conn.execute(
                "SELECT id, created_at, user, algo_version, verdict,"
                " source_run_id, topo_run_id, outage_run_id FROM placement_run"
                " ORDER BY created_at DESC"):
            out.append(dict(zip(
                ("placement_run_id", "created_at", "user", "algo_version",
                 "verdict", "source_run_id", "topo_run_id", "outage_run_id"),
                r)))
        return out

    def load_placement(self, placement_run_id: str | None = None) -> dict:
        """Reload a persisted placement execution as plain dicts (UI)."""
        import json as _json
        if placement_run_id is None:
            row = self.conn.execute(
                "SELECT id FROM placement_run ORDER BY created_at DESC"
                " LIMIT 1").fetchone()
            if row is None:
                raise ValueError("هیچ اجرای جایابی ذخیره نشده است.")
            placement_run_id = row[0]
        head = self.conn.execute(
            "SELECT id, created_at, user, algo_version, settings_json,"
            " summary_json, verdict, source_run_id, topo_run_id,"
            " outage_run_id FROM placement_run WHERE id=?",
            (placement_run_id,)).fetchone()
        if head is None:
            raise ValueError(f"placement_run یافت نشد: {placement_run_id}")
        ranking = [dict(zip(
            ("feeder_key", "rank", "score", "raw", "norm", "weighted",
             "ties_count", "ep_percent", "tl_percent", "load_priority_sum",
             "lambda_per_year", "lambda_reducible", "r_minutes"), r))
            for r in self.conn.execute(
                "SELECT feeder_key, rank, score, raw_json, norm_json,"
                " weighted_json, ties_count, ep_percent, tl_percent,"
                " load_priority_sum, lambda_per_year, lambda_reducible,"
                " r_minutes FROM placement_rank WHERE placement_run_id=?"
                " ORDER BY rank", (placement_run_id,))]
        for row in ranking:
            for k in ("raw", "norm", "weighted"):
                row[k] = _json.loads(row[k])
        eptl = [dict(zip(
            ("feeder_key", "ep_percent", "tl_percent", "worst_zone",
             "total_load_kw", "zone_count"), r))
            for r in self.conn.execute(
                "SELECT feeder_key, ep_percent, tl_percent, worst_zone,"
                " total_load_kw, zone_count FROM placement_eptl"
                " WHERE placement_run_id=? ORDER BY feeder_key",
                (placement_run_id,))]
        schemes = [dict(zip(
            ("scheme_id", "kind", "feeders", "switches", "relations",
             "note", "extra"), r))
            for r in self.conn.execute(
                "SELECT scheme_id, kind, feeders_json, switches_json,"
                " relations_json, note, extra_json FROM placement_scheme"
                " WHERE placement_run_id=? ORDER BY scheme_id",
                (placement_run_id,))]
        for s in schemes:
            for k in ("feeders", "switches", "relations", "extra"):
                s[k] = _json.loads(s[k])
        comparison = [dict(zip(
            ("scheme_id", "kind", "feeders", "n_switches", "e2_before_kwh",
             "e1_after_kwh", "ce_rials", "cn_rials", "ce_over_cn",
             "selected"), r))
            for r in self.conn.execute(
                "SELECT scheme_id, kind, feeders_json, n_switches,"
                " e2_before_kwh, e1_after_kwh, ce_rials, cn_rials,"
                " ce_over_cn, selected FROM placement_compare"
                " WHERE placement_run_id=? ORDER BY ce_over_cn DESC",
                (placement_run_id,))]
        for s in comparison:
            s["feeders"] = _json.loads(s["feeders"])
            s["selected"] = bool(s["selected"])
        return {
            "placement_run_id": head[0], "created_at": head[1],
            "user": head[2], "algo_version": head[3],
            "settings": _json.loads(head[4]),
            "summary": _json.loads(head[5]), "verdict": head[6],
            "source_run_id": head[7], "topo_run_id": head[8],
            "outage_run_id": head[9],
            "ranking": ranking, "table14_eptl": eptl,
            "schemes": schemes, "table18_comparison": comparison,
        }


    def _now(self) -> str:
        from datetime import datetime as _dt
        return _dt.now().isoformat(timespec="seconds")

    def log_setting_change(self, run_id: str, key: str, old, new,
                           user: str, at: str):
        self.conn.execute(
            "INSERT INTO settings_log (run_id, key, old_value, new_value,"
            " user, at) VALUES (?,?,?,?,?,?)",
            (run_id, key, None if old is None else str(old), str(new), user, at))
        self.conn.commit()

    # ------------------------------------------------------------------
    # نیاز ۹ — feeder capacity (نامی/پیک/اضطراری + منشأ، قابل ویرایش از GUI)
    # ------------------------------------------------------------------
    def save_feeder_capacity(self, rows: list[dict], user: str = "ui-user",
                             at: str | None = None) -> int:
        """Upsert ظرفیت فیدرها؛ ``rows`` = خروجی FeederCapacity.as_dict()."""
        from datetime import datetime as _dt
        at = at or _dt.now().isoformat(timespec="seconds")
        n = 0
        for r in rows:
            fk = str(r.get("feeder_key", "")).strip().upper()
            if not fk:
                continue
            self.conn.execute(
                "INSERT INTO feeder_capacity (feeder_key, nominal_kw,"
                " peak_kw, emergency_kw, nominal_source, peak_source,"
                " emergency_source, note, updated_at, updated_by)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(feeder_key) DO UPDATE SET"
                " nominal_kw=excluded.nominal_kw, peak_kw=excluded.peak_kw,"
                " emergency_kw=excluded.emergency_kw,"
                " nominal_source=excluded.nominal_source,"
                " peak_source=excluded.peak_source,"
                " emergency_source=excluded.emergency_source,"
                " note=excluded.note, updated_at=excluded.updated_at,"
                " updated_by=excluded.updated_by",
                (fk, r.get("nominal_kw"), r.get("peak_kw"),
                 r.get("emergency_kw"),
                 r.get("nominal_source") or "unknown",
                 r.get("peak_source") or "unknown",
                 r.get("emergency_source") or "unknown",
                 r.get("note", ""), at, user))
            n += 1
        self.conn.commit()
        return n

    def load_feeder_capacity(self) -> dict:
        """feeder_key → FeederCapacity (از جدول پروژه؛ خالی = وارد نشده)."""
        from ..placement.capacity import FeederCapacity
        out: dict[str, FeederCapacity] = {}
        for r in self.conn.execute(
                "SELECT feeder_key, nominal_kw, peak_kw, emergency_kw,"
                " nominal_source, peak_source, emergency_source, note"
                " FROM feeder_capacity ORDER BY feeder_key"):
            cap = FeederCapacity(
                feeder_key=r[0], nominal_kw=r[1], peak_kw=r[2],
                emergency_kw=r[3],
                nominal_source=r[4] or "unknown",
                peak_source=r[5] or "unknown",
                emergency_source=r[6] or "unknown",
                note=r[7] or "")
            if cap.nominal_kw or cap.peak_kw or cap.emergency_kw:
                out[cap.feeder_key] = cap
        return out

    # ------------------------------------------------------------------
    # نیاز ۱۲ — گردش کار: بازبینی کاندیدهای NO + تأیید مهندسی طرح‌ها
    # ------------------------------------------------------------------
    def save_tie_review(self, rows: list[dict], user: str = "ui-user",
                        at: str | None = None) -> int:
        from datetime import datetime as _dt
        at = at or _dt.now().isoformat(timespec="seconds")
        n = 0
        for r in rows:
            tid = str(r.get("tie_id", "")).strip()
            if not tid:
                continue
            self.conn.execute(
                "INSERT INTO tie_review (tie_id, node, feeder_a, feeder_b,"
                " switch_id, status, note, updated_at, updated_by)"
                " VALUES (?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(tie_id) DO UPDATE SET status=excluded.status,"
                " note=excluded.note, updated_at=excluded.updated_at,"
                " updated_by=excluded.updated_by",
                (tid, r.get("node"), r.get("feeder_a"), r.get("feeder_b"),
                 r.get("switch_id"),
                 r.get("status") or "proposed", r.get("note", ""), at, user))
            n += 1
        self.conn.commit()
        return n

    def load_tie_reviews(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for r in self.conn.execute(
                "SELECT tie_id, node, feeder_a, feeder_b, switch_id,"
                " status, note, updated_at, updated_by FROM tie_review"):
            out[r[0]] = {"tie_id": r[0], "node": r[1], "feeder_a": r[2],
                         "feeder_b": r[3], "switch_id": r[4], "status": r[5],
                         "note": r[6], "updated_at": r[7], "updated_by": r[8]}
        return out

    def save_plan_review(self, rows: list[dict], user: str = "ui-user",
                         at: str | None = None) -> int:
        """ثبت گردش کار تأیید مهندسی (پس از کنترل ظرفیت — نیاز ۹/۱۰)."""
        import json as _json
        from datetime import datetime as _dt
        at = at or _dt.now().isoformat(timespec="seconds")
        n = 0
        for r in rows:
            fk = str(r.get("feeder_key", "")).strip().upper()
            if not fk:
                continue
            self.conn.execute(
                "INSERT INTO plan_review (feeder_key, placement_run_id,"
                " scheme_id, status, reasons_json, updated_at, updated_by)"
                " VALUES (?,?,?,?,?,?,?)"
                " ON CONFLICT(feeder_key) DO UPDATE SET"
                " placement_run_id=excluded.placement_run_id,"
                " scheme_id=excluded.scheme_id, status=excluded.status,"
                " reasons_json=excluded.reasons_json,"
                " updated_at=excluded.updated_at, updated_by=excluded.updated_by",
                (fk, r.get("placement_run_id"), r.get("scheme_id"),
                 r.get("status"), _json.dumps(
                     r.get("reasons", []), ensure_ascii=False), at, user))
            n += 1
        self.conn.commit()
        return n

    def load_plan_reviews(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for r in self.conn.execute(
                "SELECT feeder_key, placement_run_id, scheme_id, status,"
                " reasons_json, updated_at, updated_by FROM plan_review"):
            import json as _json
            try:
                reasons = _json.loads(r[4] or "[]")
            except ValueError:
                reasons = []
            out[r[0]] = {"feeder_key": r[0], "placement_run_id": r[1],
                         "scheme_id": r[2], "status": r[3],
                         "reasons": reasons, "updated_at": r[5],
                         "updated_by": r[6]}
        return out

    # ------------------------------------------------------------------
    # project_kv — تنظیمات عمومی/نمایشی پروژه (استایل‌های نقشه، نام
    # گزارش، …) — درخواست کاربر: ماندگاری تنظیمات پس از بستن/بازکردن
    # ------------------------------------------------------------------
    def set_kv(self, key: str, value, user: str = "ui-user") -> None:
        """Upsert one JSON-safe value under a stable key."""
        from datetime import datetime as _dt
        self.conn.execute(
            "INSERT INTO project_kv (key, value_json, updated_at, updated_by)"
            " VALUES (?,?,?,?)"
            " ON CONFLICT(key) DO UPDATE SET"
            " value_json=excluded.value_json, updated_at=excluded.updated_at,"
            " updated_by=excluded.updated_by",
            (str(key),
             json.dumps(value, ensure_ascii=False, default=str),
             _dt.now().isoformat(timespec="seconds"), user))
        self.conn.commit()

    def get_kv(self, key: str, default=None):
        """Read one JSON value; missing/corrupt → ``default``."""
        try:
            row = self.conn.execute(
                "SELECT value_json FROM project_kv WHERE key=?",
                (str(key),)).fetchone()
        except sqlite3.Error as exc:
            _log.warning("get_kv(%s) failed: %s", key, exc)
            return default
        if row is None:
            return default
        try:
            return json.loads(row[0])
        except ValueError:
            return default

    def delete_kv(self, key: str) -> None:
        self.conn.execute("DELETE FROM project_kv WHERE key=?", (str(key),))
        self.conn.commit()
