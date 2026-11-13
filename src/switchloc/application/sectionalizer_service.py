# -*- coding: utf-8 -*-
"""نام قدیمی سرویس — به :mod:`switchloc.application.switch_placement_service` منتقل شد."""
from .switch_placement_service import *          # noqa: F401,F403
from .switch_placement_service import (          # noqa: F401
    KV_KEY, EENS_METHODS, EENS_METHOD_FA, EENS_METHOD_ORDER,
    EENS_METHOD_DIRECTIONAL, EENS_METHOD_UNIFORM, EENS_METHOD_MANUAL,
    EENS_METHOD_AUTO_RATES,
    SwitchPlacementAppSettings, SwitchPlacementAppResult,
    SwitchPlacementService, SectionalizerAppSettings,
    SectionalizerAppResult, SectionalizerService)
