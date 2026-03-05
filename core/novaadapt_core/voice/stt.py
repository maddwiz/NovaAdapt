from __future__ import annotations

import json
import os
import shlex
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib import error, request

from .models import TranscriptionResult


class SpeechToTextBackend(Protocol):
    name: str

    def transcribe(
        self,
        audio_path: str,
        *,
        hints: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TranscriptionResult: ...


@dataclass
class NoopSTTBackend:
    name: str = "noop-stt"

    def transcribe(
        self,
        audio_path: str,
        *,
        hints: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TranscriptionResult:
        return TranscriptionResult(
            ok=False,
            backend=self.name,
            error="stt backend not configured",
            metadata={
                "audio_path": str(audio_path),
                "hints": list(hints or []),
                **dict(metadata or {}),
            },
        )


@dataclass
class StaticSTTBackend:
    text: str
    confidence: float = 1.0
    name: str = "static-stt"

    def transcribe(
        self,
        audio_path: str,
        *,
        hints: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TranscriptionResult:
        return TranscriptionResult(
            ok=True,
            text=str(self.text),
            backend=self.name,
            confidence=max(0.0, min(1.0, float(self.confidence))),
            metadata={
                "audio_path": str(audio_path),
                "hints": list(hints or []),
                **dict(metadata or {}),
            },
        )


@dataclass
class CommandSTTBackend:
    command: str
    timeout_seconds: float = 60.0
    name: str = "command-stt"

    def transcribe(
        self,
        audio_path: str,
        *,
        hints: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TranscriptionResult:
        rendered = self._render_command(audio_path=audio_path, hints=hints)
        try:
            proc = subprocess.run(
                rendered,
                shell=True,
                capture_output=True,
                text=True,
                timeout=max(1.0, float(self.timeout_seconds)),
                check=False,
            )
        except Exception as exc:
            return TranscriptionResult(
                ok=False,
                backend=self.name,
                error=f"command transport failed: {exc}",
                metadata={"command": rendered, **dict(metadata or {})},
            )
        if proc.returncode != 0:
            stderr = (proc.stderr or "").strip()
            return TranscriptionResult(
                ok=False,
                backend=self.name,
                error=f"command failed ({proc.returncode}): {stderr or 'no stderr'}",
                metadata={"command": rendered, **dict(metadata or {})},
            )
        text, confidence = self._extract_stdout(proc.stdout or "")
        if not text:
            return TranscriptionResult(
                ok=False,
                backend=self.name,
                error="command returned empty transcription",
                metadata={"command": rendered, **dict(metadata or {})},
            )
        return TranscriptionResult(
            ok=True,
            text=text,
            backend=self.name,
            confidence=confidence,
            metadata={
                "audio_path": str(audio_path),
                "hints": list(hints or []),
                "command": rendered,
                **dict(metadata or {}),
            },
        )

    def _render_command(self, *, audio_path: str, hints: list[str] | None) -> str:
        hints_text = " ".join(str(item).strip() for item in (hints or []) if str(item).strip())
        context = {
            "audio_path": str(audio_path),
            "audio_path_q": shlex.quote(str(audio_path)),
            "hints": hints_text,
            "hints_q": shlex.quote(hints_text),
        }
        return str(self.command).format(**context)

    @staticmethod
    def _extract_stdout(stdout: str) -> tuple[str, float | None]:
        text = str(stdout or "").strip()
        if not text:
            return "", None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return text, None
        if isinstance(parsed, dict):
            result_text = str(parsed.get("text", "")).strip()
            confidence_raw = parsed.get("confidence")
            confidence = None
            if isinstance(confidence_raw, (int, float)):
                confidence = max(0.0, min(1.0, float(confidence_raw)))
            return result_text or text, confidence
        return text, None


@dataclass
class OpenAISTTBackend:
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini-transcribe"
    api_key_env: str = "OPENAI_API_KEY"
    timeout_seconds: float = 120.0
    name: str = "openai-stt"

    def transcribe(
        self,
        audio_path: str,
        *,
        hints: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TranscriptionResult:
        api_key = str(os.getenv(self.api_key_env, "")).strip()
        if not api_key:
            return TranscriptionResult(
                ok=False,
                backend=self.name,
                error=f"missing API key env var: {self.api_key_env}",
                metadata={"audio_path": str(audio_path), **dict(metadata or {})},
            )
        path = Path(audio_path).expanduser()
        if not path.exists():
            return TranscriptionResult(
                ok=False,
                backend=self.name,
                error=f"audio file not found: {path}",
                metadata=dict(metadata or {}),
            )
        try:
            file_bytes = path.read_bytes()
        except Exception as exc:
            return TranscriptionResult(
                ok=False,
                backend=self.name,
                error=f"failed to read audio file: {exc}",
                metadata=dict(metadata or {}),
            )

        fields: list[tuple[str, str]] = [("model", str(self.model).strip() or "gpt-4o-mini-transcribe")]
        hints_text = " ".join(str(item).strip() for item in (hints or []) if str(item).strip())
        if hints_text:
            fields.append(("prompt", hints_text))
        language = ""
        if metadata and isinstance(metadata, dict):
            language = str(metadata.get("language", "")).strip()
        if language:
            fields.append(("language", language))
        body, boundary = _encode_multipart(
            fields=fields,
            file_field=("file", path.name or "audio.wav", file_bytes, "application/octet-stream"),
        )
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
        }
        base = str(self.base_url).rstrip("/")
        url = f"{base}/audio/transcriptions"
        req = request.Request(url=url, data=body, headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=max(1.0, float(self.timeout_seconds))) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
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
            return TranscriptionResult(
                ok=False,
                backend=self.name,
                error=f"openai stt failed ({exc.code}): {detail}",
                metadata={"audio_path": str(path), **dict(metadata or {})},
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
            return TranscriptionResult(
                ok=False,
                backend=self.name,
                error=f"openai stt transport: {exc.reason}",
                metadata={"audio_path": str(path), **dict(metadata or {})},
            )

        text = ""
        confidence: float | None = None
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {}
        if isinstance(parsed, dict):
            text = str(parsed.get("text", "")).strip()
            confidence_raw = parsed.get("confidence")
            if isinstance(confidence_raw, (int, float)):
                confidence = max(0.0, min(1.0, float(confidence_raw)))
        if not text:
            return TranscriptionResult(
                ok=False,
                backend=self.name,
                error="openai stt returned empty transcription",
                metadata={"audio_path": str(path), **dict(metadata or {})},
            )
        return TranscriptionResult(
            ok=True,
            text=text,
            backend=self.name,
            confidence=confidence,
            metadata={
                "audio_path": str(path),
                "hints": list(hints or []),
                **dict(metadata or {}),
            },
        )


def _encode_multipart(
    *,
    fields: list[tuple[str, str]],
    file_field: tuple[str, str, bytes, str],
) -> tuple[bytes, str]:
    boundary = f"----NovaAdaptVoice{uuid.uuid4().hex}"
    field_name, filename, content, mime = file_field
    chunks: list[bytes] = []
    for key, value in fields:
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(
            f'Content-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode("utf-8")
        )
    chunks.append(f"--{boundary}\r\n".encode("utf-8"))
    chunks.append(
        (
            f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
            f"Content-Type: {mime}\r\n\r\n"
        ).encode("utf-8")
    )
    chunks.append(content)
    chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), boundary


def build_stt_backend(kind: str | None = None) -> SpeechToTextBackend:
    backend_kind = str(kind or os.getenv("NOVAADAPT_STT_BACKEND", "noop")).strip().lower()
    if backend_kind in {"", "noop", "none"}:
        return NoopSTTBackend()
    if backend_kind == "static":
        text = str(os.getenv("NOVAADAPT_STT_STATIC_TEXT", "")).strip()
        confidence_raw = str(os.getenv("NOVAADAPT_STT_STATIC_CONFIDENCE", "1.0")).strip() or "1.0"
        try:
            confidence = float(confidence_raw)
        except ValueError:
            confidence = 1.0
        return StaticSTTBackend(text=text, confidence=confidence)
    if backend_kind in {"cmd", "command", "whisper", "whisper-cli"}:
        command = str(os.getenv("NOVAADAPT_STT_COMMAND", "")).strip()
        if not command:
            raise ValueError(
                "NOVAADAPT_STT_COMMAND is required for command STT backend "
                "(use placeholders like {audio_path_q} and {hints_q})"
            )
        timeout_raw = str(os.getenv("NOVAADAPT_STT_TIMEOUT_SECONDS", "60")).strip() or "60"
        try:
            timeout = float(timeout_raw)
        except ValueError:
            timeout = 60.0
        return CommandSTTBackend(command=command, timeout_seconds=max(1.0, timeout))
    if backend_kind in {"openai", "openai-transcribe"}:
        base_url = str(os.getenv("NOVAADAPT_STT_OPENAI_BASE_URL", "https://api.openai.com/v1")).strip()
        model = str(os.getenv("NOVAADAPT_STT_OPENAI_MODEL", "gpt-4o-mini-transcribe")).strip()
        key_env = str(os.getenv("NOVAADAPT_STT_OPENAI_API_KEY_ENV", "OPENAI_API_KEY")).strip()
        timeout_raw = str(os.getenv("NOVAADAPT_STT_TIMEOUT_SECONDS", "120")).strip() or "120"
        try:
            timeout = float(timeout_raw)
        except ValueError:
            timeout = 120.0
        return OpenAISTTBackend(
            base_url=base_url or "https://api.openai.com/v1",
            model=model or "gpt-4o-mini-transcribe",
            api_key_env=key_env or "OPENAI_API_KEY",
            timeout_seconds=max(1.0, timeout),
        )
    raise ValueError(f"unsupported STT backend: {backend_kind}")
