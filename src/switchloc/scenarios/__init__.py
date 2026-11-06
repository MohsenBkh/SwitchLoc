# -*- coding: utf-8 -*-
"""scenarios — پایه سناریوهای بهره‌برداری و کلیدزنی (فاز ۲).

ARCHITECTURE.md §۵ lists `scenarios(پایه)` in Phase 2: the *model* that
Phase 4 (EP/TL, طرح‌های کلیدگذاری جدول ۱۳-۱۸) and Phase 3 (خاموشی) will
build upon.  Scope kept deliberately small and fully deterministic:

* `ScenarioState`   — effective open/closed decision per switch, derived
  from the GIS service state + confirmed NO states + the auditable
  unknown-state policy (TOPO-POL-01);
* `SwitchScenario`  — an ordered, attributed list of switching actions
  (open/close) on top of the base state — every action carries user,
  reason and timestamp so each configuration is auditable (بند ۱۹);
* `base.py`         — ScenarioState / SwitchScenario / evaluate() /
  isolation_scenario(): the base model AND the connectivity operations;
  the computational base of «برای هر خطا در هر زون» (جدول ۱۵) later on.

No load flow, no ENS — those belong to Phases 3/4 and live in their own
packages.  This package only answers: «با این وضعیت کلیدها، چه چیزی
برق‌دار است؟»
"""
