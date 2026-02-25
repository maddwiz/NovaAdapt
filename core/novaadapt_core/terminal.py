from __future__ import annotations

import os
import subprocess
import threading
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class _TerminalChunk:
    seq: int
    data: str
    stream: str
    created_at: str


class _TerminalSession:
    def __init__(self, session_id: str, command: list[str], cwd: str | None, max_chunks: int) -> None:
        self.session_id = session_id
        self.command = command
        self.cwd = cwd
        self.created_at = _now_iso()
        self._max_chunks = max(200, int(max_chunks))
        self._chunks: deque[_TerminalChunk] = deque(maxlen=self._max_chunks)
        self._next_seq = 1
        self._lock = threading.Lock()
        self._closed = False
        self._process = subprocess.Popen(
            command,
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
            close_fds=True,
        )
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def info(self) -> dict[str, Any]:
        with self._lock:
            open_state = self._is_open_locked()
            return {
                "id": self.session_id,
                "command": list(self.command),
                "cwd": self.cwd,
                "created_at": self.created_at,
                "pid": self._process.pid,
                "open": open_state,
                "exit_code": self._process.poll(),
                "last_seq": self._next_seq - 1,
            }

    def read_chunks(self, *, since_seq: int, limit: int) -> dict[str, Any]:
        limit = max(1, min(1000, int(limit)))
        marker = max(0, int(since_seq))
        with self._lock:
            selected: list[dict[str, Any]] = []
            next_seq = marker
            for chunk in self._chunks:
                if chunk.seq <= marker:
                    continue
                selected.append(
                    {
                        "seq": chunk.seq,
                        "data": chunk.data,
                        "stream": chunk.stream,
                        "created_at": chunk.created_at,
                    }
                )
                next_seq = chunk.seq
                if len(selected) >= limit:
                    break
            return {
                "id": self.session_id,
                "open": self._is_open_locked(),
                "exit_code": self._process.poll(),
                "chunks": selected,
                "next_seq": next_seq,
            }

    def write_input(self, text: str) -> dict[str, Any]:
        payload = str(text)
        with self._lock:
            if not self._is_open_locked():
                raise ValueError("terminal session is closed")
            stdin = self._process.stdin
            if stdin is None:
                raise ValueError("terminal stdin is unavailable")
            stdin.write(payload.encode("utf-8", errors="replace"))
            stdin.flush()
            return {
                "id": self.session_id,
                "accepted": True,
                "bytes": len(payload.encode("utf-8", errors="replace")),
                "open": self._is_open_locked(),
            }

    def close(self) -> dict[str, Any]:
        with self._lock:
            if self._closed:
                return {
                    "id": self.session_id,
                    "closed": True,
                    "already_closed": True,
                    "exit_code": self._process.poll(),
                }
            self._closed = True
            proc = self._process

        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3.0)
        return {
            "id": self.session_id,
            "closed": True,
            "already_closed": False,
            "exit_code": proc.poll(),
        }

    def _read_loop(self) -> None:
        stream = self._process.stdout
        if stream is None:
            return
        while True:
            chunk = stream.read(4096)
            if not chunk:
                break
            text = chunk.decode("utf-8", errors="replace")
            if not text:
                continue
            with self._lock:
                self._append_chunk_locked(text, stream="stdout")
        self._process.poll()

    def _append_chunk_locked(self, text: str, *, stream: str) -> None:
        self._chunks.append(
            _TerminalChunk(
                seq=self._next_seq,
                data=text,
                stream=stream,
                created_at=_now_iso(),
            )
        )
        self._next_seq += 1

    def _is_open_locked(self) -> bool:
        return (not self._closed) and self._process.poll() is None


class TerminalSessionManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, _TerminalSession] = {}

    def list_sessions(self) -> list[dict[str, Any]]:
        with self._lock:
            sessions = list(self._sessions.values())
        items = [session.info() for session in sessions]
        return sorted(items, key=lambda item: str(item.get("created_at", "")), reverse=True)

    def start_session(
        self,
        *,
        command: str | None = None,
        cwd: str | None = None,
        shell: str | None = None,
        max_chunks: int = 4000,
    ) -> dict[str, Any]:
        command_list = _resolve_command(command=command, shell=shell)
        safe_cwd = _resolve_cwd(cwd)
        session_id = uuid.uuid4().hex
        session = _TerminalSession(
            session_id=session_id,
            command=command_list,
            cwd=safe_cwd,
            max_chunks=max_chunks,
        )
        with self._lock:
            self._sessions[session_id] = session
        return session.info()

    def get_session(self, session_id: str) -> dict[str, Any]:
        session = self._lookup(session_id)
        return session.info()

    def read_output(self, session_id: str, *, since_seq: int = 0, limit: int = 200) -> dict[str, Any]:
        session = self._lookup(session_id)
        return session.read_chunks(since_seq=since_seq, limit=limit)

    def write_input(self, session_id: str, text: str) -> dict[str, Any]:
        session = self._lookup(session_id)
        return session.write_input(text)

    def close_session(self, session_id: str) -> dict[str, Any]:
        session = self._lookup(session_id)
        out = session.close()
        return out

    def close_all(self) -> None:
        with self._lock:
            sessions = list(self._sessions.values())
        for session in sessions:
            try:
                session.close()
            except Exception:
                continue

    def _lookup(self, session_id: str) -> _TerminalSession:
        normalized = str(session_id or "").strip()
        if not normalized:
            raise ValueError("terminal session id is required")
        with self._lock:
            session = self._sessions.get(normalized)
        if session is None:
            raise ValueError("terminal session not found")
        return session


def _resolve_command(command: str | None, shell: str | None) -> list[str]:
    requested = str(command or "").strip()
    selected_shell = str(shell or "").strip()
    if os.name == "nt":
        effective_shell = selected_shell or os.getenv("COMSPEC", "cmd.exe")
        if requested:
            return [effective_shell, "/c", requested]
        return [effective_shell]

    effective_shell = selected_shell or os.getenv("SHELL", "/bin/bash")
    if requested:
        return [effective_shell, "-lc", requested]
    return [effective_shell, "-i"]


def _resolve_cwd(cwd: str | None) -> str | None:
    raw = str(cwd or "").strip()
    if not raw:
        return None
    target = Path(raw).expanduser()
    if not target.exists() or not target.is_dir():
        raise ValueError(f"cwd is not a directory: {raw}")
    return str(target)
