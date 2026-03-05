from __future__ import annotations

from .service import NovaAdaptService


def get_voice_status(
    handler,
    service: NovaAdaptService,
    single,
    query: dict[str, list[str]],
) -> int:
    context = str(single(query, "context") or "api").strip() or "api"
    handler._send_json(200, service.voice_status(context=context))
    return 200


def post_voice_transcribe(
    handler,
    service: NovaAdaptService,
    payload: dict[str, object],
) -> int:
    audio_path = str(payload.get("audio_path") or payload.get("path") or "").strip()
    if not audio_path:
        raise ValueError("'audio_path' is required")
    hints_raw = payload.get("hints")
    hints: list[str]
    if isinstance(hints_raw, list):
        hints = [str(item).strip() for item in hints_raw if str(item).strip()]
    elif isinstance(hints_raw, str):
        hints = [item.strip() for item in hints_raw.split(",") if item.strip()]
    else:
        hints = []
    metadata = payload.get("metadata")
    backend = str(payload.get("backend") or "").strip()
    context = str(payload.get("context") or "api").strip() or "api"
    handler._send_json(
        200,
        service.voice_transcribe(
            audio_path,
            hints=hints,
            metadata=metadata if isinstance(metadata, dict) else {},
            backend=backend,
            context=context,
        ),
    )
    return 200


def post_voice_synthesize(
    handler,
    service: NovaAdaptService,
    payload: dict[str, object],
) -> int:
    text = str(payload.get("text") or "").strip()
    if not text:
        raise ValueError("'text' is required")
    output_path = str(payload.get("output_path") or "").strip()
    voice = str(payload.get("voice") or "").strip()
    metadata = payload.get("metadata")
    backend = str(payload.get("backend") or "").strip()
    context = str(payload.get("context") or "api").strip() or "api"
    handler._send_json(
        200,
        service.voice_synthesize(
            text,
            output_path=output_path,
            voice=voice,
            metadata=metadata if isinstance(metadata, dict) else {},
            backend=backend,
            context=context,
        ),
    )
    return 200
