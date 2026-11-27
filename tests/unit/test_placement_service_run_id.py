from switchloc.application.placement_service import _latest_source_run_id


class _RunsStore:
    def __init__(self, runs):
        self._runs = runs

    def runs(self):
        return self._runs


def test_latest_source_run_reads_project_store_id_key():
    assert _latest_source_run_id(_RunsStore([{"id": "study-123"}])) == "study-123"


def test_latest_source_run_accepts_legacy_run_id_key():
    assert _latest_source_run_id(_RunsStore([{"run_id": "legacy-123"}])) == "legacy-123"


def test_latest_source_run_is_empty_when_store_has_no_runs():
    assert _latest_source_run_id(_RunsStore([])) == ""
