"""Loopback-only Wi-Fi setup over USB. Passwords never enter logs or files."""
import argparse
import base64
import json
import logging
import queue
import secrets
import threading
import time
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .ai_prediction import AISettings

LOG = logging.getLogger(__name__)
FIELDS = {
    "event", "configured", "wifi_connected", "wifi_status", "ip", "http_status",
    "frame_bytes", "display_count", "last_error", "refresh_seconds",
    "networks", "scan_in_progress", "data_fresh", "link_available", "cache_ready", "cached_frame",
    "next_check_in",
    "received_frame_hash", "drawn_frame_hash",
}


def config_command(ssid, password, frame_url, refresh_seconds=0):
    if not isinstance(ssid, str) or not 1 <= len(ssid.encode()) <= 32 or "\0" in ssid:
        raise ValueError("Wi-Fi name must be 1–32 bytes.")
    if not isinstance(password, str) or "\0" in password:
        raise ValueError("Invalid Wi-Fi password.")
    size = len(password.encode())
    if size and not 8 <= size <= 63:
        raise ValueError("Wi-Fi password must be 8–63 bytes; leave blank for an open network.")
    if not isinstance(frame_url, str) or len(frame_url.encode()) > 240:
        raise ValueError("Invalid server address.")
    try:
        parts = urlsplit(frame_url)
        port = parts.port
    except ValueError:
        raise ValueError("Invalid server address.") from None
    if (parts.scheme != "http" or not parts.hostname or parts.username or parts.password
            or parts.hostname in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
            or (port is not None and not 1 <= port <= 65535) or parts.fragment
            or "\0" in frame_url):
        raise ValueError("Use a local HTTP server address that the ESP32 can reach.")
    if type(refresh_seconds) is not int or (refresh_seconds != 0 and not 180 <= refresh_seconds <= 86400):
        raise ValueError("Choose kickoff mode (0) or a check interval of 180–86400 seconds.")

    def encode(value):
        return base64.b64encode(value.encode()).decode() if value else "-"

    return ("MATCHDAY_INK_CONFIG " + " ".join(map(encode, [ssid, password, frame_url]))
            + f" {refresh_seconds}\n").encode()


class Device:
    def __init__(self, port=None):
        self.requested_port = port
        self.lock = threading.Lock()
        self.commands = queue.SimpleQueue()
        self.state = {"serial_connected": False, "firmware_ready": False}
        self.stop = threading.Event()
        self.worker = threading.Thread(target=self._run, daemon=True)

    def read(self):
        with self.lock:
            return dict(self.state)

    def _update(self, **values):
        with self.lock:
            self.state.update(values)

    def send(self, data):
        state = self.read()
        if not state.get("serial_connected") or not state.get("firmware_ready"):
            raise RuntimeError("The ESP32 firmware connection is not ready yet.")
        self.commands.put(data)

    def _port(self):
        from serial.tools import list_ports
        ports = list(list_ports.comports())
        if self.requested_port and any(p.device == self.requested_port for p in ports):
            return self.requested_port
        esp = [p.device for p in ports if p.vid == 0x303A]
        return esp[0] if len(esp) == 1 else None

    def _run(self):
        import serial
        while not self.stop.is_set():
            link = None
            try:
                port = self._port()
                if not port:
                    self._update(serial_connected=False, firmware_ready=False)
                    self.stop.wait(1)
                    continue
                link = serial.Serial(port=None, baudrate=115200, timeout=0.2, write_timeout=2)
                link.dtr = False
                link.rts = False
                link.port = port
                link.open()
                self._update(serial_connected=True, firmware_ready=False, port=port)
                poll = 0
                while not self.stop.is_set():
                    while not self.commands.empty():
                        command = self.commands.get_nowait()
                        link.write(command)
                        del command
                    if time.monotonic() >= poll:
                        link.write(b"MATCHDAY_INK_STATUS\n")
                        poll = time.monotonic() + 5
                    line = link.readline(8192)
                    if not line.startswith(b"{"):
                        continue
                    try:
                        event = json.loads(line)
                    except (ValueError, UnicodeDecodeError):
                        continue
                    if event.get("event") not in {
                        "status", "setup_required", "configured", "config_error",
                        "wifi_connecting", "wifi_connected", "wifi_disconnected", "wifi_retry",
                        "fetch_failed", "display_starting", "display_failed", "display_complete",
                        "unchanged", "display_cooldown", "refresh_requested", "data_received",
                        "wifi_scan_started", "wifi_scan_done", "wifi_scan_failed", "wifi_scan_throttled",
                        "interval_updated",
                    }:
                        continue
                    clean = {k: v for k, v in event.items() if k in FIELDS}
                    clean.update(firmware_ready=True, last_seen_at=datetime.now(UTC).isoformat())
                    if event["event"] == "data_received":
                        clean["last_data_received_at"] = datetime.now(UTC).isoformat()
                    self._update(**clean)
                    if event["event"] != "status":
                        LOG.info("Device event: %s", event["event"])
            except (OSError, serial.SerialException, ValueError):
                self._update(serial_connected=False, firmware_ready=False)
                self.stop.wait(1)
            finally:
                if link:
                    link.close()


PAGE = r"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Matchday Ink setup</title>
<style nonce="NONCE">*{box-sizing:border-box}body{margin:0;background:#f4f3ef;color:#202328;
font:16px system-ui,sans-serif}main{max-width:650px;margin:32px auto;padding:24px}
h1{font-size:30px;margin-bottom:8px}p{line-height:1.5}section{background:white;padding:24px;
border-radius:18px;margin:20px 0}label{display:block;margin:17px 0 7px;font-weight:600}
input,select,button{width:100%;padding:12px;font:inherit;border:1px solid #d4d4d2;border-radius:9px}
button{background:#ac182e;color:white;border:0;margin-top:17px;cursor:pointer}button:disabled{opacity:.5}
.secondary{background:#eeede8;color:#24272b;margin-top:9px}small{color:#686b71;line-height:1.5}
pre{white-space:pre-wrap;font:14px system-ui;line-height:1.8}#message{color:#8c1d27}
a{color:#971b30}input[readonly]{background:#f7f7f5;font-size:13px}.notes{font-size:14px}
input[type=checkbox]{width:auto;margin-right:8px}h2{font-size:20px;margin:0 0 10px}
</style><main><small>MATCHDAY INK</small><h1>Connect your device</h1>
<p>The ESP32 scans nearby <b>2.4 GHz networks</b>. Select your network and enter its password.
Use the same network as your Mac.</p>
<section><form id="setup"><label for="ssid">Available Wi-Fi networks</label>
<select id="ssid" required><option value="">Waiting for device and network scan…</option></select>
<button class="secondary" id="scan" type="button" disabled>Scan again</button>
<small id="scan-state"></small>
<label for="password">Wi-Fi password</label><input id="password" type="password" autocomplete="off">
<label for="url">Data server on this Mac</label><input id="url" readonly value="FRAME_URL">
<label for="interval">Update mode</label><select id="interval">
<option value="0">Automatic — full time + 5 minutes</option>
<option value="300">Check every 5 minutes</option><option value="3600">Check every hour</option></select>
<small>Keeps the current match until full time is confirmed, then waits five minutes before switching.
Checks match status near full time; extra time and penalties delay the switch. Background checks catch fixture changes.
The panel refresh itself takes a few seconds; its three-minute minimum interval still applies.</small>
<button class="secondary" id="save-interval" type="button" disabled>Save update mode</button>
<button id="save" type="submit" disabled>Save to device and connect</button></form><p id="message"></p>
<small>Your Wi-Fi password is sent over USB to the device; it is not written to chat or project files.</small></section>
<section><b>Connection and data status</b><pre id="status">Waiting for ESP32…</pre>
<button id="refresh" type="button" disabled>Check data now</button>
<button id="redraw" class="secondary" type="button" disabled>Download and redraw screen</button>
<p class="notes"><b>Display icons:</b> The Wi-Fi icon shows access to the data server. A circled check means the source was verified
within the last 24 hours. Crossed-out Wi-Fi means a connection problem; a clock means old or unverified data.</p></section>
<section class="notes"><b>After a power cut</b><p>Settings stay on the device. When power returns, it reconnects and checks for data.
If the network is unavailable, the last saved image remains. E-paper retains its image without power,
so its icons also represent the last known status.</p>
<b>ESP32 connection help</b><p>If the device is missing, check the USB data cable and
<b>press RESET/RST once</b>. BOOT + RESET is only needed for firmware upload mode.</p>
<small>Failed downloads retry after one minute. Icon changes refresh at most once every three minutes
to reduce panel flashing. The fixture provider has its own update schedule.</small></section>
<section><h2>AI match prediction</h2>
<p class="notes">Completed match results feed an experimental goal model. OpenAI writes a short
English outlook for the red display strip. Missing history is never invented.</p>
<form id="ai-setup"><label for="api-key">OpenAI API key</label>
<input id="api-key" type="password" autocomplete="off" placeholder="sk-… (leave blank to keep saved key)">
<small>The key stays on this Mac in a private, git-ignored file. It is never sent to the ESP32.</small>
<label for="ai-model">OpenAI model</label><input id="ai-model" value="gpt-4.1-mini" maxlength="80">
<label><input id="ai-enabled" type="checkbox">Enable daily AI analysis (uses API credits)</label>
<button type="submit">Save AI settings</button></form>
<pre id="ai-status">Checking AI settings…</pre>
<button id="ai-generate" class="secondary" type="button" disabled>Generate / check prediction</button>
<p class="notes">Display: H = home, D = draw, A = away. Data quality: High = 10 matches per team,
checked within 6 hours; Medium = at least 5 each, checked within 24 hours; otherwise Low.
This measures data coverage, not forecasting accuracy.</p>
<p class="notes">Analysis is cached for 24 hours per fixture and model. Failed attempts retry automatically
after one hour; manual retry is available after one minute.
Match updates continue if AI is unavailable. Predictions are experimental, not calibrated odds.</p>
<p class="notes"><a href="https://platform.openai.com/settings/organization/billing/overview" target="_blank" rel="noreferrer">OpenAI API billing</a> ·
<a href="https://platform.openai.com/settings/organization/limits" target="_blank" rel="noreferrer">API limits</a></p>
</section>
<p><a href="PREVIEW_URL" target="_blank" rel="noreferrer">Open display preview</a></p>
<small>The data server runs on this Mac; it must be awake to deliver new data.</small></main>
<script nonce="NONCE">const token=TOKEN;let autoScan=false,lastNetworks='',intervalLoaded=false;
async function post(path,body){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Matchday-Ink-Token':token},body:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw Error(d.error);return d}
function message(text){document.querySelector('#message').textContent=text}
async function scan(){try{await post('/api/scan',{});document.querySelector('#scan-state').textContent='ESP32 is scanning networks…'}catch(e){message(e.message)}}
function networkOptions(networks){const signature=JSON.stringify(networks);if(signature===lastNetworks)return;
lastNetworks=signature;const select=document.querySelector('#ssid'),previous=select.value;select.replaceChildren();
const blank=document.createElement('option');blank.value='';blank.textContent=networks.length?'Choose your network…':'No networks found; scan again';select.append(blank);
for(const n of networks){const option=document.createElement('option');option.value=n.ssid;
option.textContent=n.ssid+' · '+(n.rssi>=-60?'Strong':n.rssi>=-75?'Medium':'Weak')+(n.secure?'':' · Open network');select.append(option)}
if(networks.some(n=>n.ssid===previous))select.value=previous;else if(networks.length===1)select.value=networks[0].ssid;
document.querySelector('#scan-state').textContent=networks.length+' networks found.';}
async function poll(){try{const s=await(await fetch('/api/status')).json();
for(const id of ['save','refresh','redraw','scan'])document.querySelector('#'+id).disabled=!s.firmware_ready;
document.querySelector('#save-interval').disabled=!(s.firmware_ready&&s.configured);
if(s.firmware_ready&&!autoScan){autoScan=true;scan()}
if(s.networks)networkOptions(s.networks);
if(s.scan_in_progress)document.querySelector('#scan-state').textContent='ESP32 is scanning networks…';
if(s.event==='wifi_scan_throttled')document.querySelector('#scan-state').textContent='Wait 15 seconds after the last scan, then try again.';
if(s.event==='wifi_scan_failed')document.querySelector('#scan-state').textContent='Scan failed; please try again.';
if(s.configured&&!intervalLoaded){const select=document.querySelector('#interval');if([...select.options].some(o=>Number(o.value)===s.refresh_seconds))select.value=String(s.refresh_seconds);intervalLoaded=true}
const stage={display_starting:'Refreshing display',display_complete:'Display updated',
unchanged:'Image unchanged; no panel refresh needed',setup_required:'Waiting for Wi-Fi setup'}[s.event]||'';
document.querySelector('#status').textContent=[
'USB: '+(s.serial_connected?'Connected':'Waiting for device'),'Firmware: '+(s.firmware_ready?'Ready':'Waiting'),
'Wi-Fi: '+(!s.serial_connected?'USB disconnected; live status unknown':s.wifi_connected?'Connected ('+s.ip+')':'Not connected'),
'Data server: '+(s.link_available?'Reachable':'Not yet verified'),
'Data: '+(s.data_fresh?'Fresh / verified':'Waiting for recheck'),
'Update mode: '+(s.refresh_seconds===0?'Full time + 5 minutes':s.refresh_seconds===86400?'Legacy daily; save Automatic above':'Periodic with match-end override'),
typeof s.next_check_in==='number'?'Next data check: '+new Date(Date.now()+s.next_check_in*1000).toLocaleString('en-IE'):'',
s.last_data_received_at?'Last data received: '+new Date(s.last_data_received_at).toLocaleString('en-IE'):'',
'Display refresh count: '+(s.display_count||0),stage,s.last_error?'Status: '+({not_configured:'Waiting for Wi-Fi settings',connecting:'Connecting',wifi_not_connected:'Cannot connect; check the password and 2.4 GHz network',wifi_disconnected:'Wi-Fi disconnected',http_error:'Data server unreachable',invalid_frame:'Invalid display data',display_busy_timeout:'Display BUSY line did not respond'}[s.last_error]||s.last_error):''].filter(Boolean).join('\n');
}catch(e){}setTimeout(poll,1500)}poll();
document.querySelector('#scan').onclick=scan;
document.querySelector('#save-interval').onclick=async()=>{try{await post('/api/interval',{refresh_seconds:Number(document.querySelector('#interval').value)});message('Update mode saved without changing your password.')}catch(e){message(e.message)}};
document.querySelector('#setup').addEventListener('submit',async e=>{e.preventDefault();try{
await post('/api/configure',{ssid:document.querySelector('#ssid').value,password:document.querySelector('#password').value,
frame_url:document.querySelector('#url').value,refresh_seconds:Number(document.querySelector('#interval').value)});
document.querySelector('#password').value='';message('Settings sent to the device. Connection status will update below.');
}catch(e){message(e.message)}});
document.querySelector('#refresh').onclick=async()=>{try{await post('/api/refresh',{})}catch(e){message(e.message)}};
document.querySelector('#redraw').onclick=async()=>{try{await post('/api/redraw',{});message('Latest frame requested for redraw; the panel cooldown still applies.')}catch(e){message(e.message)}};
let aiLoaded=false,lastAnalysis='';
async function pollAI(){try{const s=await(await fetch('/api/ai/status')).json();
if(!aiLoaded){document.querySelector('#ai-model').value=s.model;document.querySelector('#ai-enabled').checked=s.enabled;aiLoaded=true}
document.querySelector('#ai-generate').disabled=!(s.configured&&s.enabled)||s.state==='working';
const result=s.result,p=result&&result.prediction,m=s.display_metrics;
if(s.enabled&&result&&result.generated_at!==lastAnalysis){lastAnalysis=result.generated_at;
post('/api/refresh',{}).catch(()=>{});}
document.querySelector('#ai-status').textContent=[
'API key: '+(s.configured?'Saved on this Mac':'Not configured'),
'Daily analysis: '+(s.enabled?'Enabled':'Disabled'),s.message||'',
result?'Generated: '+new Date(result.generated_at).toLocaleString('en-IE'):'',
m?'Model estimate: Home '+m.home+'% · Draw '+m.draw+'% · Away '+m.away+'%':'',
m?'Data quality: '+m.quality.toUpperCase()+' (coverage and freshness, not accuracy)':'',
p?'Likely score: '+p.most_likely_score+' · Samples: '+p.home_samples+' / '+p.away_samples:'',
result?result.analysis.summary:'',result?result.analysis.explanation:''].filter(Boolean).join('\n');
}catch(e){}setTimeout(pollAI,2000)}pollAI();
document.querySelector('#ai-setup').addEventListener('submit',async e=>{e.preventDefault();try{
await post('/api/ai/configure',{api_key:document.querySelector('#api-key').value,model:document.querySelector('#ai-model').value,enabled:document.querySelector('#ai-enabled').checked});
document.querySelector('#api-key').value='';message('AI settings saved. Analysis will run when verified data is available.');
}catch(e){message(e.message)}});
document.querySelector('#ai-generate').onclick=async()=>{try{await post('/api/ai/generate',{});message('Prediction requested. The existing 24-hour result is reused when available.')}catch(e){message(e.message)}};
</script></html>"""


def serve_setup(device, frame_url, port=8780, root=None):
    # The page and POST handlers are loopback-only and protected against cross-site requests.
    token, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(20)
    ai = AISettings(root or Path.cwd())
    preview = frame_url.rsplit("/v1/frame.bin", 1)[0].replace(urlsplit(frame_url).hostname, "127.0.0.1")
    page = (PAGE.replace("NONCE", nonce).replace("FRAME_URL", frame_url)
            .replace("PREVIEW_URL", preview).replace("TOKEN", json.dumps(token))).encode()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # Never log request bodies, credentials or provisioning commands.

        def reply(self, status, body, kind="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'none'; "
                             f"script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; "
                             "connect-src 'self'; form-action 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/":
                self.reply(200, page, "text/html; charset=utf-8")
            elif self.path == "/api/status":
                self.reply(200, device.read())
            elif self.path == "/api/ai/status":
                self.reply(200, ai.status())
            else:
                self.reply(404, {"error": "not_found"})

        def do_POST(self):
            if not secrets.compare_digest(self.headers.get("X-Matchday-Ink-Token", ""), token):
                self.reply(403, {"error": "Invalid setup request."})
                return
            try:
                size = int(self.headers.get("Content-Length", 0))
                if not 0 < size <= 2048:
                    raise ValueError("Invalid request size.")
                data = json.loads(self.rfile.read(size))
                if self.path == "/api/ai/configure":
                    ai.save(data.get("api_key", ""), data.get("model"), data.get("enabled"))
                    self.reply(202, {"saved": True})
                    return
                elif self.path == "/api/ai/generate":
                    config = ai.config()
                    if not config.get("enabled") or not config.get("api_key"):
                        raise ValueError("Save an API key and enable AI analysis first.")
                    ai.request(manual=True)
                    self.reply(202, {"queued": True})
                    return
                elif self.path == "/api/configure":
                    command = config_command(data.get("ssid"), data.get("password"),
                                             data.get("frame_url"), data.get("refresh_seconds", 0))
                elif self.path == "/api/scan":
                    command = b"MATCHDAY_INK_SCAN\n"
                elif self.path == "/api/interval":
                    seconds = data.get("refresh_seconds")
                    if type(seconds) is not int or (seconds != 0 and not 180 <= seconds <= 86400):
                        raise ValueError("Choose kickoff mode (0) or a check interval of 180–86400 seconds.")
                    command = f"MATCHDAY_INK_INTERVAL {seconds}\n".encode()
                elif self.path == "/api/refresh":
                    command = b"MATCHDAY_INK_REFRESH\n"
                elif self.path == "/api/redraw":
                    command = b"MATCHDAY_INK_REDRAW\n"
                else:
                    self.reply(404, {"error": "not_found"})
                    return
                device.send(command)
                self.reply(202, {"queued": True})
            except (ValueError, TypeError, AttributeError, RuntimeError) as exc:
                self.reply(400, {"error": str(exc)})

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    device.worker.start()
    LOG.info("Wi-Fi setup: http://127.0.0.1:%d", server.server_port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        device.stop.set()
        server.server_close()
        device.worker.join(timeout=3)


def main():
    parser = argparse.ArgumentParser(description="Private local Wi-Fi setup over USB")
    parser.add_argument("--serial-port")
    parser.add_argument("--frame-url", required=True)
    parser.add_argument("--port", type=int, default=8780)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    serve_setup(Device(args.serial_port), args.frame_url, args.port, args.project)


if __name__ == "__main__":
    main()
