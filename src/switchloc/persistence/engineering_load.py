"""Project-local, explicitly saved feeder load model."""
from __future__ import annotations

import json

from .store import ProjectStore

_KEY = "engineering_load_model_v1"


def save_load_model(path: str, model: dict) -> None:
    store = ProjectStore(path)
    try:
        store.set_kv(_KEY, model)
    finally:
        store.close()


def load_load_model(path: str) -> dict:
    store = ProjectStore(path)
    try:
        row = store.conn.execute(
            "SELECT value_json FROM project_kv WHERE key=?", (_KEY,)).fetchone()
        result = json.loads(row[0]) if row else {}
        if not isinstance(result, dict):
            raise ValueError("Invalid project load model")
        return result
    finally:
        store.close()


def merge_scoped_load_model(previous: dict, updated: dict, active_keys: list[str]) -> dict:
    """Replace the active exact feeder keys; preserve all out-of-scope entries."""
    result = dict(updated)
    pq = dict(previous.get("feeder_pq") or {})
    for key in active_keys:
        pq.pop(key, None)
    pq.update(updated.get("feeder_pq") or {})
    result["feeder_pq"] = pq
    return result
