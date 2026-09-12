"""Report limitations describe recorded scope without inventing a patched world."""
from wb_studio import caveats


def test_legacy_run_and_round_do_not_claim_a_repaired_upstream_world(monkeypatch):
    monkeypatch.setattr(caveats, "fork_version", lambda: "1.0.6")
    notes = caveats.for_run({"settings": {}}, {"setups": {}}) + caveats.for_round({})
    assert all("repaired fork" not in note for note in notes)
    assert any("local installation" in note.lower() and "1.0.6" in note for note in notes)
    assert any("not comparable" in note for note in notes)


def test_infrastructure_exclusion_names_the_attempt_metric():
    setup = {"pass": {"infrastructure": 1}, "cost": {"unknown_attempts": 0, "total": None}}
    notes = caveats.for_run({"settings": {}}, {"setups": {"example": setup}})
    assert any("attempt pass rates" in note and "selected tasks" in note for note in notes)
