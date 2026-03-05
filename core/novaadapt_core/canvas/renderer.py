from __future__ import annotations

import html
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class CanvasRenderResult:
    frame_id: str
    html: str
    created_at: str
    metadata: dict[str, Any]


class CanvasRenderer:
    def __init__(self, *, max_sections: int = 16) -> None:
        self.max_sections = max(1, int(max_sections))

    def render(
        self,
        title: str,
        *,
        sections: list[dict[str, Any]] | None = None,
        footer: str = "",
        metadata: dict[str, Any] | None = None,
        frame_id: str = "",
    ) -> CanvasRenderResult:
        normalized_sections = list(sections or [])[: self.max_sections]
        safe_title = html.escape(str(title or "Canvas"))
        safe_footer = html.escape(str(footer or ""))
        frame = str(frame_id or f"frame-{uuid.uuid4().hex[:12]}")

        section_blocks: list[str] = []
        for section in normalized_sections:
            heading = html.escape(str(section.get("heading", "") if isinstance(section, dict) else ""))
            body = html.escape(str(section.get("body", "") if isinstance(section, dict) else ""))
            meta = section.get("meta") if isinstance(section, dict) else None
            meta_badge = ""
            if isinstance(meta, str) and meta.strip():
                meta_badge = f'<span class="nova-canvas-meta">{html.escape(meta.strip())}</span>'
            section_blocks.append(
                "<section class=\"nova-canvas-section\">"
                f"<h2>{heading}</h2>"
                f"{meta_badge}"
                f"<p>{body}</p>"
                "</section>"
            )

        html_out = (
            "<!doctype html>"
            "<html><head><meta charset=\"utf-8\">"
            "<style>"
            "body{font-family:ui-sans-serif,system-ui;margin:0;padding:20px;background:#0f172a;color:#e2e8f0;}"
            ".nova-canvas{max-width:920px;margin:0 auto;display:grid;gap:14px;}"
            ".nova-canvas-section{background:#111827;border:1px solid #1f2937;border-radius:12px;padding:14px;}"
            ".nova-canvas-section h2{margin:0 0 8px 0;font-size:1.05rem;color:#93c5fd;}"
            ".nova-canvas-section p{margin:0;line-height:1.45;white-space:pre-wrap;}"
            ".nova-canvas-meta{font-size:.75rem;display:inline-block;margin-bottom:6px;color:#fcd34d;}"
            ".nova-canvas-footer{font-size:.82rem;color:#94a3b8;}"
            "</style></head><body>"
            "<main class=\"nova-canvas\">"
            f"<h1>{safe_title}</h1>"
            f"{''.join(section_blocks)}"
            f"<footer class=\"nova-canvas-footer\">{safe_footer}</footer>"
            "</main></body></html>"
        )

        return CanvasRenderResult(
            frame_id=frame,
            html=html_out,
            created_at=_utc_now(),
            metadata=dict(metadata or {}),
        )
