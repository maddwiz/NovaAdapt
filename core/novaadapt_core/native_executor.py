from __future__ import annotations

import re
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any


_DURATION_RE = re.compile(r"^\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>ms|s|sec|secs|second|seconds|m|min|mins|minute|minutes)?\s*$", re.IGNORECASE)
_COORD_PAIR_RE = re.compile(r"^\s*(?P<x>-?\d+)\s*[,x]\s*(?P<y>-?\d+)\s*$", re.IGNORECASE)
_COORD_NAMED_RE = re.compile(r"^\s*x\s*=\s*(?P<x>-?\d+)\s*[,\s]\s*y\s*=\s*(?P<y>-?\d+)\s*$", re.IGNORECASE)

_APPLE_MODIFIERS = {
    "cmd": "command down",
    "command": "command down",
    "ctrl": "control down",
    "control": "control down",
    "alt": "option down",
    "option": "option down",
    "shift": "shift down",
}

_APPLE_KEY_CODES = {
    "enter": 36,
    "return": 36,
    "tab": 48,
    "space": 49,
    "esc": 53,
    "escape": 53,
    "delete": 51,
    "backspace": 51,
    "up": 126,
    "down": 125,
    "left": 123,
    "right": 124,
}

_XDOTOOL_KEY_ALIASES = {
    "enter": "Return",
    "return": "Return",
    "tab": "Tab",
    "space": "space",
    "esc": "Escape",
    "escape": "Escape",
    "delete": "BackSpace",
    "backspace": "BackSpace",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    "cmd": "super",
    "command": "super",
    "ctrl": "ctrl",
    "control": "ctrl",
    "alt": "alt",
    "option": "alt",
    "shift": "shift",
}


@dataclass(frozen=True)
class NativeExecutionResult:
    status: str
    output: str


class NativeDesktopExecutor:
    """Built-in desktop action executor for NovaAdapt.

    This provides a no-external-runtime baseline. External DirectShell transports
    remain available for advanced deterministic control.
    """

    def __init__(
        self,
        *,
        platform_name: str | None = None,
        timeout_seconds: int = 30,
    ) -> None:
        self.platform_name = (platform_name or sys.platform).lower()
        self.timeout_seconds = max(1, int(timeout_seconds))

    def execute_action(self, action: dict[str, Any]) -> NativeExecutionResult:
        action_type = str(action.get("type", "")).strip().lower()
        if not action_type:
            return NativeExecutionResult(status="failed", output="Action missing required field: type")

        handlers = {
            "note": self._execute_note,
            "noop": self._execute_note,
            "wait": self._execute_wait,
            "sleep": self._execute_wait,
            "open_url": self._execute_open_url,
            "open_app": self._execute_open_app,
            "type": self._execute_type,
            "text": self._execute_type,
            "input": self._execute_type,
            "key": self._execute_key,
            "press": self._execute_key,
            "hotkey": self._execute_hotkey,
            "click": self._execute_click,
            "run_shell": self._execute_run_shell,
            "shell": self._execute_run_shell,
            "terminal": self._execute_run_shell,
            "command": self._execute_run_shell,
        }
        handler = handlers.get(action_type)
        if handler is None:
            supported = ", ".join(sorted(handlers.keys()))
            return NativeExecutionResult(
                status="failed",
                output=f"Unsupported native action type '{action_type}'. Supported: {supported}",
            )

        try:
            return handler(action)
        except Exception as exc:
            return NativeExecutionResult(status="failed", output=f"Native execution error: {exc}")

    def probe(self) -> dict[str, Any]:
        capabilities = self.capabilities()
        if self._is_macos():
            check = self._run_subprocess(
                ["osascript", "-e", 'return "ok"'],
                shell=False,
            )
            return {
                "ok": check.returncode == 0,
                "transport": "native",
                "platform": self.platform_name,
                "capabilities": capabilities,
                "output": (check.stdout or check.stderr).strip(),
            }

        if self._is_linux():
            has_xdotool = self._linux_has_xdotool()
            return {
                "ok": True,
                "transport": "native",
                "platform": self.platform_name,
                "capabilities": capabilities,
                "output": (
                    "linux native execution available"
                    if has_xdotool
                    else "linux native execution available (limited: install xdotool for type/key/hotkey/click)"
                ),
                "xdotool_available": has_xdotool,
            }

        if self._is_windows():
            return {
                "ok": True,
                "transport": "native",
                "platform": self.platform_name,
                "capabilities": capabilities,
                "output": "windows native execution available (open_url/open_app/run_shell/wait fully supported)",
            }

        return {
            "ok": False,
            "transport": "native",
            "platform": self.platform_name,
            "capabilities": capabilities,
            "error": f"Unsupported platform for native execution: {self.platform_name}",
        }

    @staticmethod
    def capabilities() -> list[str]:
        return [
            "note",
            "wait",
            "open_url",
            "open_app",
            "type",
            "key",
            "hotkey",
            "click",
            "run_shell",
        ]

    def _execute_note(self, action: dict[str, Any]) -> NativeExecutionResult:
        target = str(action.get("target", "")).strip() or "note"
        value = str(action.get("value", "")).strip()
        if value:
            return NativeExecutionResult(status="ok", output=f"note:{target} {value}")
        return NativeExecutionResult(status="ok", output=f"note:{target}")

    def _execute_wait(self, action: dict[str, Any]) -> NativeExecutionResult:
        raw = str(action.get("value") or action.get("target") or "1").strip()
        seconds = self._parse_duration_seconds(raw)
        seconds = max(0.0, min(300.0, seconds))
        time.sleep(seconds)
        return NativeExecutionResult(status="ok", output=f"waited {seconds:.3f}s")

    def _execute_open_url(self, action: dict[str, Any]) -> NativeExecutionResult:
        url = str(action.get("target") or action.get("value") or "").strip()
        if not url:
            return NativeExecutionResult(status="failed", output="open_url requires target or value")

        if self._is_macos():
            completed = self._run_subprocess(["open", url], shell=False)
        elif self._is_linux():
            completed = self._run_subprocess(["xdg-open", url], shell=False)
        elif self._is_windows():
            completed = self._run_subprocess(["cmd", "/c", "start", "", url], shell=False)
        else:
            return NativeExecutionResult(status="failed", output=f"Unsupported platform: {self.platform_name}")
        return self._result_from_completed(completed)

    def _execute_open_app(self, action: dict[str, Any]) -> NativeExecutionResult:
        app = str(action.get("target") or action.get("value") or "").strip()
        if not app:
            return NativeExecutionResult(status="failed", output="open_app requires target or value")

        if self._is_macos():
            completed = self._run_subprocess(["open", "-a", app], shell=False)
        elif self._is_linux():
            completed = self._run_subprocess(["nohup", app], shell=False)
        elif self._is_windows():
            completed = self._run_subprocess(["cmd", "/c", "start", "", app], shell=False)
        else:
            return NativeExecutionResult(status="failed", output=f"Unsupported platform: {self.platform_name}")
        return self._result_from_completed(completed)

    def _execute_type(self, action: dict[str, Any]) -> NativeExecutionResult:
        text = str(action.get("value") or action.get("target") or "")
        if text == "":
            return NativeExecutionResult(status="failed", output="type action requires value or target")
        if self._is_macos():
            script = f'tell application "System Events" to keystroke "{self._escape_applescript_string(text)}"'
            completed = self._run_subprocess(["osascript", "-e", script], shell=False)
            return self._result_from_completed(completed)
        if self._is_linux():
            if not self._linux_has_xdotool():
                return NativeExecutionResult(status="failed", output="type on linux requires 'xdotool' in PATH")
            completed = self._run_subprocess(["xdotool", "type", "--delay", "1", "--", text], shell=False)
            return self._result_from_completed(completed)
        return NativeExecutionResult(
            status="failed",
            output=f"type is only implemented for macOS/linux native runtime (platform={self.platform_name})",
        )

    def _execute_key(self, action: dict[str, Any]) -> NativeExecutionResult:
        key = str(action.get("target") or action.get("value") or "").strip().lower()
        if not key:
            return NativeExecutionResult(status="failed", output="key action requires target or value")
        if self._is_macos():
            script = self._apple_key_script(key, modifiers=[])
            completed = self._run_subprocess(["osascript", "-e", script], shell=False)
            return self._result_from_completed(completed)
        if self._is_linux():
            if not self._linux_has_xdotool():
                return NativeExecutionResult(status="failed", output="key on linux requires 'xdotool' in PATH")
            resolved_key = self._xdotool_key_name(key)
            completed = self._run_subprocess(["xdotool", "key", resolved_key], shell=False)
            return self._result_from_completed(completed)
        return NativeExecutionResult(
            status="failed",
            output=f"key is only implemented for macOS/linux native runtime (platform={self.platform_name})",
        )

    def _execute_hotkey(self, action: dict[str, Any]) -> NativeExecutionResult:
        chord = str(action.get("target") or action.get("value") or "").strip().lower()
        if not chord:
            return NativeExecutionResult(status="failed", output="hotkey action requires target or value")
        if self._is_macos():
            parts = [item.strip() for item in chord.split("+") if item.strip()]
            if not parts:
                return NativeExecutionResult(status="failed", output=f"invalid hotkey: {chord}")
            key = parts[-1]
            modifiers = [item for item in parts[:-1]]
            script = self._apple_key_script(key, modifiers=modifiers)
            completed = self._run_subprocess(["osascript", "-e", script], shell=False)
            return self._result_from_completed(completed)
        if self._is_linux():
            if not self._linux_has_xdotool():
                return NativeExecutionResult(status="failed", output="hotkey on linux requires 'xdotool' in PATH")
            parts = [item.strip() for item in chord.split("+") if item.strip()]
            if not parts:
                return NativeExecutionResult(status="failed", output=f"invalid hotkey: {chord}")
            resolved = [self._xdotool_key_name(item.lower()) for item in parts]
            completed = self._run_subprocess(["xdotool", "key", "+".join(resolved)], shell=False)
            return self._result_from_completed(completed)
        return NativeExecutionResult(
            status="failed",
            output=f"hotkey is only implemented for macOS/linux native runtime (platform={self.platform_name})",
        )

    def _execute_click(self, action: dict[str, Any]) -> NativeExecutionResult:
        raw = str(action.get("target") or action.get("value") or "").strip()
        if not raw:
            return NativeExecutionResult(status="failed", output="click action requires target or value")
        coords = self._parse_coordinates(raw)
        if coords is None:
            return NativeExecutionResult(
                status="failed",
                output=f"click target must be coordinates, got '{raw}'. Expected 'x,y' or 'x=.. y=..'.",
            )
        x, y = coords
        if self._is_macos():
            script = f'tell application "System Events" to click at {{{x}, {y}}}'
            completed = self._run_subprocess(["osascript", "-e", script], shell=False)
            return self._result_from_completed(completed)
        if self._is_linux():
            if not self._linux_has_xdotool():
                return NativeExecutionResult(status="failed", output="click on linux requires 'xdotool' in PATH")
            completed = self._run_subprocess(["xdotool", "mousemove", str(x), str(y), "click", "1"], shell=False)
            return self._result_from_completed(completed)
        return NativeExecutionResult(
            status="failed",
            output=f"click is only implemented for macOS/linux native runtime (platform={self.platform_name})",
        )

    def _execute_run_shell(self, action: dict[str, Any]) -> NativeExecutionResult:
        command = str(action.get("value") or action.get("target") or "").strip()
        if not command:
            return NativeExecutionResult(status="failed", output="run_shell action requires value or target")
        completed = self._run_subprocess(command, shell=True)
        return self._result_from_completed(completed)

    def _result_from_completed(self, completed: subprocess.CompletedProcess[str]) -> NativeExecutionResult:
        status = "ok" if completed.returncode == 0 else "failed"
        output = (completed.stdout or completed.stderr or "").strip()
        if not output:
            output = f"exit={completed.returncode}"
        return NativeExecutionResult(status=status, output=output)

    def _run_subprocess(self, cmd: list[str] | str, *, shell: bool) -> subprocess.CompletedProcess[str]:
        if shell and isinstance(cmd, list):
            cmd = " ".join(shlex.quote(part) for part in cmd)
        return subprocess.run(
            cmd,
            shell=shell,
            check=False,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
        )

    @staticmethod
    def _parse_duration_seconds(raw: str) -> float:
        if not raw:
            return 1.0
        match = _DURATION_RE.match(raw)
        if not match:
            return float(raw)
        value = float(match.group("value"))
        unit = (match.group("unit") or "s").lower()
        if unit in {"ms"}:
            return value / 1000.0
        if unit in {"m", "min", "mins", "minute", "minutes"}:
            return value * 60.0
        return value

    @staticmethod
    def _parse_coordinates(raw: str) -> tuple[int, int] | None:
        match = _COORD_PAIR_RE.match(raw)
        if match:
            return int(match.group("x")), int(match.group("y"))
        match = _COORD_NAMED_RE.match(raw)
        if match:
            return int(match.group("x")), int(match.group("y"))
        return None

    @staticmethod
    def _escape_applescript_string(value: str) -> str:
        escaped = value.replace("\\", "\\\\")
        return escaped.replace('"', '\\"')

    @staticmethod
    def _apple_key_script(key: str, modifiers: list[str]) -> str:
        modifier_tokens = [token for token in (_APPLE_MODIFIERS.get(item) for item in modifiers) if token]
        if len(key) == 1:
            base = f'keystroke "{NativeDesktopExecutor._escape_applescript_string(key)}"'
        else:
            key_code = _APPLE_KEY_CODES.get(key)
            if key_code is None:
                raise ValueError(f"unsupported key '{key}'")
            base = f"key code {key_code}"

        if modifier_tokens:
            modifiers_clause = ", ".join(modifier_tokens)
            return f'tell application "System Events" to {base} using {{{modifiers_clause}}}'
        return f'tell application "System Events" to {base}'

    def _is_macos(self) -> bool:
        return self.platform_name == "darwin"

    def _is_linux(self) -> bool:
        return self.platform_name.startswith("linux")

    def _is_windows(self) -> bool:
        return self.platform_name.startswith("win")

    def _linux_has_xdotool(self) -> bool:
        return shutil.which("xdotool") is not None

    @staticmethod
    def _xdotool_key_name(key: str) -> str:
        if len(key) == 1:
            return key
        return _XDOTOOL_KEY_ALIASES.get(key, key)
