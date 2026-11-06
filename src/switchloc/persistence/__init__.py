# -*- coding: utf-8 -*-
"""SQLite project persistence (docs/ARCHITECTURE.md D-03)."""
from .schema import SCHEMA_SQL
from .store import ProjectStore

__all__ = ["ProjectStore", "SCHEMA_SQL"]
