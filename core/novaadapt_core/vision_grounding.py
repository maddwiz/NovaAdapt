from __future__ import annotations

import base64
import json
import os
import platform
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

from novaadapt_shared import ModelRouter


_DEFAULT_VISION_PROMPT = (
    "You are NovaAdapt Vision Grounding. "
    "Given a desktop screenshot and operator goal, return strict JSON only using schema: "
    "{\"action\":{\"type\":str,\"target\":str?,\"value\":str?,\"x\":int?,\"y\":int?,\"x1\":int?,\"y1\":int?,"
    "\"x2\":int?,\"y2\":int?,\"platform\":str?,\"domain\":str?,\"service\":str?,\"entity_id\":str?},"
    "\"confidence\":float,\"reason\":str}. "
    "Prefer action types: click, type, hotkey, key, wait, scroll, drag, open_app, open_url, note. "
    "If the app is unknown but visible, still choose the best concrete action. "
    "If there is not enough information, return a note action."
)


class ScreenshotProvider(Protocol):
    def capture_png(self) -> bytes:
        ...


class OCRProvider(Protocol):
    def extract_text(self, screenshot_png: bytes) -> str:
        ...


class AccessibilityProvider(Protocol):
    def snapshot(self) -> str:
        ...


@dataclass(frozen=True)
class VisionGroundingResult:
    action: dict[str, Any]
    confidence: float
    reason: str
    raw_output: str
    screenshot_base64: str
    ocr_text: str
    accessibility_tree: str
    model_name: str
    model_id: str
    strategy: str
    vote_summary: dict[str, Any]
    attempted_models: list[str]
    model_errors: dict[str, str]


class NoopOCRProvider:
    def extract_text(self, screenshot_png: bytes) -> str:
        _ = screenshot_png
        return ""


class NoopAccessibilityProvider:
    def snapshot(self) -> str:
        return ""


class SystemScreenshotProvider:
    """Best-effort native screenshot capture without extra Python deps."""

    def capture_png(self) -> bytes:
        suffix = ".png"
        handle = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        path = Path(handle.name)
        handle.close()
        try:
            self._capture_to_path(path)
            return path.read_bytes()
        finally:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass

    def _capture_to_path(self, path: Path) -> None:
        system = platform.system().lower()
        if system == "darwin":
            subprocess.run(
                ["screencapture", "-x", str(path)],
                check=True,
                capture_output=True,
                text=True,
            )
            return
        if system == "windows":
            powershell = shutil.which("pwsh") or shutil.which("powershell")
            if not powershell:
                raise RuntimeError("powershell or pwsh is required for Windows screenshot capture")
            escaped_path = str(path).replace("'", "''")
            script = (
                "Add-Type -AssemblyName System.Windows.Forms;"
                "Add-Type -AssemblyName System.Drawing;"
                "$bounds=[System.Windows.Forms.SystemInformation]::VirtualScreen;"
                "$bmp=New-Object System.Drawing.Bitmap $bounds.Width,$bounds.Height;"
                "$gfx=[System.Drawing.Graphics]::FromImage($bmp);"
                "$gfx.CopyFromScreen($bounds.Left,$bounds.Top,0,0,$bmp.Size);"
                f"$bmp.Save('{escaped_path}',[System.Drawing.Imaging.ImageFormat]::Png);"
                "$gfx.Dispose();"
                "$bmp.Dispose();"
            )
            subprocess.run(
                [powershell, "-NoProfile", "-Command", script],
                check=True,
                capture_output=True,
                text=True,
            )
            return
        candidates = [
            ["gnome-screenshot", "-f", str(path)],
            ["scrot", str(path)],
            ["import", "-window", "root", str(path)],
        ]
        for cmd in candidates:
            if shutil.which(cmd[0]):
                subprocess.run(cmd, check=True, capture_output=True, text=True)
                return
        raise RuntimeError("no supported screenshot command found on this platform")


class TesseractOCRProvider:
    def __init__(self, binary: str | None = None, timeout_seconds: int = 20) -> None:
        self.binary = binary or os.getenv("NOVAADAPT_TESSERACT_BIN", "tesseract")
        self.timeout_seconds = max(1, int(timeout_seconds))

    def extract_text(self, screenshot_png: bytes) -> str:
        if not shutil.which(self.binary):
            return ""
        handle = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        path = Path(handle.name)
        handle.write(screenshot_png)
        handle.close()
        try:
            proc = subprocess.run(
                [self.binary, str(path), "stdout"],
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except Exception:
            return ""
        finally:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass
        if proc.returncode != 0:
            return ""
        return proc.stdout.strip()


class VisionGroundingExecutor:
    def __init__(
        self,
        *,
        router_loader: Callable[[Path], ModelRouter],
        default_config: Path,
        screenshot_provider: ScreenshotProvider | None = None,
        ocr_provider: OCRProvider | None = None,
        accessibility_provider: AccessibilityProvider | None = None,
    ) -> None:
        self.router_loader = router_loader
        self.default_config = default_config
        self.screenshot_provider = screenshot_provider or SystemScreenshotProvider()
        self.ocr_provider = ocr_provider or TesseractOCRProvider()
        self.accessibility_provider = accessibility_provider or NoopAccessibilityProvider()

    def ground(
        self,
        *,
        goal: str,
        config_path: Path | None = None,
        screenshot_png: bytes | None = None,
        app_name: str = "",
        model_name: str | None = None,
        strategy: str = "single",
        candidate_models: list[str] | None = None,
        fallback_models: list[str] | None = None,
        context: dict[str, Any] | None = None,
        ocr_text: str = "",
        accessibility_tree: str = "",
    ) -> VisionGroundingResult:
        normalized_goal = str(goal or "").strip()
        if not normalized_goal:
            raise ValueError("'goal' is required")

        image_bytes = screenshot_png if screenshot_png is not None else self.screenshot_provider.capture_png()
        encoded_image = base64.b64encode(image_bytes).decode("ascii")
        normalized_ocr = str(ocr_text or "").strip()
        if not normalized_ocr:
            normalized_ocr = self.ocr_provider.extract_text(image_bytes)
        normalized_accessibility = str(accessibility_tree or "").strip()
        if not normalized_accessibility:
            normalized_accessibility = self.accessibility_provider.snapshot()

        user_prompt = {
            "goal": normalized_goal,
            "app_name": str(app_name or "").strip(),
            "ocr_text": normalized_ocr[:6000],
            "accessibility_tree": normalized_accessibility[:12000],
            "context": context if isinstance(context, dict) else {},
        }
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _DEFAULT_VISION_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Ground the next GUI action for this goal.\n"
                            f"{json.dumps(user_prompt, ensure_ascii=True)}"
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{encoded_image}"},
                    },
                ],
            },
        ]

        router = self.router_loader(config_path or self.default_config)
        result = router.chat(
            messages=messages,
            model_name=model_name,
            strategy=strategy,
            candidate_models=candidate_models,
            fallback_models=fallback_models,
        )
        parsed = _parse_grounded_payload(result.content)
        return VisionGroundingResult(
            action=parsed["action"],
            confidence=float(parsed["confidence"]),
            reason=str(parsed["reason"]),
            raw_output=result.content,
            screenshot_base64=encoded_image,
            ocr_text=normalized_ocr,
            accessibility_tree=normalized_accessibility,
            model_name=result.model_name,
            model_id=result.model_id,
            strategy=result.strategy,
            vote_summary=result.vote_summary,
            attempted_models=result.attempted_models,
            model_errors=result.errors,
        )


def _parse_grounded_payload(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            text = "\n".join(lines[1:-1]).strip()
        else:
            text = text.strip("`").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]

    parsed: dict[str, Any] | None = None
    try:
        candidate = json.loads(text)
        if isinstance(candidate, dict):
            parsed = candidate
    except json.JSONDecodeError:
        parsed = None

    if parsed is None:
        return {
            "action": {"type": "note", "target": "vision_grounding", "value": raw[:500]},
            "confidence": 0.0,
            "reason": "model did not return valid JSON",
        }

    action = parsed.get("action")
    if not isinstance(action, dict) and isinstance(parsed.get("type"), str):
        action = {key: value for key, value in parsed.items() if key != "confidence" and key != "reason"}
    if not isinstance(action, dict):
        action = {"type": "note", "target": "vision_grounding", "value": "no actionable output"}

    normalized_action: dict[str, Any] = {}
    for key, value in action.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            normalized_action[str(key)] = value
        elif isinstance(value, dict):
            normalized_action[str(key)] = dict(value)
        elif isinstance(value, list):
            normalized_action[str(key)] = list(value)

    try:
        confidence = float(parsed.get("confidence", 0.0) or 0.0)
    except Exception:
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    reason = str(parsed.get("reason") or "").strip() or "vision grounding result"
    return {
        "action": normalized_action,
        "confidence": confidence,
        "reason": reason,
    }
