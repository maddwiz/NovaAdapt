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
    ) -> None:
        self.android_executor = android_executor or AndroidMaestroExecutor()
        self.ios_executor = ios_executor

    def status(self) -> dict[str, Any]:
        return {
            "ok": True,
            "android": self.android_executor.status(),
            "ios": {"ok": self.ios_executor is not None, "executor": "vision"},
        }

    def execute_action(self, action: dict[str, Any], *, dry_run: bool = True) -> MobileExecutionResult:
        normalized = dict(action)
        normalized.setdefault("platform", "android")
        platform = str(normalized.get("platform") or "").strip().lower()
        if platform != "android":
            return MobileExecutionResult(
                status="failed",
                output="UnifiedMobileExecutor only executes Android actions directly; iOS uses IOSVisionExecutor",
                action=normalized,
            )
        return self.android_executor.execute_action(normalized, dry_run=dry_run)


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
