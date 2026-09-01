# Copyright (c) 2018 Khor Chin Heong (koochyrat@gmail.com)
# Copyright (c) 2025 Ingo de Jager (ingodejager@gmail.com)
# Copyright (c) 2026 Cytech Technology Pte Ltd
#
# Original project code by Khor Chin Heong.
# Modifications in 2025 by Ingo de Jager.
# Further modifications and enhancements in 2026 by Cytech Technology Pte Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

#!/usr/bin/env python3
"""
Cytech Comfort add-on Ingress Web UI 

- Upload CCLX -> validate -> apply
- Stores active file in /data/site.cclx and backup in /data/site.cclx.bak
- Atomic apply + rollback on failure
- Tracks discovery topics to clear stale entities on next apply
"""

# Standard library imports
import hashlib
import html
import json
import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# Logging setup import only
from logging_config import setup_ram_logging

# Third-party imports
import paho.mqtt.client as mqtt
from flask import Flask, Response, redirect, request, send_file
from flask import url_for as flask_url_for
from markupsafe import escape

# Project imports
from options import load_options, get_str, get_int, get_bool
from mqtt_tls import configure_client_tls

_opts = load_options()

log_verbosity = get_str(_opts, "log_verbosity", "INFO").upper()

if log_verbosity not in ["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"]:
    log_verbosity = "INFO"

setup_ram_logging(
    level=getattr(logging, log_verbosity, logging.INFO)
)

logger = logging.getLogger("webapp")
logging.getLogger("werkzeug").disabled = True

logger.debug("Web UI RAM logging initialised at %s", log_verbosity)

import cclx_parser
import settings


# ---- Paths (use /data for production persistence) ----
DATA_DIR = Path("/data")
ACTIVE_CCLX = DATA_DIR / "site.cclx"
UPLOAD_CCLX = DATA_DIR / "upload.cclx"
BACKUP_CCLX = DATA_DIR / "site.cclx.bak"
LOCK_FILE = DATA_DIR / ".apply.lock"
RELOAD_FLAG = DATA_DIR / "reload.flag"
UPLOAD_META = DATA_DIR / "upload.meta.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)
RAM_LOG_FILE = Path("/dev/shm/cytech_comfort_mqtt.log")

app = Flask(__name__)


DOMAIN = settings.DOMAIN
RELOAD_TOPIC = f"{DOMAIN}/reload"

PASSTHROUGH_TOPIC = f"{DOMAIN}/passthrough/set"
PASSTHROUGH_STATE_FILE = DATA_DIR / "passthrough_mode.json"
passthrough_enabled = get_bool(_opts, "passthrough_enabled", False)


def _get_passthrough_mode() -> bool:
    try:
        if PASSTHROUGH_STATE_FILE.exists():
            state = json.loads(
                PASSTHROUGH_STATE_FILE.read_text(encoding="utf-8")
            )
            return state.get("active", False)
    except Exception:
        logger.exception("Failed reading passthrough state")

    return False


def _set_passthrough_mode(active: bool) -> None:
    PASSTHROUGH_STATE_FILE.write_text(
        json.dumps({"active": active}),
        encoding="utf-8"
    )

    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

    if settings.MQTTUSERNAME:
        c.username_pw_set(settings.MQTTUSERNAME, settings.MQTTPASSWORD or "")

    configure_client_tls(
        c,
        enabled=settings.MQTT_TLS_ENABLED,
        mutual_tls=settings.MQTT_MUTUAL_TLS,
        ca_filename=settings.MQTT_CA_CERT,
        client_cert_filename=settings.MQTT_CLIENT_CERT,
        client_key_filename=settings.MQTT_CLIENT_KEY,
    )

    c.connect(settings.MQTTBROKER, settings.MQTTPORT, 10)

    c.publish(
        PASSTHROUGH_TOPIC,
        "ON" if active else "OFF",
        qos=1,
        retain=False,
    )

    c.disconnect()


def mqtt_publish_reload(reason: str | None = None) -> None:
    logger.warning("MQTT reload publish requested | topic=%s | reason=%s", RELOAD_TOPIC, reason)
    logger.warning(
        "MQTT connection params | host=%s | port=%s | user=%s | password_set=%s | domain=%s",
        settings.MQTTBROKER, settings.MQTTPORT, settings.MQTTUSERNAME, bool(settings.MQTTPASSWORD), DOMAIN
    )

    connected = threading.Event()
    conn_rc = {"rc": None}

    def _on_connect(client, userdata, flags, reason_code, properties):
        # reason_code is a ReasonCode object in callback API v2
        rc_val = getattr(reason_code, "value", reason_code)
        logger.debug("MQTT on_connect reason_code=%s (value=%s)", reason_code, rc_val)
        conn_rc["rc"] = rc_val
        if rc_val == 0:
            connected.set()

    def _on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
        rc_val = getattr(reason_code, "value", reason_code)
        logger.debug("MQTT on_disconnect reason_code=%s (value=%s) flags=%s", reason_code, rc_val, disconnect_flags)

    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    c.on_connect = _on_connect
    c.on_disconnect = _on_disconnect

    if settings.MQTTUSERNAME:
        c.username_pw_set(settings.MQTTUSERNAME, settings.MQTTPASSWORD or "")
        logger.debug("MQTT auth configured (username provided)")
    else:
        logger.debug("MQTT auth not configured")


    configure_client_tls(
        c,
        enabled=settings.MQTT_TLS_ENABLED,
        mutual_tls=settings.MQTT_MUTUAL_TLS,
        ca_filename=settings.MQTT_CA_CERT,
        client_cert_filename=settings.MQTT_CLIENT_CERT,
        client_key_filename=settings.MQTT_CLIENT_KEY,
    )

    c.loop_start()
    try:
        logger.debug("Connecting to MQTT broker...")
        c.connect_async(settings.MQTTBROKER, settings.MQTTPORT, keepalive=10)

        if not connected.wait(timeout=10.0):
            raise RuntimeError("MQTT connect did not complete (timeout waiting for on_connect)")

        if conn_rc["rc"] != 0:
            raise RuntimeError(f"MQTT connect refused reason_code={conn_rc['rc']}")

        payload = {"reason": reason or "webui"}
        logger.debug("Publishing payload: %s", payload)
        info = c.publish(RELOAD_TOPIC, json.dumps(payload), qos=1, retain=False)

        info.wait_for_publish(timeout=5.0)
        logger.debug(
            "Publish result | rc=%s | mid=%s | is_published=%s",
            info.rc, getattr(info, "mid", None), info.is_published()
        )

        if info.rc != mqtt.MQTT_ERR_SUCCESS or not info.is_published():
            raise RuntimeError(f"MQTT publish did not complete (rc={info.rc}, published={info.is_published()})")

    finally:
        try:
            c.disconnect()
        except Exception:
            logger.exception("MQTT disconnect failed")
        c.loop_stop()

# ----------------------------
# Utility helpers
# ----------------------------

def url_for(endpoint, **values):
    prefix = request.headers.get("X-Ingress-Path") or request.script_root or ""
    return prefix + flask_url_for(endpoint, **values)

def _sha256_file(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()



def _atomic_replace(src: Path, dst: Path) -> None:
    # Atomic on Linux if same filesystem
    tmp = dst.with_suffix(dst.suffix + ".tmp")
    tmp.write_bytes(src.read_bytes())
    os.sync()
    tmp.replace(dst)

def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")

def _html(page_title: str, body: str) -> Response:
    # Keep links relative for ingress (no leading absolute URLs)
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{page_title}</title>
  <base href="./">
  <style>
    body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 18px; }}
    .card {{ border: 1px solid #ddd; border-radius: 12px; padding: 14px; margin: 12px 0; }}
    .row {{ display: flex; gap: 12px; flex-wrap: wrap; }}
    .pill {{ display:inline-block; padding: 2px 10px; border-radius: 999px; background:#f2f2f2; }}
    code, pre {{ background:#f6f6f6; padding: 2px 6px; border-radius: 6px; }}
    pre {{ padding: 10px; overflow: auto; max-height: 70vh; white-space: pre-wrap; }}
    .btn {{ padding: 10px 14px; border-radius: 10px; border: 1px solid #ccc; background: #fff; cursor: pointer; }}
    .btn-primary {{ border-color: #333; }}
    .warn {{ color: #8a4b00; }}
    .err {{ color: #a40000; }}
    .ok {{ color: #0a6; }}
  </style>
</head>
<body>
<h2>{page_title}</h2>
{body}
</body>
</html>"""
    return Response(html, mimetype="text/html")

def _try_parse_cclx(path: Path) -> Tuple[bool, str, Dict[str, Any]]:
    try:
        if hasattr(cclx_parser, "parse_cclx"):
            # Minimal validators for UI validation phase
            def check_zone_name(name: str) -> bool:
                return isinstance(name, str) and len(name) > 0

            def check_index_number(value: str, max_index: int) -> bool:
                if not value:
                    return False
                try:
                    n = int(value)
                    return 0 <= n <= max_index
                except ValueError:
                    return False

            result = cclx_parser.parse_cclx(
                path,
                device_properties_in={},
                check_zone_name=check_zone_name,
                check_index_number=check_index_number,
                logger=app.logger,
            )

            # Convert dataclass result into readable summary
            summary = {
                "found": result.found,
                "flags": result.flags.__dict__,
                "zones": len(result.input_properties),
                "counters": len(result.counter_properties),
                "flags_count": len(result.flag_properties),
                "outputs": len(result.output_properties),
                "sensors": len(result.sensor_properties),
                "timers": len(result.timer_properties),
                "users": len(result.user_properties),
            }

            return True, "Parsed OK", summary

        return False, "No parse_cclx() found in cclx_parser.py", {}

    except Exception as e:
        return False, f"{type(e).__name__}: {e}", {}


def _normalise_summary(summary: Any) -> Dict[str, Any]:
    """
    Make a nice human-readable summary even if parser returns different structures.
    """
    if isinstance(summary, dict):
        return summary
    return {"summary": str(summary)}


def _read_upload_meta() -> Dict[str, Any]:
    if not UPLOAD_META.exists():
        return {}
    try:
        return json.loads(UPLOAD_META.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _file_info(path: Path) -> dict:
    if not path.exists():
        return {"exists": False}

    st = path.stat()
    return {
        "exists": True,
        "size": st.st_size,
        "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(sep=" ", timespec="seconds"),
        "sha256": _sha256_file(path),
    }

def _file_preview_text(path: Path, max_bytes: int = 4096) -> str:
    """
    Return a small text preview for UI display.
    Uses UTF-8 with replacement so it won't crash on odd encodings.
    """
    if not path.exists():
        return ""

    data = path.read_bytes()[:max_bytes]
    text = data.decode("utf-8", errors="replace")

    # Keep it readable in HTML
    return text


def _ingress_prefix() -> str:
    # HA ingress proxy usually provides one of these
    return (
        request.headers.get("X-Ingress-Path")
        or request.script_root
        or ""
    )

def ingress_url(endpoint: str, **values) -> str:
    return _ingress_prefix() + url_for(endpoint, **values)

class ApplyLock:
    def __init__(self, lock_path: Path):
        self.lock_path = lock_path
        self.fd = None

    def __enter__(self):
        # Simple exclusive lock using lock file creation
        # (good enough for single-container ingress UI)
        start = time.time()
        while True:
            try:
                self.fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self.fd, str(os.getpid()).encode("utf-8"))
                return self
            except FileExistsError:
                if time.time() - start > 10:
                    raise RuntimeError("Another apply is in progress. Try again.")
                time.sleep(0.2)

    def __exit__(self, exc_type, exc, tb):
        try:
            if self.fd is not None:
                os.close(self.fd)
            if self.lock_path.exists():
                self.lock_path.unlink()
        except Exception:
            pass

# ----------------------------
# Routes
# ----------------------------


@app.get("/")
def home():
    active_sha = _sha256_file(ACTIVE_CCLX)
    backup_sha = _sha256_file(BACKUP_CCLX)

    upload_info = _file_info(UPLOAD_CCLX)
    upload_meta = _read_upload_meta()

    notice = request.args.get("notice")
    banner_html = ""

    if notice == "uploaded":
        name = request.args.get("name", "")
        size = request.args.get("size", "")
        when = request.args.get("when", "")
        sha = request.args.get("sha", "")

        banner_html = f"""
<div class="card" style="border-color:#0a6;">
  <div class="ok"><strong>Upload complete</strong></div>
  <div>File: <code>{html.escape(name)}</code></div>
  <div>Size: <code>{html.escape(size)}</code> bytes</div>
  <div>Time: <code>{html.escape(when)}</code></div>
  <div>SHA256: <code>{html.escape(sha)}</code></div>
</div>
"""

    passthrough_html = ""

    if passthrough_enabled:
        mode_text = (
            "Comfigurator Maintenance Mode"
            if _get_passthrough_mode()
            else "Normal MQTT Mode"
        )

        passthrough_html = f"""
<div class="card" style="border-color:#333;">
  <div><strong>1) Comfort Bridge Mode</strong></div>
  <div style="margin-top:8px;">
    Current mode: <span class="pill">{mode_text}</span>
  </div>

  <div class="warn" style="margin-top:10px;">
    <div>In Comfigurator Maintenance Mode, Home Assistant stops communicating with Comfort.</div>
    <div>Connect Comfigurator to Comfort using the Home Assistant IP address on port 10001.</div>
    <div>Return to Normal MQTT Mode when finished.</div>
  </div>

  <div class="row" style="margin-top:12px;">
    <form method="post" action="./passthrough/enable" style="display:inline;">
      <button class="btn" type="submit">Enable Comfigurator Mode</button>
    </form>

    <form method="post" action="./passthrough/disable" style="display:inline;">
      <button class="btn btn-primary" type="submit">Return to Normal MQTT Mode</button>
    </form>
  </div>
</div>
"""

    body = f"""
{passthrough_html}

<div class="card">
  <div><strong>Logs</strong></div>
  <div>View the live RAM log for bridge, web UI and passthrough activity.</div>
  <div class="row" style="margin-top:10px;">
    <a class="btn btn-primary" href="{url_for('view_log')}">Open Logs</a>
    <a class="btn" href="{url_for('download_log')}">Download Full Log</a>
  </div>
</div>

<div class="card">
  <div><strong>3) CCLX Configuration</strong></div>
  <div class="warn" style="margin-top:6px;">
    Use this section to upload, validate and apply a Comfort CCLX file.
  </div>
</div>


<div class="card" id="cclx-status">
  <div><strong>CCLX Status</strong></div>
  <div>Time: <span class="pill">{_now()}</span></div>
  <div>Active CCLX: {"<span class='ok'>present</span>" if ACTIVE_CCLX.exists() else "<span class='warn'>missing</span>"}</div>
  <div>Uploaded CCLX: {"<span class='ok'>present</span>" if upload_info.get("exists") else "<span class='warn'>none</span>"}</div>
  <div>Reload pending: {"<span class='warn'>yes</span>" if RELOAD_FLAG.exists() else "<span class='ok'>no</span>"}</div>
  <div>Backup: {"<span class='ok'>present</span>" if BACKUP_CCLX.exists() else "<span class='warn'>none</span>"}</div>

  <details style="margin-top:10px;">
    <summary>Show advanced CCLX details</summary>
    <div style="margin-top:8px;">
      <div>Active SHA256: <code>{active_sha or "-"}</code></div>
      {f"<div>Original filename: <code>{html.escape(str(upload_meta.get('original_filename','-')))}</code></div>" if upload_meta else ""}
      {f"<div>Uploaded at: <code>{html.escape(str(upload_meta.get('uploaded_at','-')))}</code></div>" if upload_meta else ""}
      {f"<div>Type: <code>{html.escape(str(upload_meta.get('content_type','-')))}</code></div>" if upload_meta else ""}
      <div>Upload path: <code>{UPLOAD_CCLX}</code></div>
      <div>Upload size: <code>{upload_info.get("size","-")}</code> bytes</div>
      <div>Upload modified: <code>{upload_info.get("mtime","-")}</code></div>
      <div>Upload SHA256: <code>{upload_info.get("sha256") or "-"}</code></div>
      <div>Backup SHA256: <code>{backup_sha or "-"}</code></div>
    </div>
  </details>

  {f"<div class='row' style='margin-top:10px;'><a class='btn' href='{url_for('download')}'>Download uploaded CCLX</a></div>" if upload_info.get("exists") else ""}
</div>

<div class="card">
  <div><strong>Upload CCLX</strong></div>
  <form method="post" action="./upload" enctype="multipart/form-data" style="margin-top:10px;">
    <input type="file" name="file" accept=".cclx,.txt" required />
    <button class="btn btn-primary" type="submit">Upload</button>
  </form>
</div>

{banner_html}
<div class="card" id="validate-cclx">
  <div><strong>Validate uploaded CCLX</strong></div>
  <form method="post" action="./validate" style="margin-top:10px;">
    <button class="btn" type="submit">Validate</button>
  </form>
</div>

<div class="card" id="apply-cclx">
  <div><strong>Apply CCLX</strong></div>
  <div class="warn">
    This will clear old MQTT discovery entities and recreate them from the uploaded CCLX.
  </div>
  <div>The bridge will reload the CCLX and rebuild MQTT discovery within a few seconds.</div>
  <form method="post" action="./apply" style="margin-top:10px;">
    <button class="btn btn-primary" type="submit">Apply</button>
  </form>
</div>

<div class="card">
  <div><strong>Rollback</strong></div>
  <form method="post" action="./rollback" style="margin-top:10px;">
    <button class="btn" type="submit">Rollback to previous active</button>
  </form>
</div>
"""
    return _html("Cytech Comfort Add-on", body)

@app.post("/passthrough/enable")
def enable_passthrough():
    _set_passthrough_mode(True)
    return redirect(url_for("home"))


@app.post("/passthrough/disable")
def disable_passthrough():
    _set_passthrough_mode(False)
    return redirect(url_for("home"))



@app.post("/upload")
def upload():
    f = request.files.get("file")
    if not f or not f.filename:
        return _html("Upload failed",
                    f"<p class='err'>No file selected.</p><p><a href='{url_for('home')}'>Back</a></p>"), 400

    if not f.filename.lower().endswith((".cclx", ".txt")):
        return _html("Upload failed",
                     f"<p class='err'>File must be .cclx (or .txt).</p><p><a href='{url_for('home')}'>Back</a></p>"), 400

    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)

        tmp_path = UPLOAD_CCLX.with_suffix(".cclx.uploading")
        app.logger.debug("UPLOAD: saving '%s' -> tmp=%s final=%s",
                           f.filename, str(tmp_path), str(UPLOAD_CCLX))
        if tmp_path.exists():
            tmp_path.unlink()
        # Save to tmp then atomic rename
        f.save(str(tmp_path))
        os.replace(str(tmp_path), str(UPLOAD_CCLX))

        # Verify
        st = UPLOAD_CCLX.stat()
        app.logger.debug("UPLOAD: saved OK path=%s size=%d bytes", str(UPLOAD_CCLX), st.st_size)

        if st.st_size == 0:
            raise RuntimeError("Saved file is 0 bytes (empty upload)")

        # --- Save upload metadata for UI (original filename, timestamps, etc.) ---
        meta = {
            "original_filename": f.filename,
            "stored_path": str(UPLOAD_CCLX),
            "size_bytes": st.st_size,
            "sha256": _sha256_file(UPLOAD_CCLX),
            "uploaded_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
            "content_type": f.mimetype,
        }
        UPLOAD_META.write_text(json.dumps(meta, indent=2), encoding="utf-8")

        # Redirect back with a one-time success banner
        app.logger.debug("UPLOAD: redirecting to home with notice=uploaded")
        return redirect(
            url_for(
                "home",
                notice="uploaded",
                name=meta["original_filename"],
                size=str(meta["size_bytes"]),
                when=meta["uploaded_at"],
                sha=meta["sha256"],
            ) + "#validate-cclx"
        )   
 
    except Exception as e:
        msg = escape(str(e))
        return _html(
            "Upload failed",
            (
                f"<p class='err'>Upload failed: {type(e).__name__}: {msg}</p>"
                f"<p><a href='{url_for('home')}'>Back</a></p>"
            ),
        ), 500


@app.get("/download")
def download():
    if not UPLOAD_CCLX.exists():
        return _html(
            "Download",
            f"<p class='err'>No uploaded CCLX staged. Upload first.</p><p><a href='{url_for('home')}'>Back</a></p>"
        ), 404

    meta = _read_upload_meta()
    dl_name = meta.get("original_filename") if isinstance(meta.get("original_filename"), str) else None
    if not dl_name:
        dl_name = "comfort.cclx"

    return send_file(
        str(UPLOAD_CCLX),
        as_attachment=True,
        download_name=dl_name,
        mimetype="application/octet-stream",
        conditional=True,
    )



@app.post("/validate")
def validate():
    if not UPLOAD_CCLX.exists():
        return _html("Validate", f"<p class='err'>No uploaded CCLX staged. Upload first.</p><p><a href='{url_for('home')}'>Back</a></p>"), 400

    ok, msg, summary = _try_parse_cclx(UPLOAD_CCLX)
    if not ok:
       return _html("Validate", f"<p class='err'>Validation failed: {msg}</p><p><a href='{url_for('home')}'>Back</a></p>"), 400

    
    return _html(
        "Validate",
        f"""
        <p class='ok'>Validation OK: {msg}</p>

        <p>
        <a href='{url_for("home")}#apply-cclx'>
            Continue to Apply
        </a>
        </p>
        """
    )


@app.post("/apply")
def apply():
    if not UPLOAD_CCLX.exists():
        return _html("Apply", f"<p class='err'>No uploaded CCLX staged. Upload first.</p><p><a href='{url_for('home')}'>Back</a></p>"), 400

    with ApplyLock(LOCK_FILE):
        # Validate again just before applying
        ok, msg, summary = _try_parse_cclx(UPLOAD_CCLX)
        if not ok:
            return _html("Apply", f"<p class='err'>Validation failed: {msg}</p><p><a href='{url_for('home')}'>Back</a></p>"), 400

        # Backup current active
        if ACTIVE_CCLX.exists():
            BACKUP_CCLX.write_bytes(ACTIVE_CCLX.read_bytes())

        # Activate uploaded file atomically
        _atomic_replace(UPLOAD_CCLX, ACTIVE_CCLX)

    # Production-critical: clear stale discovery entities and recreate from CCLX
    try:
        # Signal the running bridge to reload CCLX and rebuild discovery (MQTT)
        mqtt_publish_reload(reason="cclx_applied")
    except Exception as e:
        # Rollback active file if discovery rebuild fails
        if BACKUP_CCLX.exists():
            _atomic_replace(BACKUP_CCLX, ACTIVE_CCLX)
        return _html(
            "Apply",
            f"<p class='err'>Apply failed (rolled back): {type(e).__name__}: {e}</p><p><a href='{url_for('home')}'>Back</a></p>"
        ), 500
   
    return _html(
    "Apply complete",
    f"""
    <p class='ok'>Applied successfully at {_now()}.</p>

    <p>
      <a href="{url_for('home')}#cclx-status">
        Return to CCLX Status
      </a>
    </p>
    """
)


@app.post("/rollback")
def rollback():
    if not BACKUP_CCLX.exists():
        return _html("Rollback", f"<p class='err'>No backup available.</p><p><a href='{url_for('home')}'>Back</a></p>"), 400

    with ApplyLock(LOCK_FILE):
        _atomic_replace(BACKUP_CCLX, ACTIVE_CCLX)

        # Signal the running bridge to reload and rebuild discovery
        try:
            RELOAD_FLAG.write_text(str(int(time.time())), encoding="utf-8")
        except Exception as e:
            return _html(
                "Rollback",
                f"<p class='warn'>Rolled back file, but reload signalling failed: {type(e).__name__}: {e}</p><p><a href='{url_for('home')}'>Back</a></p>"
            ), 500

    return _html("Rollback", f"<p class='ok'>Rollback complete at {_now()}.</p><p><a href='{url_for('home')}'>Back</a></p>")


@app.get("/mqtt")
def view_mqtt():
    mqtt_security = get_str(
        _opts,
        "mqtt_security",
        "password",
    ).strip().lower()

    mqtt_port = 8883 if mqtt_security in {
        "tls",
        "mutual_tls",
    } else 1883

    mode_names = {
        "password": "Password",
        "tls": "TLS",
        "mutual_tls": "Mutual TLS",
    }

    mode_text = mode_names.get(
        mqtt_security,
        mqtt_security,
    )

    body = f"""
<div class="card">
  <div><strong>Cytech Comfort Add-on</strong></div>

  <div class="row" style="margin-top:10px;">
    <a class="btn" href="{url_for('home')}">CCLX</a>
    <a class="btn" href="{url_for('view_log')}">Logs</a>
    <a class="btn btn-primary" href="{url_for('view_mqtt')}">MQTT</a>
  </div>
</div>

<div class="card">
  <div><strong>MQTT Security</strong></div>

  <p>
    The Cytech Comfort add-on can connect to the Mosquitto MQTT
    broker using password authentication, TLS, or mutual TLS.
  </p>

  <div>
    Current Comfort MQTT security mode:
    <span class="pill">{html.escape(mode_text)}</span>
  </div>

  <div style="margin-top:8px;">
    MQTT port: <code>{mqtt_port}</code>
  </div>
</div>

<div class="card">
  <div><strong>CA Certificate</strong></div>

  <p>
    When TLS is enabled, the Mosquitto broker uses a certificate
    issued by a certificate authority unique to this Home Assistant
    installation.
  </p>

  <p>
    Other MQTT applications connecting securely to this broker on
    port 8883 may need the CA certificate so that they can verify
    the broker certificate.
  </p>

  <p>
    The CA certificate can be downloaded from this page.
  </p>

  <div class="warn">
    Only the public CA certificate is provided. Private certificate
    keys are not made available through the Web UI.
  </div>
</div>
"""

    return _html("Cytech Comfort MQTT", body)



@app.get("/log/raw")
def raw_log():
    if not RAM_LOG_FILE.exists():
        return Response("", mimetype="text/plain")

    text = RAM_LOG_FILE.read_text(encoding="utf-8", errors="replace")
    return Response(text[-200000:], mimetype="text/plain")


@app.get("/log")
def view_log():
    if not RAM_LOG_FILE.exists():
        return _html(
            "Cytech Comfort Logs",
            f"<p class='warn'>No RAM log file exists yet.</p>"
            f"<p><a href='{url_for('home')}'>Back</a></p>"
        ), 404

    text = RAM_LOG_FILE.read_text(encoding="utf-8", errors="replace")
    safe_text = html.escape(text[-200000:])

    actual_bytes = len(safe_text.encode("utf-8"))

    body = f"""
<div class="card">
  <div><strong>Cytech Comfort Add-on</strong></div>
  <div class="row" style="margin-top:10px;">
    <a class="btn" href="{url_for('home')}">CCLX</a>
    <a class="btn btn-primary" href="{url_for('view_log')}">Logs</a>
    <a class="btn" href="{url_for('view_mqtt')}">MQTT</a>
    </div>
</div>

<div class="card">
  <div><strong>RAM log file</strong></div>
  <div>Path: <code>{RAM_LOG_FILE}</code></div>
  <div>
  Showing <code>{actual_bytes}</code> bytes
  (maximum view: 200 KB).
</div>
  


  <div class="row" style="margin-top:10px;">
    <button class="btn btn-primary" type="button" onclick="refreshLog()">Refresh</button>
    <button class="btn" type="button" id="autoRefreshLogBtn" onclick="toggleLogAutoRefresh()">Auto refresh: OFF</button>
    <button class="btn" type="button" id="reverseLogBtn" onclick="toggleLogReverse()">Latest first: OFF</button>
    <a class="btn" href="{url_for('download_log')}">Download full log</a>

    <form method="post" action="{url_for('clear_log')}" style="display:inline;">
      <button class="btn" type="submit">Clear log</button>
    </form>
  </div>
</div>

<div class="card">
  <pre id="logOutput">{safe_text}</pre>
</div>

<script>
  let logAutoRefreshTimer = null;
  let logReversed = false;
  const rawLogUrl = "{url_for('raw_log')}";

  function renderLog(text) {{
    const logBox = document.getElementById("logOutput");
    let displayText = text || "";

    if (logReversed) {{
      displayText = displayText.split("\\n").reverse().join("\\n");
    }}

    logBox.textContent = displayText;

    if (logReversed) {{
      logBox.scrollTop = 0;
    }} else {{
      logBox.scrollTop = logBox.scrollHeight;
    }}
  }}

  function refreshLog() {{
    fetch(rawLogUrl, {{ cache: "no-store" }})
      .then(response => response.text())
      .then(text => renderLog(text))
      .catch(error => console.error("Failed to refresh log:", error));
  }}

  function toggleLogAutoRefresh() {{
    const btn = document.getElementById("autoRefreshLogBtn");

    if (logAutoRefreshTimer) {{
      clearInterval(logAutoRefreshTimer);
      logAutoRefreshTimer = null;
      btn.textContent = "Auto refresh: OFF";
      return;
    }}

    refreshLog();
    logAutoRefreshTimer = setInterval(refreshLog, 2000);
    btn.textContent = "Auto refresh: ON";
  }}

  function toggleLogReverse() {{
    const btn = document.getElementById("reverseLogBtn");

    logReversed = !logReversed;
    btn.textContent = logReversed ? "Latest first: ON" : "Latest first: OFF";

    refreshLog();
  }}
</script>
"""
    return _html("Cytech Comfort Logs", body)

@app.get("/log/download")
def download_log():
    if not RAM_LOG_FILE.exists():
        return _html("Download Log", f"<p class='warn'>No RAM log file exists yet.</p><p><a href='{url_for('home')}'>Back</a></p>"), 404

    return send_file(
        str(RAM_LOG_FILE),
        as_attachment=True,
        download_name="cytech_comfort_mqtt.log",
        mimetype="text/plain",
        conditional=True,
    )


@app.post("/log/clear")
def clear_log():
    RAM_LOG_FILE.write_text("", encoding="utf-8")
    logger.debug("RAM log cleared from Web UI")
    return redirect(url_for("view_log"))  

if __name__ == "__main__":
    # Ingress requires binding to 0.0.0.0
    app.run(host="0.0.0.0", port=8099)