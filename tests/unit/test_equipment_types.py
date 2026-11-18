import sys
from types import SimpleNamespace

from switchloc.application.equipment_types import (
    DEFAULT_TYPES_CATALOG, EquipmentTypeCatalog, default_types_catalog_path,
    resolution_report)
from switchloc.application.level2_placement_service import _apply_catalog_lines
from switchloc.reliability.power_flow import PowerFlowSettings
from switchloc.domain.enums import BranchKind, SwitchFamily


def test_bundled_catalog_has_required_sheets_and_rows():
    catalog = EquipmentTypeCatalog(DEFAULT_TYPES_CATALOG)
    assert len(catalog.lines) >= 35
    assert len(catalog.transformers) == 60
    assert len(catalog.fuses) == 20


def test_catalog_resolves_from_data_next_to_frozen_executable(tmp_path, monkeypatch):
    executable_dir = tmp_path / "dist"
    catalog = executable_dir / "data" / "catalog" / "types_override.xlsx"
    catalog.parent.mkdir(parents=True)
    catalog.write_bytes(b"catalog")
    monkeypatch.setenv("SWITCHLOC_TYPES_CATALOG", "")
    monkeypatch.setattr(sys, "executable", str(executable_dir / "SwitchLoc.exe"))
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "_MEI_TEMP"), raising=False)
    assert default_types_catalog_path() == catalog


def test_exact_bare_acsr_signature_selects_catalog_line_type():
    catalog = EquipmentTypeCatalog()
    branch = SimpleNamespace(
        id="b-35", feeder_name="F1", kind=BranchKind.LINE_AERIAL,
        conductor="(ACSR) آلومينيوم – فولاد", section_mm2=35,
        installation="سيم لخت")
    result = catalog.resolve_branch(branch)
    assert result.status == "matched"
    assert result.selected_type == "35-Al_St"


def test_explicit_catalog_conductor_type_mink_resolves_from_gis_name():
    catalog = EquipmentTypeCatalog()
    branch = SimpleNamespace(
        id="b-mink", feeder_name="F1", kind=BranchKind.LINE_AERIAL,
        conductor="ACSR-MINK", section_mm2=None, installation="سيم لخت")
    result = catalog.resolve_branch(branch)
    assert result.status == "matched"
    assert result.selected_type == "ACSR-MINK"
    assert catalog.line_ampacity_a(result.selected_type) == 291.0


def test_level2_uses_catalog_sline_in_kiloamps_as_amps_by_default():
    catalog = EquipmentTypeCatalog()
    branch = SimpleNamespace(
        id="b-mink", feeder_name="F1", kind=BranchKind.LINE_AERIAL,
        conductor="ACSR-MINK", section_mm2=None, installation="سيم لخت")
    settings = PowerFlowSettings(base_voltage_kv=20.0)
    _apply_catalog_lines(settings, catalog, [branch])
    assert settings.edge_overrides["b-mink"]["max_current_a"] == 291.0
    assert settings.edge_overrides["b-mink"]["r_ohm_per_km"] == 0.46


def test_overhead_covered_acsr_is_not_assumed_to_be_bare_type():
    catalog = EquipmentTypeCatalog()
    branch = SimpleNamespace(
        id="b-covered", feeder_name="F2", kind=BranchKind.LINE_AERIAL,
        conductor="(ACSR) آلومينيوم – فولاد", section_mm2=70,
        installation="سيم روكش دار")
    result = catalog.resolve_branch(branch)
    assert result.status == "unmatched"
    assert result.selected_type is None


def test_transformer_capacity_with_multiple_catalog_families_is_ambiguous():
    catalog = EquipmentTypeCatalog()
    transformer = SimpleNamespace(id="t-100", feeder_name="F3",
                                  capacity_kva=100, kind_raw="روغنی")
    result = catalog.resolve_transformer(transformer)
    assert result.status == "ambiguous"
    assert len(result.candidates) > 1
    assert result.selected_type is None


def test_fuse_matches_exact_current_and_voltage_only():
    catalog = EquipmentTypeCatalog()
    fuse = SimpleNamespace(id="f-10", feeder_name="F4",
                           family=SwitchFamily.FUSE_CUTOUT, rating_a=10,
                           switch_type_raw="cutout")
    assert catalog.resolve_switch(fuse, 20).selected_type == "Fuse_Type_10"
    assert catalog.resolve_switch(fuse, 11).status == "unmatched"


def test_other_switch_family_has_no_workbook_type_sheet():
    catalog = EquipmentTypeCatalog()
    switch = SimpleNamespace(id="s-1", feeder_name="F1",
                             family=SwitchFamily.BREAKER, rating_a=400,
                             switch_type_raw="breaker")
    assert catalog.resolve_switch(switch).status == "unsupported"


def test_resolution_report_preserves_feeder_and_status_counts():
    catalog = EquipmentTypeCatalog()
    branch = SimpleNamespace(id="b", feeder_name="F9", kind=BranchKind.JUMPER,
                             conductor="", section_mm2=None, installation="")
    report = resolution_report([catalog.resolve_branch(branch)])
    assert report["feeders"]["F9"]["counts"]["unsupported"] == 1
