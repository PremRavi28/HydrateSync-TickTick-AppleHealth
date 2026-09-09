"""
Tests for the pure logic in hydrate_sync.py — no network, no secrets,
no TickTick or GitHub account needed to run these.

    python -m pytest test_hydrate_sync.py
"""

from hydrate_sync import merge_days


def test_merge_adds_new_days():
    existing = {"20260907": 3000}
    fresh = {"20260908": 3150}
    assert merge_days(existing, fresh) == {"20260907": 3000, "20260908": 3150}


def test_merge_overwrites_changed_days():
    # TickTick can report a corrected total for a day already synced —
    # the fresh value must win, not the stale one.
    existing = {"20260908": 2000}
    fresh = {"20260908": 3150}
    assert merge_days(existing, fresh) == {"20260908": 3150}


def test_merge_keeps_untouched_history():
    # Days outside the lookback window shouldn't disappear just because
    # this run didn't re-fetch them.
    existing = {"20260801": 3000, "20260802": 2800}
    fresh = {"20260908": 3150}
    result = merge_days(existing, fresh)
    assert result["20260801"] == 3000
    assert result["20260802"] == 2800
    assert result["20260908"] == 3150


def test_merge_handles_empty_existing_log():
    # First-ever run: nothing synced yet.
    assert merge_days({}, {"20260908": 3150}) == {"20260908": 3150}


def test_merge_handles_empty_fresh_fetch():
    # A run where TickTick returned nothing new shouldn't erase history.
    existing = {"20260907": 3000}
    assert merge_days(existing, {}) == existing
