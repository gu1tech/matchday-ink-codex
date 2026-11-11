import io
import json
import logging
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from .domain import next_fixture
from .metrics import prediction_metrics
from .render import encode_frame, render
from .scheduling import kickoff_due, poll_after
from .weather import forecast

LOG = logging.getLogger(__name__)


class Dashboard:
    def __init__(self, path=None, timezone="Europe/Dublin", weather_enabled=False, source=None,
                 prediction_engine=None, lifecycle=None):
        self.path = path
        self.source = source
        self.timezone = timezone
        self.weather_enabled = weather_enabled
        self.lock = threading.Lock()
        self.snapshot = None
        self.error = None
        self.prediction_engine = prediction_engine
        self.refresh_lock = threading.Lock()
        self.rollover_lock = threading.Lock()
        self.next_rollover_attempt = None
        self.ai_pending = False
        self.lifecycle = lifecycle
        restored = lifecycle.restore() if lifecycle else None
        if restored:
            self._publish(restored)

    def _publish(self, state):
        image = render(state["fixture"], self.timezone, state["weather"], stale=state["stale"],
                       ai_note=state.get("ai_note"), metrics=state.get("prediction_metrics"))
        png = io.BytesIO()
        image.save(png, format="PNG")
        with self.lock:
            self.snapshot = (state, encode_frame(image), png.getvalue())

    def refresh(self, now=None, include_ai=True):
        with self.refresh_lock:
            return self._refresh(now or datetime.now(UTC), include_ai)

    def _refresh(self, now, include_ai):
        if include_ai:
            self.ai_pending = False
        try:
            previous, _ = self.read()
            if self.lifecycle and previous and previous[0].get("fixture"):
                from .domain import timestamp
                current = previous[0]["fixture"]
                if timestamp(current["kickoff"]) <= now:
                    transition = self.lifecycle.check(current, now)
                    if transition["hold"]:
                        state = dict(previous[0], match_lifecycle=transition,
                                     update_policy="full_time_plus_5_minutes")
                        verified = state.get("data_verified_at")
                        if verified and (now - timestamp(verified)).total_seconds() > 86400:
                            state["stale"] = True
                        self.lifecycle.save(state)
                        self._publish(state)
                        return True
            raw = self.source.load(now) if self.source else json.loads(self.path.read_text())
            fixture = next_fixture(raw["fixtures"], now)
            weather = None
            weather_error = None
            if fixture and self.weather_enabled and not fixture["demo"]:
                try:
                    weather = forecast(fixture, now)
                except Exception as exc:
                    weather_error = type(exc).__name__
                    LOG.warning("Weather unavailable: %s", weather_error)
            state = {
                "schema_version": 1,
                "fixture": fixture,
                "weather": weather,
                "weather_error": weather_error,
                "timezone": self.timezone,
                "generated_at": now.isoformat(),
                "schedule_checked_at": now.isoformat(),
                "source_updated_at": raw.get("source_updated_at"),
                "data_verified_at": raw.get("source_verified_at") or raw.get("source_updated_at"),
                "demo": raw.get("demo", False),
                "stale": False,
                "provider": raw.get("provider"),
                "warnings": raw.get("warnings", []),
                "prediction": None,
                "ai_note": None,
                "prediction_metrics": None,
                "update_policy": "full_time_plus_5_minutes" if self.lifecycle else "kickoff",
            }
            # A future fixture isn't proof that a manually curated schedule is fresh.
            # Report source time separately; never pretend a reread is an upstream fetch.
            if not isinstance(raw.get("demo"), bool) or any(
                f["demo"] != raw["demo"] for f in raw["fixtures"]
            ):
                raise ValueError("Schedule and fixture demo flags must agree")
            if not raw["demo"]:
                from .domain import timestamp

                if not raw.get("source_updated_at"):
                    raise ValueError("Live/manual schedule requires source_updated_at")
                age = (now - timestamp(state["data_verified_at"])).total_seconds()
                if age < -300 or age > 86400:
                    state["stale"] = True
            if self.prediction_engine and include_ai:
                ai_status, result = self.prediction_engine.run(fixture, state["stale"], now)
                state["ai_status"] = {k: v for k, v in ai_status.items() if k != "result"}
                if result:
                    state["prediction"] = result["prediction"]
                    state["ai_analysis"] = result
                    state["prediction_metrics"] = prediction_metrics(result, now)
                    state["ai_note"] = (result["analysis"]["summary"] + " · "
                                        + result["prediction"]["most_likely_score"])
            image = render(fixture, self.timezone, weather, stale=state["stale"],
                           ai_note=state["ai_note"], metrics=state["prediction_metrics"])
            png = io.BytesIO()
            image.save(png, format="PNG")
            snapshot = (state, encode_frame(image), png.getvalue())
            with self.lock:
                self.snapshot, self.error = snapshot, None
                self.ai_pending = bool(self.prediction_engine and not include_ai)
            if self.lifecycle:
                self.lifecycle.save(state)
            return True
        except Exception as exc:
            LOG.warning("Schedule refresh failed: %s", type(exc).__name__)
            with self.lock:
                self.error = type(exc).__name__
                if self.snapshot:
                    state = dict(self.snapshot[0], stale=True)
                    image = render(state["fixture"], self.timezone, state["weather"], stale=True)
                    png = io.BytesIO()
                    image.save(png, format="PNG")
                    self.snapshot = (state, encode_frame(image), png.getvalue())
            return False

    def rollover(self, now=None):
        """Publish the next fixture without waiting for a model call at the boundary."""
        from datetime import timedelta

        now = now or datetime.now(UTC)
        with self.rollover_lock:
            snapshot, _ = self.read()
            if not snapshot or not kickoff_due(snapshot[0], now):
                return False
            if self.next_rollover_attempt and now < self.next_rollover_attempt:
                return False
            self.next_rollover_attempt = now + timedelta(seconds=60)
            return self.refresh(now, include_ai=False)

    def read(self):
        with self.lock:
            return self.snapshot, self.error


def serve(dashboard, host="127.0.0.1", port=8000, interval=3600):
    if interval < 180:
        raise ValueError("Refresh interval must be >=180 seconds")
    dashboard.refresh()
    stop = threading.Event()

    def refresh_loop():
        import time
        next_refresh = time.monotonic() + interval
        while not stop.wait(2):
            if dashboard.rollover():
                next_refresh = time.monotonic() + interval
                continue
            requested = dashboard.prediction_engine and dashboard.prediction_engine.requested()
            if requested or dashboard.ai_pending or time.monotonic() >= next_refresh:
                dashboard.refresh()
                next_refresh = time.monotonic() + interval

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = urlsplit(self.path).path
            if path in {"/v1/frame.bin", "/preview.png", "/v1/dashboard", "/"}:
                dashboard.rollover()
            snapshot, error = dashboard.read()
            status, kind = 200, "application/json"
            if path == "/health":
                body = json.dumps({"ready": snapshot is not None, "refresh_error": error}).encode()
                status = 200 if snapshot else 503
            elif path not in {"/v1/dashboard", "/v1/frame.bin", "/preview.png", "/"}:
                status, body = 404, b'{"error":"not_found"}'
            elif snapshot is None:
                status, body = 503, b'{"error":"no_valid_schedule"}'
            elif path == "/v1/dashboard":
                body = json.dumps(snapshot[0], ensure_ascii=True).encode()
            elif path == "/v1/frame.bin":
                kind, body = "application/octet-stream", snapshot[1]
            elif path == "/preview.png":
                kind, body = "image/png", snapshot[2]
            else:
                kind = "text/html; charset=utf-8"
                body = (
                    "<!doctype html><title>Matchday Ink</title>"
                    "<body style='background:#eee;font-family:system-ui;padding:2rem'>"
                    "<h1>Matchday Ink</h1><p>296 × 128 hardware preview</p>"
                    "<img src='/preview.png' width='888' height='384' style='image-rendering:pixelated;max-width:100%;height:auto'>"
                    "<p><a href='/v1/dashboard'>Data and provenance</a></p>"
                    "<p>Fixture source and freshness are available in the data view.</p>"
                ).encode()
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            if path == "/v1/frame.bin" and snapshot:
                from .domain import timestamp
                state = snapshot[0]
                remaining = 0
                if not state["stale"] and not state["demo"] and state.get("data_verified_at"):
                    age = (datetime.now(UTC) - timestamp(state["data_verified_at"])).total_seconds()
                    if age >= -300:
                        remaining = max(0, min(86400, int(86400 - age)))
                self.send_header("X-Matchday-Ink-Fresh-For", str(remaining))
                self.send_header("X-Matchday-Ink-Poll-After", str(poll_after(state, datetime.now(UTC))))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer((host, port), Handler)
    worker = threading.Thread(target=refresh_loop, daemon=True)
    worker.start()
    LOG.info("Dashboard listening on http://%s:%d", host, server.server_port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()
        worker.join(timeout=16)
