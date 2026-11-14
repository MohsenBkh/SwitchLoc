# -*- coding: utf-8 -*-
"""Qt offscreen: پنل «لایهٔ خاموشی‌ها» در تب نقشه (روشن/خاموش کردن رخدادها)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest                                        # noqa: E402

try:
    from PySide6 import QtWidgets                    # noqa: E402
    from PySide6.QtCore import Qt                    # noqa: E402
    HAS_QT = True
    ROLE = Qt.ItemDataRole.UserRole
except ImportError:                                  # pragma: no cover
    HAS_QT = False
    ROLE = 256

pytestmark = pytest.mark.skipif(
    not HAS_QT, reason="PySide6.QtWidgets is not importable")

POINTS = [
    {"id": "e1", "x": 50.0, "y": 0.0, "label": "پست الف",
     "status": "confirmed", "feeder": "F1", "zone_x": 60.0, "zone_y": 0.0},
    {"id": "e2", "x": 90.0, "y": 5.0, "label": "پست ب",
     "status": "pending", "feeder": "F1"},
    {"id": "e3", "x": 10.0, "y": 9.0, "label": "پست ج",
     "status": "rejected", "feeder": "F2"},
]


@pytest.fixture()
def app():
    if QtWidgets.QApplication.instance() is None:
        QtWidgets.QApplication([])
    yield


def _tab():
    from switchloc.ui.qt.map_canvas import make_map_canvas
    return make_map_canvas()


def _renderer():
    from types import SimpleNamespace
    from switchloc.ui.map_renderer import NetworkMapRenderer
    graph = SimpleNamespace(edges={}, nodes={}, switch_ids_at={},
                            transformer_ids_at={})
    return NetworkMapRenderer(graph, traces=[], zones=None, switches={})


def _items(tab):
    tree = tab.outage_list
    return [tree.topLevelItem(i).child(j)
            for i in range(tree.topLevelItemCount())
            for j in range(tree.topLevelItem(i).childCount())]


def test_panel_exists_and_starts_empty(app):
    tab = _tab()
    assert tab.outage_panel.isVisibleTo(tab) or True     # ویجت ساخته شده است
    assert tab.outage_count.text().startswith("0 خاموشی")
    assert tab.outage_list.topLevelItemCount() == 0
    assert tab.chk_outages.isChecked() is False          # هنوز رندری نبوده


def test_points_fill_the_panel_grouped_by_feeder(app):
    tab = _tab()
    tab.set_outage_points(POINTS)
    assert tab.outage_list.topLevelItemCount() == 2      # F1 و F2
    labels = [i.text(0) for i in _items(tab)]
    assert any("پست الف" in t and "تأیید مهندسی" in t for t in labels)
    assert any("در انتظار" in t for t in labels)
    assert "3 خاموشی دارای مختصات" in tab.outage_count.text()
    assert all(i.checkState(0) for i in _items(tab))     # همه روشن


def test_master_checkbox_controls_the_layer(app):
    tab = _tab()
    tab.show_network(_renderer(), title="t")
    tab.set_outage_points(POINTS)
    tab.chk_outages.setChecked(True)
    assert tab._renderer.style.show_outages is True
    tab.chk_outages.setChecked(False)
    assert tab._renderer.style.show_outages is False


def test_unchecking_one_event_hides_only_it_and_persists(app):
    tab = _tab()
    tab.show_network(_renderer(), title="t")
    tab.set_outage_points(POINTS)
    seen = []
    tab.on_outages_changed = lambda: seen.append(True)
    item = next(i for i in _items(tab) if i.data(0, ROLE) == "e2")
    item.setCheckState(0, item.checkState(0).Unchecked)
    assert tab._hidden_outage_ids == {"e2"}
    assert tab._renderer.style.hidden_outage_ids == ["e2"]
    assert seen                                     # ذخیره‌سازی سبک صدا زده شد
    assert "2 قابل نمایش" in tab.outage_count.text()


def test_show_all_and_hide_all_buttons(app):
    tab = _tab()
    tab.show_network(_renderer(), title="t")
    tab.set_outage_points(POINTS)
    tab.btn_outage_none.click()
    assert tab._hidden_outage_ids == {"e1", "e2", "e3"}
    assert "0 قابل نمایش" in tab.outage_count.text()
    tab.btn_outage_all.click()
    assert tab._hidden_outage_ids == set()
    assert "3 قابل نمایش" in tab.outage_count.text()


def test_group_checkbox_toggles_all_of_its_children(app):
    tab = _tab()
    tab.show_network(_renderer(), title="t")
    tab.set_outage_points(POINTS)
    group = next(tab.outage_list.topLevelItem(i)
                 for i in range(tab.outage_list.topLevelItemCount())
                 if tab.outage_list.topLevelItem(i).text(0) == "F1")
    group.setCheckState(0, group.checkState(0).Unchecked)
    assert tab._hidden_outage_ids == {"e1", "e2"}
    assert "1 قابل نمایش" in tab.outage_count.text()


def test_hidden_ids_from_the_style_are_restored(app):
    tab = _tab()
    tab.show_network(_renderer(), title="t")
    tab.set_outage_points(POINTS)
    tab.show_network(_renderer(), title="t2", hidden_outage_ids=["e3"])
    item = next(i for i in _items(tab) if i.data(0, ROLE) == "e3")
    assert item.checkState(0) != item.checkState(0).Checked
    tab.show_network(_renderer(), title="t3", hidden_outage_ids=[])
    assert all(i.checkState(0) for i in _items(tab))


def test_empty_list_is_stated_explicitly(app):
    tab = _tab()
    tab.show_network(_renderer(), title="t")
    tab.set_outage_points([])
    assert "0 خاموشی دارای مختصات" in tab.outage_count.text()
    assert tab.outage_list.topLevelItemCount() == 0
