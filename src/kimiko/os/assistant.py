"""Kimiko OS Assistant — Phase 8: Advanced Intelligence.

Features:
  - Multi-monitor awareness (thumbnails for all screens)
  - System context (running processes, CPU/RAM/Disk)
  - Memory bridge (facts + chat history from Kimiko API)
  - Expanded local HTTP bridge for Electron UI
"""

import sys
import base64
import io
import json
import os
import re
import subprocess
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

import httpx
import keyboard
import mss
import psutil
import pyperclip
import pygetwindow as gw
from PIL import Image

from kimiko.config import get_settings
from kimiko.os.screen_context import ScreenContextEngine
from kimiko.os.command_executor import CommandExecutor
from kimiko.os.automation_executor import AutomationExecutor
from kimiko.tools.os_filesystem import OSFileSystem

settings = get_settings()

# ── Security ──
SENSITIVE_PATTERNS = [
    r'(?i)password\s*[:=]\s*\S+',
    r'(?i)secret\s*[:=]\s*\S+',
    r'(?i)api_key\s*[:=]\s*\S+',
    r'\b(?:\d[ -]*?){13,16}\b',
]

# ── Shared State ──
STATE = {
    "active_window": "Unknown",
    "clipboard": "",
    "screenshot": None,        # Active monitor full screenshot (base64)
    "monitors": [],            # List of {id, name, width, height, thumbnail}
    "processes": [],           # Top processes [{name, pid, cpu, memory}]
    "resources": {},           # {cpu, ram, disk}
    "screen_details": {},      # {visible_text, ui_elements, active_app}
    "pending_action": None,    # {id, type, command, content, status}
    "action_results": {},      # {action_id: {stdout, stderr, success, exit_code}}
    "terminal_history": [],    # List of {command, timestamp, status, result_preview}
    "suggestions": [],         # Proactive suggestions queue
    "last_response": "",
    "query": None,
    "session_id": "os-assistant",
}

OS_USER_ID = "00000000-0000-0000-0000-000000000001"


def _get_pending_suggestion():
    for suggestion in reversed(STATE["suggestions"]):
        if suggestion.get("status") == "pending":
            return suggestion
    return None


def _dismiss_suggestion(suggestion_id=None):
    if suggestion_id:
        for suggestion in STATE["suggestions"]:
            if suggestion.get("id") == suggestion_id and suggestion.get("status") == "pending":
                suggestion["status"] = "dismissed"
                suggestion["dismissed_at"] = int(time.time())
                return suggestion_id
        return None

    pending = _get_pending_suggestion()
    if not pending:
        return None
    pending["status"] = "dismissed"
    pending["dismissed_at"] = int(time.time())
    return pending.get("id")


class InsightEngine:
    """Background detector that proposes proactive suggestions from live screen text."""

    def __init__(self, poll_interval=4, cooldown_seconds=45, max_suggestions=20):
        self.poll_interval = poll_interval
        self.cooldown_seconds = cooldown_seconds
        self.max_suggestions = max_suggestions
        self._last_seen = {}
        self._patterns = [
            {
                "kind": "python_traceback",
                "title": "Python Traceback Detected",
                "regex": re.compile(r"Traceback \(most recent call last\):", re.IGNORECASE),
                "message": "I noticed a Python traceback on screen and can help identify the root cause.",
                "suggested_query": "Analyze the traceback on my screen and suggest a fix.",
            },
            {
                "kind": "module_not_found",
                "title": "Missing Python Module",
                "regex": re.compile(r"ModuleNotFoundError:\s*No module named ['\"][^'\"]+['\"]", re.IGNORECASE),
                "message": "A dependency appears to be missing. I can suggest the correct install command.",
                "suggested_query": "Fix the ModuleNotFoundError currently shown on screen.",
            },
            {
                "kind": "assertion_error",
                "title": "Assertion Failure Detected",
                "regex": re.compile(r"AssertionError\b", re.IGNORECASE),
                "message": "A test assertion failed. I can help isolate likely causes and propose a patch.",
                "suggested_query": "Explain the current AssertionError and propose a code fix.",
            },
            {
                "kind": "npm_error",
                "title": "Node Build Error Detected",
                "regex": re.compile(r"\bnpm ERR!\b|\bTypeError:\b|\bReferenceError:\b", re.IGNORECASE),
                "message": "A JavaScript or npm error is visible. I can suggest the next debugging step.",
                "suggested_query": "Analyze the JavaScript/npm error on screen and suggest a fix.",
            },
        ]

    def _enqueue_suggestion(self, pattern, matched_text):
        signature = f"{pattern['kind']}::{matched_text.strip().lower()[:180]}"
        now = time.time()
        last_ts = self._last_seen.get(signature, 0.0)
        if now - last_ts < self.cooldown_seconds:
            return
        self._last_seen[signature] = now

        pending_same_kind = [
            s for s in STATE["suggestions"]
            if s.get("status") == "pending" and s.get("kind") == pattern["kind"]
        ]
        if pending_same_kind:
            return

        suggestion = {
            "id": str(uuid.uuid4())[:8],
            "kind": pattern["kind"],
            "title": pattern["title"],
            "message": pattern["message"],
            "matched_text": matched_text[:240],
            "suggested_query": pattern["suggested_query"],
            "created_at": int(now),
            "status": "pending",
        }
        STATE["suggestions"].append(suggestion)
        STATE["suggestions"] = STATE["suggestions"][-self.max_suggestions:]

    def scan_once(self):
        visible_text = (STATE.get("screen_details", {}) or {}).get("visible_text", "") or ""
        clipboard = STATE.get("clipboard", "") or ""
        candidate = f"{visible_text}\n{clipboard}"
        if not candidate.strip():
            return

        for pattern in self._patterns:
            match = pattern["regex"].search(candidate)
            if match:
                self._enqueue_suggestion(pattern, match.group(0))

    def run_forever(self):
        while True:
            try:
                self.scan_once()
            except Exception as e:
                print(f"Insight loop error: {e}")
            time.sleep(self.poll_interval)


# ═══════════════════════════════════════════════════
#  IMAGE PROCESSOR
# ═══════════════════════════════════════════════════
class ImageProcessor:
    @staticmethod
    def process(sct_img, max_width=None) -> str:
        """Convert mss capture to base64 JPEG."""
        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        w = max_width or settings.os_screenshot_width
        if img.width > w:
            aspect = img.height / img.width
            img = img.resize((w, int(w * aspect)), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=settings.os_screenshot_quality)
        return base64.b64encode(buf.getvalue()).decode("utf-8")


# ═══════════════════════════════════════════════════
#  SYSTEM CONTEXT COLLECTOR
# ═══════════════════════════════════════════════════
class SystemContext:
    """Collects running processes, resources, and monitor info."""

    @staticmethod
    def get_processes(max_count=10):
        """Get top processes sorted by CPU usage."""
        procs = []
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            try:
                info = proc.info
                if info['cpu_percent'] is not None and info['name'] not in ('System Idle Process', 'System', ''):
                    procs.append({
                        "pid": info['pid'],
                        "name": info['name'],
                        "cpu": round(info['cpu_percent'], 1),
                        "memory": round(info['memory_percent'] or 0, 1),
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        procs.sort(key=lambda x: x['cpu'], reverse=True)
        return procs[:max_count]

    @staticmethod
    def get_resources():
        """Get system resource usage."""
        cpu = psutil.cpu_percent(interval=0)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        return {
            "cpu": round(cpu, 1),
            "ram": round(ram.percent, 1),
            "ram_used_gb": round(ram.used / (1024**3), 1),
            "ram_total_gb": round(ram.total / (1024**3), 1),
            "disk": round(disk.percent, 1),
            "disk_used_gb": round(disk.used / (1024**3), 1),
            "disk_total_gb": round(disk.total / (1024**3), 1),
        }

    @staticmethod
    def get_monitors():
        """Get all monitor info with thumbnails."""
        monitors = []
        try:
            with mss.mss() as sct:
                # sct.monitors[0] = virtual combined, [1..N] = individual
                for i, mon in enumerate(sct.monitors):
                    if i == 0:
                        continue  # Skip combined virtual monitor
                    try:
                        img = sct.grab(mon)
                        thumb = ImageProcessor.process(img, max_width=320)
                    except Exception:
                        thumb = None
                    monitors.append({
                        "id": i,
                        "name": f"Display {i}",
                        "width": mon["width"],
                        "height": mon["height"],
                        "left": mon["left"],
                        "top": mon["top"],
                        "thumbnail": thumb,
                    })
        except Exception as e:
            print(f"Monitor scan error: {e}")
        return monitors


# ═══════════════════════════════════════════════════
#  CONTEXT BRIDGE SERVER (HTTP on 127.0.0.1:8001)
# ═══════════════════════════════════════════════════
class ContextServer(BaseHTTPRequestHandler):
    """Local bridge between Python backend and Electron UI."""

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json_response(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/context":
            self._json_response({
                "window": STATE["active_window"],
                "clipboard": STATE["clipboard"][:200],
                "resources": STATE["resources"],
            })

        elif path == "/context/full":
            self._json_response({
                "window": STATE["active_window"],
                "clipboard": STATE["clipboard"],
                "resources": STATE["resources"],
                "screen": STATE["screen_details"],
            })

        elif path.startswith("/approval/result/"):
            action_id = path.split("/")[-1]
            result = STATE["action_results"].get(action_id)
            if result:
                self._json_response(result)
            else:
                self._json_response({"error": "Action result not found"}, 404)

        elif path == "/terminal/history":
            self._json_response({"history": STATE["terminal_history"]})

        elif path == "/files/list":
            # Simple list for the UI
            query = parse_qs(parsed.query)
            root = query.get("path", [os.path.expanduser("~")])[0]
            try:
                items = []
                for entry in os.scandir(root):
                    items.append({
                        "name": entry.name,
                        "is_dir": entry.is_dir(),
                        "size": entry.stat().st_size if entry.is_file() else 0,
                        "path": entry.path
                    })
                items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
                self._json_response({"items": items[:200], "path": root})
            except Exception as e:
                self._json_response({"error": str(e)}, 500)

        elif path == "/files/read":
            query = parse_qs(parsed.query)
            f_path = query.get("path", [""])[0]
            try:
                if not os.path.exists(f_path):
                    return self._json_response({"error": "File not found"}, 404)
                with open(f_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read(10000) # Limit to 10kb
                self._json_response({"content": content, "path": f_path})
            except Exception as e:
                self._json_response({"error": str(e)}, 500)

        elif path == "/system":
            self._json_response({
                "monitors": [{k: v for k, v in m.items() if k != "thumbnail"} for m in STATE["monitors"]],
                "processes": STATE["processes"],
                "resources": STATE["resources"],
                "active_window": STATE["active_window"],
            })

        elif path == "/monitors":
            # Returns monitors WITH thumbnails
            self._json_response({"monitors": STATE["monitors"]})

        elif path == "/memories":
            # Proxy to Kimiko API for stored facts
            try:
                host = "127.0.0.1" if settings.api_host == "0.0.0.0" else settings.api_host
                api_url = f"http://{host}:{settings.api_port}/v1/memory/facts"
                headers = {"X-API-Key": settings.api_secret_key}
                with httpx.Client(timeout=10.0) as client:
                    resp = client.get(api_url, params={"user_id": OS_USER_ID}, headers=headers)
                    if resp.status_code == 200:
                        self._json_response(resp.json())
                    else:
                        self._json_response({"facts": [], "error": f"API {resp.status_code}"})
            except Exception as e:
                self._json_response({"facts": [], "error": str(e)})

        elif path == "/history":
            # (Keep existing implementation)
            pass

        elif path == "/approval/pending":
            self._json_response({"pending": STATE["pending_action"]})

        elif path == "/suggestions/pending":
            self._json_response({"pending": _get_pending_suggestion()})

        else:
            self._json_response({"error": "not found"}, 404)

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length) if content_length > 0 else b"{}"
        payload = json.loads(post_data) if post_data else {}

        if self.path == "/query":
            q = payload.get("query")
            STATE["last_response"] = ""
            STATE["query"] = q
            timeout = 120
            start = time.time()
            while not STATE["last_response"] and time.time() - start < timeout:
                time.sleep(0.5)
            resp_text = STATE["last_response"] or "Timeout waiting for Kimiko."
            self._json_response({"response": resp_text})

        elif self.path == "/terminal/run":
            cmd = payload.get("command")
            if not cmd: return self._json_response({"error": "No command"}, 400)
            
            # Logic: If it's safe (whitelisted), we can decide to run it immediately or ask.
            # For now, let's ASK for everything to be ultra-safe.
            action_id = str(uuid.uuid4())[:8]
            STATE["pending_action"] = {
                "id": action_id,
                "type": "terminal",
                "command": cmd,
                "status": "pending"
            }
            self._json_response({"action_id": action_id, "status": "pending"})

        elif self.path == "/files/write":
            f_path = payload.get("path")
            content = payload.get("content")
            action_id = str(uuid.uuid4())[:8]
            STATE["pending_action"] = {
                "id": action_id,
                "type": "file_write",
                "path": f_path,
                "content": content,
                "status": "pending"
            }
            self._json_response({"action_id": action_id, "status": "pending"})

        elif self.path == "/automation/run":
            action = payload.get("action")
            params = payload.get("params", {})
            action_id = str(uuid.uuid4())[:8]
            STATE["pending_action"] = {
                "id": action_id,
                "type": "automation",
                "action": action,
                "params": params,
                "status": "pending"
            }
            self._json_response({"action_id": action_id, "status": "pending"})

        elif self.path == "/approval/confirm":
            action_id = payload.get("action_id")
            if not STATE["pending_action"] or STATE["pending_action"]["id"] != action_id:
                return self._json_response({"error": "Invalid action_id"}, 400)
            
            # Switch case for confirmation
            action = STATE["pending_action"]
            result_data = None
            
            if action["type"] == "terminal":
                result = CommandExecutor.execute(action["command"])
                result_data = {
                    "stdout": result.get("stdout", ""),
                    "stderr": result.get("stderr", ""),
                    "success": result.get("success", False),
                    "exit_code": result.get("exit_code", 0)
                }
                STATE["action_results"][action_id] = result_data
                STATE["terminal_history"].append({
                    "command": action["command"],
                    "timestamp": int(time.time()),
                    "status": "success" if result_data["success"] else "error",
                    "result_preview": (result_data["stdout"] or result_data["stderr"])[:100]
                })
                STATE["pending_action"] = None
                self._json_response({"success": True, "result": result})
                
            elif action["type"] == "file_write":
                success = OSFileSystem.write_file(action["path"], action["content"])
                result_data = {"success": success}
                STATE["action_results"][action_id] = result_data
                STATE["pending_action"] = None
                self._json_response({"success": success})
                
            elif action["type"] == "automation":
                executor = AutomationExecutor()
                result = executor.execute(action["action"], action["params"])
                result_data = {"result": result, "success": "Error" not in result}
                STATE["action_results"][action_id] = result_data
                STATE["pending_action"] = None
                self._json_response({"success": True, "result": result})

        elif self.path == "/approval/deny":
            STATE["pending_action"] = None
            self._json_response({"success": True})

        elif self.path == "/suggestions/dismiss":
            dismissed_id = _dismiss_suggestion(payload.get("suggestion_id"))
            if not dismissed_id:
                return self._json_response({"success": False, "error": "No pending suggestion found."}, 404)
            self._json_response({"success": True, "dismissed_id": dismissed_id})

    def log_message(self, format, *args):
        return


# ═══════════════════════════════════════════════════
#  HOTKEY MANAGER (Core Logic)
# ═══════════════════════════════════════════════════
class HotkeyManager:
    def __init__(self):
        self.electron_path = self._get_electron_path()
        host = "127.0.0.1" if settings.api_host == "0.0.0.0" else settings.api_host
        self.api_url = f"http://{host}:{settings.api_port}/v1/chat"
        self.api_key = settings.api_secret_key
        self.ui_process = None
        self.insight_engine = InsightEngine()

    def _get_electron_path(self):
        base = os.path.dirname(__file__)
        path = os.path.join(base, "ui-electron", "node_modules", ".bin", "electron")
        if os.name == 'nt':
            path += ".cmd"
        return path if os.path.exists(path) else "electron"

    # ── Context Capture ──
    def capture_context(self):
        """Capture active window, clipboard, and screenshots/context of all monitors."""
        try:
            win = gw.getActiveWindow()
            STATE["active_window"] = win.title if win else "Unknown"
        except Exception:
            STATE["active_window"] = "Unknown"

        clip = pyperclip.paste()
        for p in SENSITIVE_PATTERNS:
            clip = re.sub(p, "[REDACTED]", clip)
        STATE["clipboard"] = clip

        try:
            with mss.mss() as sct:
                # 1. Capture all monitors (thumbnails)
                monitors_data = []
                for i, mon in enumerate(sct.monitors):
                    if i == 0: continue
                    img = sct.grab(mon)
                    monitors_data.append({
                        "id": i,
                        "name": f"Display {i}",
                        "width": mon["width"],
                        "height": mon["height"],
                        "base64": ImageProcessor.process(img, max_width=320)
                    })
                STATE["monitors"] = monitors_data
                
                # 2. Primary Monitor Full Screenshot (for LLM)
                primary_img = sct.grab(sct.monitors[1])
                STATE["screenshot"] = ImageProcessor.process(primary_img)
                
                # 3. OCR & UI Tree (Primary Monitor)
                pil_img = Image.frombytes("RGB", primary_img.size, primary_img.bgra, "raw", "BGRX")
                try:
                    STATE["screen_details"]["visible_text"] = ScreenContextEngine.extract_text_pil(pil_img)
                except Exception:
                    STATE["screen_details"]["visible_text"] = "[OCR Failed]"
                
                STATE["screen_details"]["ui_elements"] = ScreenContextEngine.get_ui_elements()
                STATE["screen_details"]["active_app"] = STATE["active_window"]

        except Exception as e:
            print(f"Capture Error: {e}")
            STATE["screenshot"] = None

    def _refresh_live_screen_details(self):
        """Lightweight refresh for proactive insight scanning."""
        try:
            win = gw.getActiveWindow()
            STATE["active_window"] = win.title if win else STATE["active_window"]
        except Exception:
            pass

        try:
            with mss.mss() as sct:
                if len(sct.monitors) < 2:
                    return
                primary_img = sct.grab(sct.monitors[1])
                pil_img = Image.frombytes("RGB", primary_img.size, primary_img.bgra, "raw", "BGRX")
                STATE["screen_details"]["visible_text"] = ScreenContextEngine.extract_text_pil(pil_img)
                STATE["screen_details"]["active_app"] = STATE["active_window"]
        except Exception:
            pass

    # ── System Context Loop ──
    def _system_context_loop(self):
        """Background thread: polls system state every 3 seconds."""
        # Initial CPU measurement (first call always returns 0)
        psutil.cpu_percent(interval=0)
        tick = 0
        while True:
            try:
                STATE["processes"] = SystemContext.get_processes(max_count=10)
                STATE["resources"] = SystemContext.get_resources()
                STATE["monitors"] = SystemContext.get_monitors()
                tick += 1
                if tick % 2 == 0:
                    self._refresh_live_screen_details()
            except Exception as e:
                print(f"Context loop error: {e}")
            time.sleep(3)

    # ── Kimiko API Call ──
    def call_kimiko(self, query):
        print(f"DEBUG: Calling Kimiko API at {self.api_url}")
        payload = {
            "message": f"Context: {STATE['active_window']} | Clipboard: {STATE['clipboard']}\n\nQuery: {query}",
            "model": settings.os_model,
            "images": [STATE["screenshot"]] if STATE["screenshot"] else [],
            "user_id": OS_USER_ID,
            "session_id": STATE["session_id"],
            "metadata": {
                "active_window": STATE["active_window"],
                "resource_usage": STATE["resources"],
                "monitor_count": len(STATE["monitors"])
            }
        }
        headers = {"X-API-Key": self.api_key}

        try:
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(self.api_url, json=payload, headers=headers)
                print(f"DEBUG: API Response Code: {resp.status_code}")
                if resp.status_code == 200:
                    data = resp.json()
                    msg = data.get("message", {})
                    content = msg.get("content", "No content returned.")
                    STATE["last_response"] = content
                else:
                    print(f"DEBUG: API Error: {resp.text[:200]}")
                    STATE["last_response"] = f"Error {resp.status_code}: {resp.text[:100]}..."
        except Exception as e:
            print(f"DEBUG: Connection Error: {e}")
            STATE["last_response"] = f"Connection Error: {str(e)}"

    # ── Trigger (Hotkey Pressed) ──
    def trigger(self):
        print("Summoning Kimiko...")

        # Kill previous UI if running
        if self.ui_process and self.ui_process.poll() is None:
            try:
                self.ui_process.terminate()
                self.ui_process.wait(timeout=2)
            except Exception:
                try:
                    self.ui_process.kill()
                except Exception:
                    pass

        self.capture_context()
        ui_path = os.path.join(os.path.dirname(__file__), "ui-electron")
        self.ui_process = subprocess.Popen(
            [self.electron_path, "."],
            cwd=ui_path,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    # ── Query Watcher ──
    def watch_queries(self):
        while True:
            if STATE["query"]:
                q = STATE["query"]
                STATE["query"] = None
                self.call_kimiko(q)
            time.sleep(0.5)

    # ── Main Entry ──
    def start(self):
        # 1. Singleton via port lock
        try:
            server = HTTPServer(("127.0.0.1", 8001), ContextServer)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            print("✔ Context Bridge active on 127.0.0.1:8001")
        except OSError:
            print("❌ Another Kimiko OS Assistant is already running.")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Server Error: {e}")
            sys.exit(1)

        # 2. Start system context loop
        threading.Thread(target=self._system_context_loop, daemon=True).start()
        print("✔ System context monitor active")

        # 3. Start query watcher
        threading.Thread(target=self.watch_queries, daemon=True).start()

        # 4. Start proactive insight engine
        threading.Thread(target=self.insight_engine.run_forever, daemon=True).start()
        print("Proactive insight engine active")

        print(f"\n╔══════════════════════════════════════════════════╗")
        print(f"║ 🚀 Kimiko OS Assistant (Phase 8) Active          ║")
        print(f"╚══════════════════════════════════════════════════╝")
        print(f"Hotkey: {settings.os_hotkey}")
        print(f"Monitors detected: polling...")
        keyboard.add_hotkey(settings.os_hotkey, self.trigger)

        try:
            keyboard.wait()
        except KeyboardInterrupt:
            print("\n👋 Stopping Kimiko OS Assistant...")
            if self.ui_process:
                self.ui_process.terminate()


if __name__ == "__main__":
    HotkeyManager().start()
