from __future__ import annotations

import json
import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib import error, request

from .models import SynthesisResult


class TextToSpeechBackend(Protocol):
    name: str

    def synthesize(
        self,
        text: str,
        *,
        output_path: str = "",
        voice: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> SynthesisResult: ...


@dataclass
class NoopTTSBackend:
    name: str = "noop-tts"

    def synthesize(
        self,
        text: str,
        *,
        output_path: str = "",
        voice: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> SynthesisResult:
        return SynthesisResult(
            ok=False,
            backend=self.name,
            error="tts backend not configured",
            output_path=str(output_path or ""),
            metadata={
                "voice": str(voice or ""),
                "text_length": len(str(text or "")),
                **dict(metadata or {}),
            },
        )


@dataclass
class StaticTTSBackend:
    name: str = "static-tts"

    def synthesize(
        self,
        text: str,
        *,
        output_path: str = "",
        voice: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> SynthesisResult:
        out = _resolve_output_path(output_path, suffix=".txt")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(str(text), encoding="utf-8")
        return SynthesisResult(
            ok=True,
            backend=self.name,
            output_path=str(out),
            metadata={
                "voice": str(voice or ""),
                "text_length": len(str(text or "")),
                **dict(metadata or {}),
            },
        )


@dataclass
class CommandTTSBackend:
    command: str
    timeout_seconds: float = 60.0
    default_extension: str = ".txt"
    name: str = "command-tts"

    def synthesize(
        self,
        text: str,
        *,
        output_path: str = "",
        voice: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> SynthesisResult:
        out = _resolve_output_path(output_path, suffix=self.default_extension)
        rendered = self._render_command(text=text, output_path=str(out), voice=voice)
        try:
            proc = subprocess.run(
                rendered,
                shell=True,
                capture_output=True,
                text=False,
                timeout=max(1.0, float(self.timeout_seconds)),
                check=False,
            )
        except Exception as exc:
            return SynthesisResult(
                ok=False,
                backend=self.name,
                output_path=str(out),
                error=f"command transport failed: {exc}",
                metadata={"command": rendered, **dict(metadata or {})},
            )
        if proc.returncode != 0:
            stderr = (proc.stderr or b"").decode("utf-8", errors="ignore").strip()
            return SynthesisResult(
                ok=False,
                backend=self.name,
                output_path=str(out),
                error=f"command failed ({proc.returncode}): {stderr or 'no stderr'}",
                metadata={"command": rendered, **dict(metadata or {})},
            )
        if not out.exists():
            stdout = proc.stdout or b""
            if stdout:
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(stdout)
        if not out.exists():
            return SynthesisResult(
                ok=False,
                backend=self.name,
                output_path=str(out),
                error="command succeeded but produced no output artifact",
                metadata={"command": rendered, **dict(metadata or {})},
            )
        return SynthesisResult(
            ok=True,
            backend=self.name,
            output_path=str(out),
            metadata={
                "voice": str(voice or ""),
                "text_length": len(str(text or "")),
                "command": rendered,
                **dict(metadata or {}),
            },
        )

    def _render_command(self, *, text: str, output_path: str, voice: str) -> str:
        text_value = str(text or "")
        voice_value = str(voice or "")
        context = {
            "text": text_value,
            "text_q": shlex.quote(text_value),
            "output_path": str(output_path),
            "output_path_q": shlex.quote(str(output_path)),
            "voice": voice_value,
            "voice_q": shlex.quote(voice_value),
        }
        return str(self.command).format(**context)


@dataclass
class OpenAITTSBackend:
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini-tts"
    default_voice: str = "alloy"
    audio_format: str = "mp3"
    api_key_env: str = "OPENAI_API_KEY"
    timeout_seconds: float = 120.0
    name: str = "openai-tts"

    def synthesize(
        self,
        text: str,
        *,
        output_path: str = "",
        voice: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> SynthesisResult:
        api_key = str(os.getenv(self.api_key_env, "")).strip()
        if not api_key:
            return SynthesisResult(
                ok=False,
                backend=self.name,
                output_path=str(output_path or ""),
                error=f"missing API key env var: {self.api_key_env}",
                metadata=dict(metadata or {}),
            )
        out = _resolve_output_path(output_path, suffix=f".{self.audio_format.strip('.') or 'mp3'}")
        model = str(self.model).strip() or "gpt-4o-mini-tts"
        chosen_voice = str(voice or self.default_voice or "alloy").strip() or "alloy"
        payload = json.dumps(
            {
                "model": model,
                "input": str(text or ""),
                "voice": chosen_voice,
                "format": str(self.audio_format or "mp3"),
            }
        ).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/octet-stream",
        }
        base = str(self.base_url).rstrip("/")
        req = request.Request(url=f"{base}/audio/speech", data=payload, headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=max(1.0, float(self.timeout_seconds))) as resp:
                blob = resp.read()
        except error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="ignore")
            finally:
                try:
                    exc.close()
                except Exception:
                    pass
                try:
                    exc.fp = None
                    exc.file = None
                except Exception:
                    pass
            return SynthesisResult(
                ok=False,
                backend=self.name,
                output_path=str(out),
                error=f"openai tts failed ({exc.code}): {detail}",
                metadata={"voice": chosen_voice, **dict(metadata or {})},
            )
        except error.URLError as exc:
            reason = exc.reason
            close_fn = getattr(reason, "close", None)
            if callable(close_fn):
                try:
                    close_fn()
                except Exception:
                    pass
            try:
                setattr(reason, "fp", None)
                setattr(reason, "file", None)
            except Exception:
                pass
            return SynthesisResult(
                ok=False,
                backend=self.name,
                output_path=str(out),
                error=f"openai tts transport: {exc.reason}",
                metadata={"voice": chosen_voice, **dict(metadata or {})},
            )

        if not blob:
            return SynthesisResult(
                ok=False,
                backend=self.name,
                output_path=str(out),
                error="openai tts returned empty audio payload",
                metadata={"voice": chosen_voice, **dict(metadata or {})},
            )
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(blob)
        return SynthesisResult(
            ok=True,
            backend=self.name,
            output_path=str(out),
            metadata={
                "voice": chosen_voice,
                "text_length": len(str(text or "")),
                "model": model,
                **dict(metadata or {}),
            },
        )


def _resolve_output_path(output_path: str, *, suffix: str) -> Path:
    cleaned = str(output_path or "").strip()
    if cleaned:
        return Path(cleaned).expanduser()
    ext = suffix if suffix.startswith(".") else f".{suffix}"
    return Path.cwd() / f"novaadapt_voice_output{ext}"


def build_tts_backend(kind: str | None = None) -> TextToSpeechBackend:
    backend_kind = str(kind or os.getenv("NOVAADAPT_TTS_BACKEND", "noop")).strip().lower()
    if backend_kind in {"", "noop", "none"}:
        return NoopTTSBackend()
    if backend_kind == "static":
        return StaticTTSBackend()
    if backend_kind in {"cmd", "command", "shell"}:
        command = str(os.getenv("NOVAADAPT_TTS_COMMAND", "")).strip()
        if not command:
            raise ValueError(
                "NOVAADAPT_TTS_COMMAND is required for command TTS backend "
                "(use placeholders like {text_q}, {output_path_q}, {voice_q})"
            )
        timeout_raw = str(os.getenv("NOVAADAPT_TTS_TIMEOUT_SECONDS", "60")).strip() or "60"
        try:
            timeout = float(timeout_raw)
        except ValueError:
            timeout = 60.0
        ext = str(os.getenv("NOVAADAPT_TTS_COMMAND_DEFAULT_EXTENSION", ".txt")).strip() or ".txt"
        return CommandTTSBackend(
            command=command,
            timeout_seconds=max(1.0, timeout),
            default_extension=ext if ext.startswith(".") else f".{ext}",
        )
    if backend_kind in {"openai", "openai-speech"}:
        base_url = str(os.getenv("NOVAADAPT_TTS_OPENAI_BASE_URL", "https://api.openai.com/v1")).strip()
        model = str(os.getenv("NOVAADAPT_TTS_OPENAI_MODEL", "gpt-4o-mini-tts")).strip()
        default_voice = str(os.getenv("NOVAADAPT_TTS_OPENAI_VOICE", "alloy")).strip()
        audio_format = str(os.getenv("NOVAADAPT_TTS_OPENAI_FORMAT", "mp3")).strip()
        key_env = str(os.getenv("NOVAADAPT_TTS_OPENAI_API_KEY_ENV", "OPENAI_API_KEY")).strip()
        timeout_raw = str(os.getenv("NOVAADAPT_TTS_TIMEOUT_SECONDS", "120")).strip() or "120"
        try:
            timeout = float(timeout_raw)
        except ValueError:
            timeout = 120.0
        return OpenAITTSBackend(
            base_url=base_url or "https://api.openai.com/v1",
            model=model or "gpt-4o-mini-tts",
            default_voice=default_voice or "alloy",
            audio_format=audio_format or "mp3",
            api_key_env=key_env or "OPENAI_API_KEY",
            timeout_seconds=max(1.0, timeout),
        )
    raise ValueError(f"unsupported TTS backend: {backend_kind}")
