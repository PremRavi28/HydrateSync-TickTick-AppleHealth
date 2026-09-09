#!/usr/bin/env python3
"""
hydrate_sync.py

Reads the "Drink Water" habit from TickTick and mirrors it into a
private GitHub Gist as JSON. Runs on a schedule via GitHub Actions
(see .github/workflows/hydrate-sync.yml) — no server, no manual step
on this side. The HydrateSync iOS Shortcut (see shortcut/README.md)
later reads the Gist and writes it into Apple Health, which is the
one hop that has to happen on-device (Apple does not allow cloud
writes to HealthKit).

Author: Prem Ravi
"""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import requests
from requests.adapters import HTTPAdapter, Retry

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("hydrate_sync")

SYNC_FILENAME = "hydrate_sync.json"   # the file inside the gist that holds synced data
LOOKBACK_DAYS = 60                    # wide enough that a missed run (or a month away) still backfills
REQUEST_TIMEOUT = 20                  # seconds — never let a hung request block the whole job
BADGE_PATH = "badge.json"             # shields.io "endpoint" format — see README badge


@dataclass(frozen=True)
class HydrateSyncConfig:
    """All external inputs, read once and validated up front."""

    ticktick_username: str
    ticktick_password: str
    gist_id: str
    gist_token: str
    habit_name: str

    @classmethod
    def from_env(cls) -> "HydrateSyncConfig":
        required = [
            "TICKTICK_USERNAME",
            "TICKTICK_PASSWORD",
            "GIST_ID",
            "GIST_TOKEN",
        ]
        missing = [name for name in required if not os.environ.get(name)]
        if missing:
            log.error("Missing required secret(s): %s", ", ".join(missing))
            sys.exit(1)

        return cls(
            ticktick_username=os.environ["TICKTICK_USERNAME"],
            ticktick_password=os.environ["TICKTICK_PASSWORD"],
            gist_id=os.environ["GIST_ID"],
            gist_token=os.environ["GIST_TOKEN"],
            habit_name=os.environ.get("HABIT_NAME", "Drink Water"),
        )


def build_http_session() -> requests.Session:
    """A session that retries transient failures instead of just dying."""
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1.5, status_forcelist=(429, 500, 502, 503, 504))
    session.mount("https://", HTTPAdapter(max_retries=retries))
    return session


def fetch_hydration_log(config: HydrateSyncConfig) -> tuple[dict[str, int], int | None, str]:
    """
    Returns (days, goal, unit) where `days` maps "YYYYMMDD" -> ml logged.

    TickTick has no official public API for habit data, so this uses the
    community-maintained `ticktick-py-v2` client, which authenticates the
    same way a browser session would. Because it's an unofficial client,
    treat this function as the one most likely to need a small update if
    TickTick changes something on their end — everything below it (the
    Gist read/write) is a stable, documented GitHub API and won't need
    to change alongside it.
    """
    from ticktick_v2.habits import TicktickHabitHandler

    # ticktick-py-v2 reads these two exact env var names internally.
    os.environ["TICKTICK_EMAIL"] = config.ticktick_username
    os.environ["TICKTICK_PASSWORD"] = config.ticktick_password

    handler = TicktickHabitHandler()
    habits = handler.get_habits()
    habit = next((h for h in habits if getattr(h, "name", None) == config.habit_name), None)
    if habit is None:
        log.error("Habit %r not found in this TickTick account.", config.habit_name)
        sys.exit(1)

    since = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    checkins = handler.get_habit_checkins(habit, since=since)

    days: dict[str, int] = {}
    for entry in checkins:
        stamp = getattr(entry, "stamp", None) or getattr(entry, "date", None)
        value = getattr(entry, "value", None)
        if stamp is not None and value is not None:
            days[str(stamp)] = int(value)

    return days, getattr(habit, "goal", None), getattr(habit, "unit", "Milliliter")


def load_synced_log(session: requests.Session, config: HydrateSyncConfig) -> dict:
    """Reads whatever HydrateSync last wrote to the gist, so today's run can merge onto it."""
    resp = session.get(
        f"https://api.github.com/gists/{config.gist_id}",
        headers={"Authorization": f"Bearer {config.gist_token}", "Accept": "application/vnd.github+json"},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    raw = resp.json().get("files", {}).get(SYNC_FILENAME, {}).get("content")
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        log.warning("Existing gist content wasn't valid JSON — starting fresh.")
        return {}


def merge_days(existing_days: dict[str, int], fresh_days: dict[str, int]) -> dict[str, int]:
    """
    Combines a previously-synced day map with a freshly-fetched one.
    Fresh data wins on overlap, so a day TickTick has since corrected
    (e.g. a check-in edited after the fact) stays correct rather than
    getting stuck on whatever was synced first. Pulled out as its own
    function because it's the one piece of real logic in this script
    worth testing without needing TickTick or GitHub credentials.
    """
    return {**existing_days, **fresh_days}


def save_synced_log(session: requests.Session, config: HydrateSyncConfig, payload: dict) -> None:
    resp = session.patch(
        f"https://api.github.com/gists/{config.gist_id}",
        headers={"Authorization": f"Bearer {config.gist_token}", "Accept": "application/vnd.github+json"},
        json={"files": {SYNC_FILENAME: {"content": json.dumps(payload, indent=2, sort_keys=True)}}},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()


def write_status_badge(synced_at: datetime, day_count: int) -> None:
    """
    Writes badge.json in the shields.io "endpoint" schema
    (https://shields.io/badges/endpoint-badge). The workflow commits this
    file after a successful run, and the README badge points shields.io
    at its raw GitHub URL — shields re-reads it live on every view, so
    the badge always reflects the last successful sync with no separate
    badge-hosting service involved.
    """
    badge = {
        "schemaVersion": 1,
        "label": "last synced",
        "message": f"{synced_at.strftime('%Y-%m-%d %H:%M UTC')} · {day_count}d",
        "color": "0B8C87",
    }
    with open(BADGE_PATH, "w") as f:
        json.dump(badge, f, indent=2)


def main() -> None:
    config = HydrateSyncConfig.from_env()
    session = build_http_session()

    fresh_days, goal, unit = fetch_hydration_log(config)
    synced_log = load_synced_log(session, config)

    merged_days = merge_days(synced_log.get("days", {}), fresh_days)

    payload = {
        "habit": config.habit_name,
        "unit": unit,
        "goal": goal,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "days": merged_days,
    }

    save_synced_log(session, config, payload)
    write_status_badge(datetime.now(timezone.utc), len(merged_days))
    log.info("Synced %d day(s); gist now holds %d day(s) total.", len(fresh_days), len(merged_days))


if __name__ == "__main__":
    main()
