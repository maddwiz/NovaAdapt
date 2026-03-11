from __future__ import annotations

import base64
import json
import os
import shlex
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, request

from .vision_grounding import VisionGroundingExecutor, VisionGroundingResult


@dataclass(frozen=True)
class MobileExecutionResult:
    status: str
    output: str
    action: dict[str, Any]
    data: dict[str, Any] | None = None


class AndroidMaestroExecutor:
    def __init__(self, *, device_id: str | None = None, timeout_seconds: int = 30) -> None:
        self.device_id = str(device_id or os.getenv("NOVAADAPT_ANDROID_DEVICE_ID", "")).strip() or None
        self.timeout_seconds = max(1, int(timeout_seconds))

    def status(self) -> dict[str, Any]:
        adb = shutil.which("adb")
        maestro = shutil.which("maestro")
        out: dict[str, Any] = {
            "ok": bool(adb),
            "platform": "android",
            "adb_available": bool(adb),
            "maestro_available": bool(maestro),
            "device_id": self.device_id,
        }
        if not adb:
            out["error"] = "adb is not installed"
            return out
        try:
            devices = self._list_devices()
        except Exception as exc:
            out["ok"] = False
            out["error"] = str(exc)
            return out
        out["devices"] = devices
        out["connected"] = len(devices)
        if self.device_id:
            out["selected_available"] = self.device_id in devices
            out["ok"] = out["ok"] and bool(out["selected_available"])
        return out

    def execute_action(self, action: dict[str, Any], *, dry_run: bool = False) -> MobileExecutionResult:
        normalized = dict(action)
        normalized.setdefault("platform", "android")
        if dry_run:
            return MobileExecutionResult(
                status="preview",
                output=f"Preview only: {json.dumps(normalized, ensure_ascii=True)}",
                action=normalized,
            )

        action_type = str(normalized.get("type") or "").strip().lower()
        if not action_type:
            return MobileExecutionResult(
                status="failed",
                output="mobile action missing required field: type",
                action=normalized,
            )
        handlers = {
            "open_app": self._open_app,
            "launch_app": self._open_app,
            "open_url": self._open_url,
            "tap": self._tap,
            "click": self._tap,
            "type": self._type_text,
            "input": self._type_text,
            "key": self._press_key,
            "press": self._press_key,
            "swipe": self._swipe,
            "scroll": self._scroll,
            "wait": self._wait,
            "screenshot": self._screenshot,
            "run_adb": self._run_adb,
        }
        handler = handlers.get(action_type)
        if handler is None:
            return MobileExecutionResult(
                status="failed",
                output=f"unsupported android action type '{action_type}'",
                action=normalized,
            )
        try:
            return handler(normalized)
        except Exception as exc:
            return MobileExecutionResult(status="failed", output=f"android execution error: {exc}", action=normalized)

    def _open_app(self, action: dict[str, Any]) -> MobileExecutionResult:
        package = str(action.get("package") or action.get("target") or action.get("value") or "").strip()
        if not package:
            return MobileExecutionResult(status="failed", output="open_app requires package/target/value", action=action)
        completed = self._adb(["shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"])
        return self._result(completed, action, {"package": package})

    def _open_url(self, action: dict[str, Any]) -> MobileExecutionResult:
        url = str(action.get("url") or action.get("target") or action.get("value") or "").strip()
        if not url:
            return MobileExecutionResult(status="failed", output="open_url requires url/target/value", action=action)
        completed = self._adb(["shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", url])
        return self._result(completed, action, {"url": url})

    def _tap(self, action: dict[str, Any]) -> MobileExecutionResult:
        coords = _mobile_coords(action)
        if coords is None:
            selector = str(action.get("selector") or action.get("text") or "").strip()
            if selector and shutil.which("maestro"):
                return self._maestro_tap(selector, action)
            return MobileExecutionResult(
                status="failed",
                output="tap requires x/y coordinates or selector/text with maestro",
                action=action,
            )
        x, y = coords
        completed = self._adb(["shell", "input", "tap", str(x), str(y)])
        return self._result(completed, action, {"x": x, "y": y})

    def _type_text(self, action: dict[str, Any]) -> MobileExecutionResult:
        text = str(action.get("text") or action.get("value") or action.get("target") or "").strip()
        if not text:
            return MobileExecutionResult(status="failed", output="type requires text/value/target", action=action)
        completed = self._adb(["shell", "input", "text", text.replace(" ", "%s")])
        return self._result(completed, action, {"text": text})

    def _press_key(self, action: dict[str, Any]) -> MobileExecutionResult:
        key = str(action.get("key") or action.get("target") or action.get("value") or "").strip()
        if not key:
            return MobileExecutionResult(status="failed", output="key requires key/target/value", action=action)
        keycode = _ANDROID_KEYCODE_ALIASES.get(key.lower(), key)
        completed = self._adb(["shell", "input", "keyevent", str(keycode)])
        return self._result(completed, action, {"key": key})

    def _swipe(self, action: dict[str, Any]) -> MobileExecutionResult:
        start = _mobile_coords(action, prefix="")
        end = _mobile_coords(action, prefix="to_")
        if start is None or end is None:
            return MobileExecutionResult(status="failed", output="swipe requires x/y and to_x/to_y", action=action)
        duration = int(action.get("duration_ms", 300) or 300)
        completed = self._adb(
            ["shell", "input", "swipe", str(start[0]), str(start[1]), str(end[0]), str(end[1]), str(duration)]
        )
        return self._result(
            completed,
            action,
            {"x": start[0], "y": start[1], "to_x": end[0], "to_y": end[1], "duration_ms": duration},
        )

    def _scroll(self, action: dict[str, Any]) -> MobileExecutionResult:
        direction = str(action.get("direction") or action.get("target") or "down").strip().lower() or "down"
        width = int(action.get("width", 540) or 540)
        height = int(action.get("height", 1600) or 1600)
        x = width // 2
        start_y, end_y = (int(height * 0.75), int(height * 0.25))
        if direction in {"up", "reverse"}:
            start_y, end_y = end_y, start_y
        completed = self._adb(["shell", "input", "swipe", str(x), str(start_y), str(x), str(end_y), "250"])
        return self._result(
            completed,
            action,
            {"direction": direction, "x": x, "start_y": start_y, "end_y": end_y},
        )

    def _wait(self, action: dict[str, Any]) -> MobileExecutionResult:
        seconds = _parse_wait_seconds(action)
        time.sleep(seconds)
        return MobileExecutionResult(status="ok", output=f"waited {seconds:.3f}s", action=action, data={"seconds": seconds})

    def _screenshot(self, action: dict[str, Any]) -> MobileExecutionResult:
        output = Path(
            str(action.get("path") or Path.home() / ".novaadapt" / "mobile_screenshots" / f"android-{int(time.time())}.png")
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        completed = self._adb_raw(["exec-out", "screencap", "-p"])
        if completed.returncode != 0:
            text = (completed.stderr.decode("utf-8", errors="ignore") or "").strip()
            return MobileExecutionResult(status="failed", output=text or "android screenshot failed", action=action)
        output.write_bytes(completed.stdout)
        return MobileExecutionResult(status="ok", output=f"screenshot saved: {output}", action=action, data={"path": str(output)})

    def _run_adb(self, action: dict[str, Any]) -> MobileExecutionResult:
        raw = str(action.get("command") or action.get("value") or action.get("target") or "").strip()
        if not raw:
            return MobileExecutionResult(status="failed", output="run_adb requires command/value/target", action=action)
        completed = self._adb(shlex.split(raw))
        return self._result(completed, action, None)

    def _maestro_tap(self, selector: str, action: dict[str, Any]) -> MobileExecutionResult:
        maestro = shutil.which("maestro")
        if not maestro:
            return MobileExecutionResult(status="failed", output="maestro is not installed", action=action)
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as handle:
            handle.write("appId: com.android.shell\n---\n")
            handle.write(f"- tapOn: {json.dumps(selector)}\n")
            flow_path = handle.name
        try:
            completed = subprocess.run(
                [maestro, "test", flow_path],
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        finally:
            try:
                Path(flow_path).unlink(missing_ok=True)
            except Exception:
                pass
        return self._result(completed, action, {"selector": selector, "maestro": True})

    def _adb(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        adb = shutil.which("adb")
        if not adb:
            raise RuntimeError("adb is not installed")
        cmd = [adb]
        if self.device_id:
            cmd.extend(["-s", self.device_id])
        cmd.extend(args)
        return subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=self.timeout_seconds)

    def _adb_raw(self, args: list[str]) -> subprocess.CompletedProcess[bytes]:
        adb = shutil.which("adb")
        if not adb:
            raise RuntimeError("adb is not installed")
        cmd = [adb]
        if self.device_id:
            cmd.extend(["-s", self.device_id])
        cmd.extend(args)
        return subprocess.run(cmd, check=False, capture_output=True, timeout=self.timeout_seconds)

    def _list_devices(self) -> list[str]:
        completed = self._adb(["devices"])
        if completed.returncode != 0:
            raise RuntimeError((completed.stderr or completed.stdout or "adb devices failed").strip())
        devices: list[str] = []
        for line in str(completed.stdout or "").splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                devices.append(parts[0])
        return devices

    @staticmethod
    def _result(
        completed: subprocess.CompletedProcess[str],
        action: dict[str, Any],
        data: dict[str, Any] | None,
    ) -> MobileExecutionResult:
        status = "ok" if completed.returncode == 0 else "failed"
        output = (completed.stdout or completed.stderr or "").strip()
        if not output:
            output = f"exit={completed.returncode}"
        return MobileExecutionResult(status=status, output=output, action=action, data=data)


class IOSAppiumExecutor:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        session_id: str | None = None,
        desired_capabilities: dict[str, Any] | None = None,
        timeout_seconds: int = 30,
    ) -> None:
        self.base_url = str(base_url or os.getenv("NOVAADAPT_IOS_APPIUM_URL", "")).rstrip("/")
        self.session_id = str(session_id or os.getenv("NOVAADAPT_IOS_APPIUM_SESSION_ID", "")).strip() or None
        raw_caps = (
            desired_capabilities
            if desired_capabilities is not None
            else _parse_optional_json_object(os.getenv("NOVAADAPT_IOS_APPIUM_CAPABILITIES", ""))
        )
        self.desired_capabilities = raw_caps if isinstance(raw_caps, dict) else {}
        self.timeout_seconds = max(1, int(timeout_seconds))

    def status(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "ok": False,
            "platform": "ios",
            "transport": "appium",
            "configured": bool(self.base_url),
            "base_url": self.base_url,
            "session_id": self.session_id,
            "capabilities_configured": bool(self.desired_capabilities),
        }
        if not self.base_url:
            out["error"] = "NOVAADAPT_IOS_APPIUM_URL is not configured"
            return out
        try:
            payload = self._request_json("GET", "/status", None)
        except Exception as exc:
            out["reachable"] = False
            out["error"] = str(exc)
            return out
        out["ok"] = True
        out["reachable"] = True
        out["status_payload"] = payload
        return out

    def available(self) -> bool:
        return bool(self.base_url)

    def execute_action(self, action: dict[str, Any], *, dry_run: bool = False) -> MobileExecutionResult:
        normalized = dict(action)
        normalized["platform"] = "ios"
        if dry_run:
            return MobileExecutionResult(
                status="preview",
                output=f"Preview only: {json.dumps(normalized, ensure_ascii=True)}",
                action=normalized,
            )

        session_id = self._ensure_session()
        action_type = str(normalized.get("type") or "").strip().lower()
        if not action_type:
            return MobileExecutionResult(status="failed", output="iOS action missing required field: type", action=normalized)

        handlers = {
            "open_url": self._open_url,
            "open_app": self._open_app,
            "launch_app": self._open_app,
            "tap": self._tap,
            "click": self._tap,
            "type": self._type_text,
            "input": self._type_text,
            "key": self._press_key,
            "swipe": self._swipe,
            "drag": self._swipe,
            "scroll": self._scroll,
            "wait": self._wait,
            "note": self._note,
        }
        handler = handlers.get(action_type)
        if handler is None:
            return MobileExecutionResult(
                status="failed",
                output=f"unsupported iOS Appium action type '{action_type}'",
                action=normalized,
                data={"session_id": session_id},
            )
        try:
            return handler(session_id, normalized)
        except Exception as exc:
            return MobileExecutionResult(
                status="failed",
                output=f"iOS Appium execution error: {exc}",
                action=normalized,
                data={"session_id": session_id},
            )

    def _open_url(self, session_id: str, action: dict[str, Any]) -> MobileExecutionResult:
        url = str(action.get("url") or action.get("target") or action.get("value") or "").strip()
        if not url:
            return MobileExecutionResult(status="failed", output="open_url requires url/target/value", action=action)
        self._request_json("POST", f"/session/{session_id}/url", {"url": url})
        return MobileExecutionResult(status="ok", output=f"opened {url}", action=action, data={"session_id": session_id})

    def _open_app(self, session_id: str, action: dict[str, Any]) -> MobileExecutionResult:
        bundle_id = str(action.get("bundle_id") or action.get("target") or action.get("value") or "").strip()
        if not bundle_id:
            return MobileExecutionResult(status="failed", output="open_app requires bundle_id/target/value", action=action)
        self._request_json(
            "POST",
            f"/session/{session_id}/execute/sync",
            {"script": "mobile: activateApp", "args": [{"bundleId": bundle_id}]},
        )
        return MobileExecutionResult(
            status="ok",
            output=f"activated {bundle_id}",
            action=action,
            data={"session_id": session_id, "bundle_id": bundle_id},
        )

    def _tap(self, session_id: str, action: dict[str, Any]) -> MobileExecutionResult:
        coords = _mobile_coords(action)
        if coords is not None:
            self._pointer_action(
                session_id,
                [
                    {"type": "pointerMove", "duration": 0, "x": coords[0], "y": coords[1]},
                    {"type": "pointerDown", "button": 0},
                    {"type": "pause", "duration": 50},
                    {"type": "pointerUp", "button": 0},
                ],
            )
            return MobileExecutionResult(
                status="ok",
                output=f"tapped {coords[0]},{coords[1]}",
                action=action,
                data={"session_id": session_id, "x": coords[0], "y": coords[1]},
            )
        element_id = self._find_element(session_id, action)
        self._request_json("POST", f"/session/{session_id}/element/{element_id}/click", {})
        return MobileExecutionResult(
            status="ok",
            output=f"clicked element {element_id}",
            action=action,
            data={"session_id": session_id, "element_id": element_id},
        )

    def _type_text(self, session_id: str, action: dict[str, Any]) -> MobileExecutionResult:
        text = str(action.get("text") or action.get("value") or action.get("target") or "")
        if text == "":
            return MobileExecutionResult(status="failed", output="type requires text/value/target", action=action)
        element_id = self._find_element(session_id, action, allow_missing=True)
        if element_id:
            self._request_json(
                "POST",
                f"/session/{session_id}/element/{element_id}/value",
                {"text": text, "value": list(text)},
            )
        else:
            active = self._request_json("GET", f"/session/{session_id}/element/active", None)
            active_id = self._extract_element_id(active)
            if not active_id:
                raise RuntimeError("no active element available for typing")
            self._request_json(
                "POST",
                f"/session/{session_id}/element/{active_id}/value",
                {"text": text, "value": list(text)},
            )
            element_id = active_id
        return MobileExecutionResult(
            status="ok",
            output=f"typed {len(text)} characters",
            action=action,
            data={"session_id": session_id, "element_id": element_id},
        )

    def _press_key(self, session_id: str, action: dict[str, Any]) -> MobileExecutionResult:
        key = str(action.get("key") or action.get("target") or action.get("value") or "").strip()
        if not key:
            return MobileExecutionResult(status="failed", output="key requires key/target/value", action=action)
        self._request_json(
            "POST",
            f"/session/{session_id}/execute/sync",
            {"script": "mobile: pressButton", "args": [{"name": key}]},
        )
        return MobileExecutionResult(
            status="ok",
            output=f"pressed {key}",
            action=action,
            data={"session_id": session_id, "key": key},
        )

    def _swipe(self, session_id: str, action: dict[str, Any]) -> MobileExecutionResult:
        start = _mobile_coords(action, prefix="")
        end = _mobile_coords(action, prefix="to_")
        if start is not None and end is not None:
            duration_ms = max(50, int(action.get("duration_ms", 300) or 300))
            self._pointer_action(
                session_id,
                [
                    {"type": "pointerMove", "duration": 0, "x": start[0], "y": start[1]},
                    {"type": "pointerDown", "button": 0},
                    {"type": "pointerMove", "duration": duration_ms, "x": end[0], "y": end[1]},
                    {"type": "pointerUp", "button": 0},
                ],
            )
            return MobileExecutionResult(
                status="ok",
                output=f"swiped {start[0]},{start[1]} -> {end[0]},{end[1]}",
                action=action,
                data={"session_id": session_id},
            )
        direction = str(action.get("direction") or action.get("target") or "up").strip().lower()
        self._request_json(
            "POST",
            f"/session/{session_id}/execute/sync",
            {"script": "mobile: swipe", "args": [{"direction": direction}]},
        )
        return MobileExecutionResult(
            status="ok",
            output=f"swiped {direction}",
            action=action,
            data={"session_id": session_id, "direction": direction},
        )

    def _scroll(self, session_id: str, action: dict[str, Any]) -> MobileExecutionResult:
        direction = str(action.get("direction") or action.get("target") or "down").strip().lower()
        self._request_json(
            "POST",
            f"/session/{session_id}/execute/sync",
            {"script": "mobile: scroll", "args": [{"direction": direction}]},
        )
        return MobileExecutionResult(
            status="ok",
            output=f"scrolled {direction}",
            action=action,
            data={"session_id": session_id, "direction": direction},
        )

    def _wait(self, session_id: str, action: dict[str, Any]) -> MobileExecutionResult:
        seconds = _parse_wait_seconds(action)
        time.sleep(seconds)
        return MobileExecutionResult(
            status="ok",
            output=f"waited {seconds:.3f}s",
            action=action,
            data={"session_id": session_id, "seconds": seconds},
        )

    def _note(self, session_id: str, action: dict[str, Any]) -> MobileExecutionResult:
        _ = session_id
        target = str(action.get("target") or "").strip()
        value = str(action.get("value") or "").strip()
        return MobileExecutionResult(
            status="ok",
            output=("note: " + " ".join(part for part in (target, value) if part)).strip(),
            action=action,
        )

    def _ensure_session(self) -> str:
        if self.session_id:
            return self.session_id
        if not self.base_url:
            raise RuntimeError("NOVAADAPT_IOS_APPIUM_URL is not configured")
        if not self.desired_capabilities:
            raise RuntimeError("set NOVAADAPT_IOS_APPIUM_SESSION_ID or NOVAADAPT_IOS_APPIUM_CAPABILITIES")
        payload = self._request_json(
            "POST",
            "/session",
            {
                "capabilities": {
                    "alwaysMatch": self.desired_capabilities,
                    "firstMatch": [{}],
                }
            },
        )
        value = payload.get("value") if isinstance(payload, dict) else {}
        session_id = ""
        if isinstance(payload.get("sessionId"), str):
            session_id = str(payload.get("sessionId"))
        elif isinstance(value, dict) and isinstance(value.get("sessionId"), str):
            session_id = str(value.get("sessionId"))
        if not session_id:
            raise RuntimeError("Appium did not return a session id")
        self.session_id = session_id
        return session_id

    def _pointer_action(self, session_id: str, actions: list[dict[str, Any]]) -> None:
        self._request_json(
            "POST",
            f"/session/{session_id}/actions",
            {
                "actions": [
                    {
                        "type": "pointer",
                        "id": "finger1",
                        "parameters": {"pointerType": "touch"},
                        "actions": actions,
                    }
                ]
            },
        )

    def _find_element(self, session_id: str, action: dict[str, Any], *, allow_missing: bool = False) -> str:
        locator = str(action.get("selector") or action.get("element") or action.get("target") or "").strip()
        if not locator:
            if allow_missing:
                return ""
            raise RuntimeError("selector/target is required for element-based iOS actions")
        using, value = self._locator_strategy(locator)
        payload = self._request_json("POST", f"/session/{session_id}/element", {"using": using, "value": value})
        element_id = self._extract_element_id(payload)
        if element_id:
            return element_id
        if allow_missing:
            return ""
        raise RuntimeError(f"unable to resolve iOS element for selector '{locator}'")

    @staticmethod
    def _locator_strategy(locator: str) -> tuple[str, str]:
        text = str(locator or "").strip()
        lowered = text.lower()
        if lowered.startswith("xpath="):
            return "xpath", text.split("=", 1)[1]
        if text.startswith("//"):
            return "xpath", text
        if lowered.startswith("predicate:"):
            return "-ios predicate string", text.split(":", 1)[1].strip()
        if lowered.startswith("class:"):
            return "class name", text.split(":", 1)[1].strip()
        if lowered.startswith("id="):
            return "accessibility id", text.split("=", 1)[1]
        if lowered.startswith("accessibility:"):
            return "accessibility id", text.split(":", 1)[1].strip()
        return "accessibility id", text

    @staticmethod
    def _extract_element_id(payload: Any) -> str:
        if not isinstance(payload, dict):
            return ""
        value = payload.get("value")
        if isinstance(value, dict):
            if isinstance(value.get("element-6066-11e4-a52e-4f735466cecf"), str):
                return str(value.get("element-6066-11e4-a52e-4f735466cecf"))
            if isinstance(value.get("ELEMENT"), str):
                return str(value.get("ELEMENT"))
        if isinstance(payload.get("element-6066-11e4-a52e-4f735466cecf"), str):
            return str(payload.get("element-6066-11e4-a52e-4f735466cecf"))
        return ""

    def _request_json(self, method: str, path: str, payload: dict[str, Any] | None) -> Any:
        if not self.base_url:
            raise RuntimeError("NOVAADAPT_IOS_APPIUM_URL is not configured")
        headers = {"Accept": "application/json"}
        raw: bytes | None = None
        if payload is not None:
            raw = json.dumps(payload, ensure_ascii=True).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = request.Request(f"{self.base_url}{path}", data=raw, headers=headers, method=method.upper())
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="ignore")
            finally:
                try:
                    exc.close()
                except Exception:
                    pass
            raise RuntimeError(f"Appium HTTP {int(exc.code)}: {detail}") from None
        except error.URLError as exc:
            reason = exc.reason
            close_fn = getattr(reason, "close", None)
            if callable(close_fn):
                try:
                    close_fn()
                except Exception:
                    pass
            raise RuntimeError(f"Appium transport error: {reason}") from None
        if not body.strip():
            return {}
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {"raw": body.strip()}


class IOSVisionExecutor:
    def __init__(self, vision_executor: VisionGroundingExecutor) -> None:
        self.vision_executor = vision_executor

    def execute(
        self,
        payload: dict[str, Any],
        *,
        config_path: Path,
        execute: bool,
        strategy: str,
        model_name: str | None,
        candidate_models: list[str] | None,
        fallback_models: list[str] | None,
    ) -> tuple[VisionGroundingResult, dict[str, Any]]:
        goal = str(payload.get("goal") or payload.get("objective") or "").strip()
        if not goal:
            raw_action = payload.get("action")
            goal = _ios_goal_from_action(raw_action if isinstance(raw_action, dict) else payload)
        screenshot_png = _decode_base64_image(payload.get("screenshot_base64"))
        grounded = self.vision_executor.ground(
            goal=goal,
            config_path=config_path,
            screenshot_png=screenshot_png,
            app_name=str(payload.get("app_name") or "iPhone").strip(),
            model_name=model_name,
            strategy=strategy,
            candidate_models=candidate_models,
            fallback_models=fallback_models,
            context=payload.get("context") if isinstance(payload.get("context"), dict) else None,
            ocr_text=str(payload.get("ocr_text") or ""),
            accessibility_tree=str(payload.get("accessibility_tree") or ""),
        )
        routed_action = {
            "type": "vision_goal",
            "executor": "vision",
            "goal": goal,
            "platform": "ios",
            "execute": bool(execute),
            "screenshot_base64": grounded.screenshot_base64,
            "ocr_text": grounded.ocr_text,
            "accessibility_tree": grounded.accessibility_tree,
            "app_name": str(payload.get("app_name") or "iPhone").strip(),
            "model": model_name,
            "strategy": strategy,
            "candidates": list(candidate_models or []),
            "fallbacks": list(fallback_models or []),
        }
        return grounded, routed_action


class UnifiedMobileExecutor:
    def __init__(
        self,
        *,
        android_executor: AndroidMaestroExecutor | None = None,
        ios_executor: IOSVisionExecutor | None = None,
        ios_appium_executor: IOSAppiumExecutor | None = None,
    ) -> None:
        self.android_executor = android_executor or AndroidMaestroExecutor()
        self.ios_executor = ios_executor
        self.ios_appium_executor = ios_appium_executor or IOSAppiumExecutor()

    def status(self) -> dict[str, Any]:
        return {
            "ok": True,
            "android": self.android_executor.status(),
            "ios": {
                "ok": self.ios_executor is not None or self.ios_appium_executor.available(),
                "vision": {"ok": self.ios_executor is not None, "executor": "vision"},
                "appium": self.ios_appium_executor.status(),
            },
        }

    def execute_action(self, action: dict[str, Any], *, dry_run: bool = True) -> MobileExecutionResult:
        normalized = dict(action)
        normalized.setdefault("platform", "android")
        platform = str(normalized.get("platform") or "").strip().lower()
        if platform == "android":
            return self.android_executor.execute_action(normalized, dry_run=dry_run)
        if platform == "ios":
            return self.ios_appium_executor.execute_action(normalized, dry_run=dry_run)
        return MobileExecutionResult(status="failed", output=f"unsupported mobile platform '{platform}'", action=normalized)


_ANDROID_KEYCODE_ALIASES = {
    "back": "4",
    "home": "3",
    "enter": "66",
    "tab": "61",
    "space": "62",
    "menu": "82",
}


def _mobile_coords(action: dict[str, Any], *, prefix: str = "") -> tuple[int, int] | None:
    x_key = prefix + "x"
    y_key = prefix + "y"
    if action.get(x_key) is not None and action.get(y_key) is not None:
        try:
            return int(action.get(x_key)), int(action.get(y_key))
        except Exception:
            return None
    raw = action.get("target") if prefix == "" else action.get(prefix + "target")
    if raw is None:
        return None
    text = str(raw).strip()
    if "," not in text:
        return None
    left, right = text.split(",", 1)
    try:
        return int(left.strip()), int(right.strip())
    except Exception:
        return None


def _parse_wait_seconds(action: dict[str, Any]) -> float:
    raw = str(action.get("value") or action.get("target") or action.get("seconds") or "1").strip().lower()
    if raw.endswith("ms"):
        try:
            return max(0.0, min(300.0, float(raw[:-2]) / 1000.0))
        except Exception:
            return 1.0
    if raw.endswith("s"):
        raw = raw[:-1]
    try:
        return max(0.0, min(300.0, float(raw)))
    except Exception:
        return 1.0


def _ios_goal_from_action(action: dict[str, Any]) -> str:
    action_type = str(action.get("type") or "").strip().lower() or "mobile_action"
    target = str(action.get("target") or "").strip()
    value = str(action.get("value") or action.get("text") or "").strip()
    if target and value:
        return f"On the current iPhone screen, perform action '{action_type}' using target '{target}' and value '{value}'."
    if target:
        return f"On the current iPhone screen, perform action '{action_type}' using target '{target}'."
    if value:
        return f"On the current iPhone screen, perform action '{action_type}' using value '{value}'."
    return f"On the current iPhone screen, perform action '{action_type}'."


def _decode_base64_image(raw: object) -> bytes | None:
    text = str(raw or "").strip()
    if not text:
        return None
    if "," in text and text.lower().startswith("data:image"):
        text = text.split(",", 1)[1]
    try:
        return base64.b64decode(text, validate=True)
    except Exception as exc:
        raise ValueError("invalid screenshot_base64 payload") from exc


def _parse_optional_json_object(raw: object) -> dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
