from __future__ import annotations

from typing import Callable

from .service import NovaAdaptService
from .terminal import TerminalSessionManager


def get_browser_status(handler, service: NovaAdaptService) -> int:
    handler._send_json(200, service.browser_status())
    return 200


def get_browser_pages(handler, service: NovaAdaptService) -> int:
    handler._send_json(200, service.browser_pages())
    return 200


def get_terminal_sessions(handler, terminal_manager: TerminalSessionManager) -> int:
    handler._send_json(200, terminal_manager.list_sessions())
    return 200


def get_terminal_session_item(handler, terminal_manager: TerminalSessionManager, path: str) -> int:
    session_id = path.removeprefix("/terminal/sessions/").strip("/")
    if not session_id:
        handler._send_json(404, {"error": "Not found"})
        return 404
    try:
        handler._send_json(200, terminal_manager.get_session(session_id))
        return 200
    except ValueError as exc:
        handler._send_json(404, {"error": str(exc)})
        return 404


def get_terminal_output(
    handler,
    terminal_manager: TerminalSessionManager,
    query_single: Callable[[dict[str, list[str]], str], str | None],
    path: str,
    query: dict[str, list[str]],
) -> int:
    session_id = path.removeprefix("/terminal/sessions/").removesuffix("/output").strip("/")
    if not session_id:
        handler._send_json(404, {"error": "Not found"})
        return 404
    since_seq = int(query_single(query, "since_seq") or 0)
    limit = int(query_single(query, "limit") or 200)
    try:
        handler._send_json(
            200,
            terminal_manager.read_output(
                session_id,
                since_seq=max(0, since_seq),
                limit=max(1, min(1000, limit)),
            ),
        )
        return 200
    except ValueError as exc:
        handler._send_json(404, {"error": str(exc)})
        return 404


def post_terminal_start(
    handler,
    terminal_manager: TerminalSessionManager,
    path: str,
    payload: dict[str, object],
) -> int:
    command = payload.get("command")
    cwd = payload.get("cwd")
    shell = payload.get("shell")
    max_chunks = int(payload.get("max_chunks", 4000))

    def _start() -> tuple[int, object]:
        return (
            201,
            terminal_manager.start_session(
                command=(str(command) if command is not None else None),
                cwd=(str(cwd) if cwd is not None else None),
                shell=(str(shell) if shell is not None else None),
                max_chunks=max(200, min(20000, max_chunks)),
            ),
        )

    return handler._respond_idempotent(
        path=path,
        payload=payload,
        operation=_start,
        category="terminal",
        action="start",
        entity_type="terminal_session",
        entity_id_key="id",
    )


def post_terminal_input(
    handler,
    terminal_manager: TerminalSessionManager,
    path: str,
    payload: dict[str, object],
) -> int:
    session_id = path.removeprefix("/terminal/sessions/").removesuffix("/input").strip("/")
    if not session_id:
        handler._send_json(404, {"error": "Not found"})
        return 404
    raw_input = payload.get("input")
    if raw_input is None:
        raise ValueError("'input' is required")
    try:
        out = terminal_manager.write_input(session_id, str(raw_input))
        handler._audit_event(
            category="terminal",
            action="input",
            status="ok",
            entity_type="terminal_session",
            entity_id=session_id,
            payload=out,
        )
        handler._send_json(200, out)
        return 200
    except ValueError as exc:
        handler._send_json(404, {"error": str(exc)})
        return 404


def post_terminal_close(
    handler,
    terminal_manager: TerminalSessionManager,
    path: str,
    payload: dict[str, object],
) -> int:
    session_id = path.removeprefix("/terminal/sessions/").removesuffix("/close").strip("/")
    if not session_id:
        handler._send_json(404, {"error": "Not found"})
        return 404

    def _close() -> tuple[int, object]:
        return (200, terminal_manager.close_session(session_id))

    return handler._respond_idempotent(
        path=path,
        payload=payload,
        operation=_close,
        category="terminal",
        action="close",
        entity_type="terminal_session",
        entity_id=session_id,
    )


def post_browser_action(
    handler,
    service: NovaAdaptService,
    path: str,
    payload: dict[str, object],
) -> int:
    return handler._respond_idempotent(
        path=path,
        payload=payload,
        operation=lambda: (200, service.browser_action(payload)),
        category="browser",
        action="action",
        entity_type="browser_session",
    )


def post_browser_typed_action(
    handler,
    service: NovaAdaptService,
    path: str,
    payload: dict[str, object],
    *,
    action_type: str,
) -> int:
    action_payload = dict(payload)
    action_payload["type"] = action_type
    return handler._respond_idempotent(
        path=path,
        payload=action_payload,
        operation=lambda: (200, service.browser_action(action_payload)),
        category="browser",
        action=action_type,
        entity_type="browser_session",
    )


def post_browser_navigate(
    handler,
    service: NovaAdaptService,
    path: str,
    payload: dict[str, object],
) -> int:
    local_payload = dict(payload)
    url = local_payload.get("url")
    if url is not None and local_payload.get("target") is None and local_payload.get("value") is None:
        local_payload = {**local_payload, "target": str(url)}
    return post_browser_typed_action(handler, service, path, local_payload, action_type="navigate")


def post_browser_close(
    handler,
    service: NovaAdaptService,
    path: str,
    payload: dict[str, object],
) -> int:
    return handler._respond_idempotent(
        path=path,
        payload=payload,
        operation=lambda: (200, service.browser_close()),
        category="browser",
        action="close",
        entity_type="browser_session",
    )
