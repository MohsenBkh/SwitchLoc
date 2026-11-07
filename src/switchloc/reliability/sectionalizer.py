# -*- coding: utf-8 -*-
"""نام قدیمی ماژول — به :mod:`switchloc.reliability.switch_placement` منتقل شد.

این فایل فقط برای سازگاری با کد/آزمون‌های قبلی نگه داشته می‌شود؛ همهٔ
نام‌های عمومی از ماژول جدید بازصادر می‌شوند. کد جدید باید مستقیم از
``switch_placement`` ایمپورت کند.
"""
from .switch_placement import *              # noqa: F401,F403
from .switch_placement import (              # noqa: F401
    DEFAULT_FAILURE_RATE_PER_YEAR, DEFAULT_MAX_DOWNSTREAM_LOAD_RATIO,
    DEFAULT_MAX_SECTIONALIZERS, DEFAULT_MIN_CANDIDATE_DEPTH,
    DEFAULT_REPAIR_TIME_MIN, DEFAULT_RESTORATION_TIME_MIN,
    RESTORATION_MODELS, RESTORATION_MODEL_FA, SWITCH_TYPES, SWITCH_TYPE_FA,
    SWITCH_RECLOSER, SWITCH_SECTIONALIZER, SWITCH_DISCONNECTOR,
    RadialTree, Section, SectionCandidate, OptimizationStep, FeederStudy,
    SectionalizerSettings, SectionalizerStudy, SectionalizerEngine,
    SwitchPlacementSettings, SwitchPlacementStudy, SwitchPlacementEngine,
    build_radial_tree, build_sections, compute_eens_kwh,
    compute_transient_eens_kwh, eens_single_section_kwh,
    length_weighted_lambdas, theoretical_eens_kwh)
