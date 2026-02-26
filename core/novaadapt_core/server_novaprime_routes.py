from __future__ import annotations

from .service import NovaAdaptService


def get_novaprime_status(handler, service: NovaAdaptService) -> int:
    handler._send_json(200, service.novaprime_status())
    return 200
