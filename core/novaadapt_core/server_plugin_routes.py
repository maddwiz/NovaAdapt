from __future__ import annotations

from .service import NovaAdaptService


def get_plugins(handler, service: NovaAdaptService) -> int:
    handler._send_json(200, service.plugins())
    return 200


def get_plugin_health(
    handler,
    service: NovaAdaptService,
    path: str,
) -> int:
    plugin_name = path.removeprefix("/plugins/").removesuffix("/health").strip("/")
    if not plugin_name:
        handler._send_json(404, {"error": "Not found"})
        return 404
    handler._send_json(200, service.plugin_health(plugin_name))
    return 200


def post_plugin_call(
    handler,
    service: NovaAdaptService,
    path: str,
    payload: dict[str, object],
) -> int:
    plugin_name = path.removeprefix("/plugins/").removesuffix("/call").strip("/")
    if not plugin_name:
        handler._send_json(404, {"error": "Not found"})
        return 404
    return handler._respond_idempotent(
        path=path,
        payload=payload,
        operation=lambda: (200, service.plugin_call(plugin_name, payload)),
        category="plugins",
        action="call",
        entity_type="plugin",
        entity_id=plugin_name,
    )
