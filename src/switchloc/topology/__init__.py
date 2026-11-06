# -*- coding: utf-8 -*-
"""topology — موتور توپولوژی SwitchLoc (فاز ۲، ARCHITECTURE.md §۵).

Modules:
* graph    : CanonicalNetwork → traversable NetworkGraph (edges split at
             device vertices so a mid-line switch can actually interrupt
             the line — the GeoGrid splice trick, re-implemented;
             audit §۳-۴ / test TG-03);
* tracing  : normal-state feeder reconstruction from SOURCE nodes with
             passability rules (TOPO-POL-01/02) and GIS-label mismatch
             detection;
* ties     : A-09 — NO/Tie candidate detection (proposed rule R1/R2) +
             explicit user confirmation contract;
* zones    : زون‌بندی per TAV122-02/00 تعریف ۵-۲۱ — components bounded by
             switches (split-node component labelling), Zone0..n numbering,
             boundary-switch bookkeeping for جدول ۱۵/۱۷.

Discipline (ARCHITECTURE.md §۱): engineering logic lives here, never in
ui/; every exclusion/assumption surfaces as an Issue; determinism in
every iteration order.
"""
