from datetime import UTC, datetime

import pytest

from matchday.providers.api_football import ProviderError
from matchday.providers.calendar_feed import parse_calendar

NOW = datetime(2030, 11, 2, 12, tzinfo=UTC)
URL = "https://ics.fixtur.es/v2/example.ics"


def event(
    uid="one",
    start="20301103T174500Z",
    summary="Galatasaray - Test FC [CL]",
    status="CONFIRMED",
    sequence=0,
):
    return f"""BEGIN:VEVENT\r
UID:{uid}\r
SEQUENCE:{sequence}\r
DTSTAMP:20301102T090000Z\r
DTSTART:{start}\r
SUMMARY:{summary}\r
STATUS:{status}\r
END:VEVENT\r
"""


def feed(*events):
    return (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:unit-test\r\n"
        + "".join(events)
        + "END:VCALENDAR\r\n"
    ).encode()


def parse(data):
    return parse_calendar(data, "Galatasaray", URL, NOW, NOW)


def test_calendar_gets_upcoming_home_and_away_without_fake_enrichment():
    raw = parse(
        feed(
            event("later", "20301105T190000Z"),
            event("first", "20301103T174500Z", "Test FC - Galatasaray [CL]"),
        )
    )
    f = raw["fixtures"][0]
    assert f["id"] == "first" and f["away"] == "Galatasaray"
    assert f["kickoff"] == "2030-11-03T17:45:00+00:00" and not f["demo"]
    assert "home_form" not in f and "home_standing" not in f
    assert raw["source_updated_at"] == "2030-11-02T09:00:00+00:00"


def test_cancelled_and_past_events_excluded():
    raw = parse(
        feed(
            event("past", "20301101T174500Z"),
            event("cancelled", "20301103T174500Z", status="CANCELLED"),
            event("next", "20301105T174500Z"),
        )
    )
    assert raw["fixtures"][0]["id"] == "next"


def test_date_only_match_cannot_be_silently_skipped():
    all_day = event("date-only", "20301103").replace("DTSTART:", "DTSTART;VALUE=DATE:")
    with pytest.raises(ProviderError, match="unconfirmed kickoff"):
        parse(feed(all_day, event("later", "20301105T190000Z")))


def test_latest_cancellation_supersedes_earlier_same_uid():
    raw = parse(
        feed(
            event("same", "20301103T174500Z"),
            event("same", "20301103T174500Z", status="CANCELLED", sequence=1),
            event("next", "20301105T174500Z"),
        )
    )
    assert raw["fixtures"][0]["id"] == "next"


def test_timezone_offset_is_normalized():
    value = event(start="20301103T204500").replace("DTSTART:", "DTSTART;TZID=Europe/Istanbul:")
    assert parse(feed(value))["fixtures"][0]["kickoff"] == "2030-11-03T17:45:00+00:00"


def test_empty_calendar_does_not_become_demo():
    with pytest.raises(ProviderError, match="no verified future"):
        parse(feed())
