"""Keep the current match until confirmed full time plus a five-minute buffer."""

import json
import re
import ssl
from datetime import timedelta
from urllib.request import urlopen

import certifi

from .domain import timestamp
from .providers.standings import match_scoreboard
from .storage import read_json, write_json


def completed_status(payload, event):
    header = payload.get("header", {})
    if str(header.get("id")) != str(event["event_id"]):
        raise ValueError("Match status identity mismatch")
    competitions = header.get("competitions", [])
    if len(competitions) != 1:
        raise ValueError("Ambiguous match status")
    comp = competitions[0]
    actual = {entry.get("homeAway"): str(entry.get("team", {}).get("id"))
              for entry in comp.get("competitors", [])}
    expected = {side: str(event["teams"][side]["id"]) for side in ("home", "away")}
    if actual != expected:
        raise ValueError("Match status team mismatch")
    status = comp.get("status", {}).get("type", {})
    return status.get("completed") is True and status.get("state") == "post"


class MatchLifecycle:
    def __init__(self, root, opener=urlopen):
        self.path = root / "data/cache/match-lifecycle.json"
        self.opener = opener
        self.saved = read_json(self.path, {})

    def restore(self):
        return self.saved.get("snapshot")

    def save(self, state):
        old = self.saved.get("snapshot", {}).get("fixture") or {}
        new = state.get("fixture") or {}
        if old.get("id") != new.get("id") or old.get("kickoff") != new.get("kickoff"):
            self.saved = {}
        self.saved["snapshot"] = state
        write_json(self.path, self.saved)

    def get(self, url):
        with self.opener(url, timeout=12,
                         context=ssl.create_default_context(cafile=certifi.where())) as response:
            data = response.read(2_000_001)
        if len(data) > 2_000_000:
            raise ValueError("Match status response too large")
        return json.loads(data)

    def check(self, fixture, now):
        kickoff = timestamp(fixture["kickoff"])
        # Full time cannot normally occur before 90 minutes + half time.
        # Start checking at 105 minutes; never assume that this means the match has ended.
        first_check = kickoff + timedelta(minutes=105)
        if now < first_check:
            return {"hold": True, "phase": "in_progress", "next_check_at": first_check.isoformat()}
        ended = self.saved.get("full_time_observed_at")
        if ended:
            release = timestamp(ended) + timedelta(minutes=5)
            return {"hold": now < release, "phase": "buffer" if now < release else "complete",
                    "full_time_observed_at": ended, "release_at": release.isoformat(),
                    "next_check_at": release.isoformat()}
        try:
            event = fixture.get("provenance", {}).get("espn_event")
            if not event:
                league = {"CL": "uefa.champions"}.get(fixture["competition"], fixture["competition"])
                if not re.fullmatch(r"[a-z]+\.[a-z0-9]+", league):
                    raise ValueError("Unverified competition")
                url = (f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league}"
                       f"/scoreboard?dates={kickoff.strftime('%Y%m%d')}")
                found = match_scoreboard(self.get(url), fixture, league)
                if len(found) != 1:
                    raise ValueError("Unverified match")
                event = found[0]
            league, identity = event["league"], str(event["event_id"])
            if not re.fullmatch(r"[a-z]+\.[a-z0-9]+", league) or not identity.isdigit():
                raise ValueError("Invalid status identity")
            url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league}/summary?event={identity}"
            if completed_status(self.get(url), event):
                self.saved["full_time_observed_at"] = now.isoformat()
                write_json(self.path, self.saved)
                return {"hold": True, "phase": "buffer", "full_time_observed_at": now.isoformat(),
                        "release_at": (now + timedelta(minutes=5)).isoformat(),
                        "next_check_at": (now + timedelta(minutes=5)).isoformat(), "source": url}
            phase = "in_progress"
        except Exception:
            # Unknown full time must not become a guessed release time.
            phase = "status_unavailable"
        return {"hold": True, "phase": phase,
                "next_check_at": (now + timedelta(seconds=60)).isoformat()}
