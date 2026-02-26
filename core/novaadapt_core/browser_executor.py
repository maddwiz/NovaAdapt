from __future__ import annotations

import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse


_DOMAIN_SPLIT_RE = re.compile(r"[\s,]+")
_SCREENSHOT_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")
_SENSITIVE_TOKENS = (
    "password",
    "passwd",
    "pwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "cvv",
    "card",
    "ssn",
)


@dataclass(frozen=True)
class BrowserExecutionResult:
    status: str
    output: str
    data: dict[str, Any] | None = None


class BrowserExecutor:
    """Playwright-backed browser automation runtime.

    This runtime is optional and initializes lazily so NovaAdapt can run without
    Playwright unless browser transport/routes are used.
    """

    def __init__(
        self,
        *,
        browser_name: str | None = None,
        headless: bool | None = None,
        timeout_seconds: int = 30,
        default_timeout_ms: int | None = None,
        allowlist: list[str] | None = None,
        blocklist: list[str] | None = None,
        allow_sensitive_fill: bool | None = None,
        screenshot_dir: Path | None = None,
        playwright_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.browser_name = str(browser_name or os.getenv("NOVAADAPT_BROWSER_NAME", "chromium")).strip().lower() or "chromium"
        self.headless = _parse_bool(
            headless,
            default=_parse_bool_env("NOVAADAPT_BROWSER_HEADLESS", default=True),
        )
        self.timeout_seconds = max(1, int(timeout_seconds))
        configured_timeout_ms = default_timeout_ms if default_timeout_ms is not None else int(
            os.getenv("NOVAADAPT_BROWSER_TIMEOUT_MS", "15000")
        )
        self.default_timeout_ms = max(100, int(configured_timeout_ms))
        self.allowed_domains = _normalize_domains(
            allowlist if allowlist is not None else _split_domains(os.getenv("NOVAADAPT_BROWSER_ALLOWLIST", ""))
        )
        self.blocked_domains = _normalize_domains(
            blocklist if blocklist is not None else _split_domains(os.getenv("NOVAADAPT_BROWSER_BLOCKLIST", ""))
        )
        self.allow_sensitive_fill = _parse_bool(
            allow_sensitive_fill,
            default=_parse_bool_env("NOVAADAPT_BROWSER_ALLOW_SENSITIVE_FILL", default=False),
        )
        default_shot_dir = Path(
            os.getenv("NOVAADAPT_BROWSER_SCREENSHOT_DIR", str(Path.home() / ".novaadapt" / "browser_screenshots"))
        )
        self.screenshot_dir = screenshot_dir or default_shot_dir

        self._playwright_factory = playwright_factory
        self._lock = threading.RLock()
        self._playwright_manager: Any = None
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None
        self._pages: dict[str, Any] = {}
        self._current_page_id: str | None = None
        self._page_seq = 0

    @staticmethod
    def capabilities() -> list[str]:
        return [
            "navigate",
            "click_selector",
            "fill",
            "extract_text",
            "screenshot",
            "wait_for_selector",
            "evaluate_js",
            "new_context",
            "new_page",
            "list_pages",
            "switch_page",
            "close_page",
        ]

    def probe(self) -> dict[str, Any]:
        with self._lock:
            try:
                page = self._ensure_page()
            except Exception as exc:
                return {
                    "ok": False,
                    "transport": "browser",
                    "browser": self.browser_name,
                    "headless": self.headless,
                    "allowlist": sorted(self.allowed_domains),
                    "blocklist": sorted(self.blocked_domains),
                    "error": str(exc),
                    "capabilities": self.capabilities(),
                }
            return {
                "ok": True,
                "transport": "browser",
                "browser": self.browser_name,
                "headless": self.headless,
                "allowlist": sorted(self.allowed_domains),
                "blocklist": sorted(self.blocked_domains),
                "url": str(getattr(page, "url", "") or "about:blank"),
                "capabilities": self.capabilities(),
            }

    def execute_action(self, action: dict[str, Any]) -> BrowserExecutionResult:
        action_type = str(action.get("type", "")).strip().lower()
        if not action_type:
            return BrowserExecutionResult(status="failed", output="Browser action missing required field: type")

        handlers: dict[str, Callable[[dict[str, Any]], BrowserExecutionResult]] = {
            "navigate": self._action_navigate,
            "goto": self._action_navigate,
            "click_selector": self._action_click_selector,
            "click": self._action_click_selector,
            "fill": self._action_fill,
            "extract_text": self._action_extract_text,
            "screenshot": self._action_screenshot,
            "wait_for_selector": self._action_wait_for_selector,
            "evaluate_js": self._action_evaluate_js,
            "new_context": self._action_new_context,
            "reset_context": self._action_new_context,
            "new_page": self._action_new_page,
            "list_pages": self._action_list_pages,
            "switch_page": self._action_switch_page,
            "focus_page": self._action_switch_page,
            "close_page": self._action_close_page,
        }
        handler = handlers.get(action_type)
        if handler is None:
            return BrowserExecutionResult(
                status="failed",
                output=(
                    f"Unsupported browser action type '{action_type}'. "
                    f"Supported: {', '.join(sorted(handlers.keys()))}"
                ),
            )

        with self._lock:
            try:
                return handler(action)
            except Exception as exc:
                return BrowserExecutionResult(status="failed", output=f"Browser execution error: {exc}")

    def close(self) -> BrowserExecutionResult:
        with self._lock:
            self._close_locked()
            return BrowserExecutionResult(status="ok", output="browser session closed")

    def _action_navigate(self, action: dict[str, Any]) -> BrowserExecutionResult:
        url = str(action.get("url") or action.get("target") or action.get("value") or "").strip()
        if not url:
            return BrowserExecutionResult(status="failed", output="navigate requires url/target/value")

        blocked_reason = self._validate_url(url)
        if blocked_reason:
            return BrowserExecutionResult(status="blocked", output=blocked_reason)

        page = self._ensure_page()
        wait_until = str(action.get("wait_until") or "domcontentloaded").strip() or "domcontentloaded"
        timeout_ms = self._timeout_ms(action)
        response = page.goto(url, wait_until=wait_until, timeout=timeout_ms)
        status_code = getattr(response, "status", None) if response is not None else None
        final_url = str(getattr(page, "url", url) or url)
        return BrowserExecutionResult(
            status="ok",
            output=f"navigated to {final_url}",
            data={"url": final_url, "status_code": status_code, "page_id": self._current_page_id},
        )

    def _action_click_selector(self, action: dict[str, Any]) -> BrowserExecutionResult:
        selector = self._selector_from_action(action)
        if not selector:
            return BrowserExecutionResult(status="failed", output="click_selector requires selector/target/value")

        page = self._ensure_page()
        page.click(
            selector,
            timeout=self._timeout_ms(action),
            button=str(action.get("button") or "left"),
            force=bool(action.get("force", False)),
        )
        return BrowserExecutionResult(
            status="ok",
            output=f"clicked selector {selector}",
            data={"selector": selector, "page_id": self._current_page_id},
        )

    def _action_fill(self, action: dict[str, Any]) -> BrowserExecutionResult:
        selector = self._selector_from_action(action)
        if not selector:
            return BrowserExecutionResult(status="failed", output="fill requires selector/target")
        value = str(action.get("value") if action.get("value") is not None else action.get("text") or "")

        allow_sensitive = self.allow_sensitive_fill
        if action.get("allow_sensitive_fill") is not None:
            allow_sensitive = bool(action.get("allow_sensitive_fill"))
        if not allow_sensitive and self._is_sensitive_fill(selector, value):
            return BrowserExecutionResult(
                status="blocked",
                output="fill blocked by policy; set allow_sensitive_fill=true for explicit approval",
                data={"selector": selector},
            )

        page = self._ensure_page()
        page.fill(selector, value, timeout=self._timeout_ms(action))
        return BrowserExecutionResult(
            status="ok",
            output=f"filled selector {selector}",
            data={"selector": selector, "page_id": self._current_page_id},
        )

    def _action_extract_text(self, action: dict[str, Any]) -> BrowserExecutionResult:
        selector = self._selector_from_action(action)
        page = self._ensure_page()
        if selector:
            locator = page.locator(selector)
            text = str(locator.inner_text(timeout=self._timeout_ms(action)))
        else:
            text = str(page.text_content("body") or "")
        preview = text.strip()
        if len(preview) > 120:
            preview = preview[:117] + "..."
        return BrowserExecutionResult(
            status="ok",
            output=(f"extracted text from {selector}: {preview}" if selector else f"extracted page text: {preview}"),
            data={"selector": selector or "body", "text": text, "page_id": self._current_page_id},
        )

    def _action_screenshot(self, action: dict[str, Any]) -> BrowserExecutionResult:
        page = self._ensure_page()
        output_path = self._screenshot_output_path(
            str(action.get("path") or action.get("target") or action.get("value") or "")
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(output_path), full_page=bool(action.get("full_page", True)))
        return BrowserExecutionResult(
            status="ok",
            output=f"screenshot saved: {output_path}",
            data={"path": str(output_path), "page_id": self._current_page_id},
        )

    def _action_wait_for_selector(self, action: dict[str, Any]) -> BrowserExecutionResult:
        selector = self._selector_from_action(action)
        if not selector:
            return BrowserExecutionResult(status="failed", output="wait_for_selector requires selector/target/value")
        state = str(action.get("state") or "visible").strip() or "visible"

        page = self._ensure_page()
        page.wait_for_selector(selector, state=state, timeout=self._timeout_ms(action))
        return BrowserExecutionResult(
            status="ok",
            output=f"selector ready: {selector} ({state})",
            data={"selector": selector, "state": state, "page_id": self._current_page_id},
        )

    def _action_evaluate_js(self, action: dict[str, Any]) -> BrowserExecutionResult:
        script = str(action.get("script") or action.get("value") or action.get("target") or "").strip()
        if not script:
            return BrowserExecutionResult(status="failed", output="evaluate_js requires script/value/target")

        page = self._ensure_page()
        if "arg" in action:
            result = page.evaluate(script, action.get("arg"))
        else:
            result = page.evaluate(script)
        return BrowserExecutionResult(
            status="ok",
            output="script evaluated",
            data={"result": result, "page_id": self._current_page_id},
        )

    def _action_new_context(self, action: dict[str, Any]) -> BrowserExecutionResult:
        _ = action
        if self._playwright_factory is None:
            # Ensures consistent missing-runtime error behavior.
            self._ensure_page()
        if self._context is not None:
            close_fn = getattr(self._context, "close", None)
            if callable(close_fn):
                try:
                    close_fn()
                except Exception:
                    pass
        self._context = None
        self._page = None
        self._pages = {}
        self._current_page_id = None
        page = self._ensure_page()
        return BrowserExecutionResult(
            status="ok",
            output="browser context reset",
            data={
                "page_id": self._current_page_id,
                "url": str(getattr(page, "url", "") or "about:blank"),
            },
        )

    def _action_new_page(self, action: dict[str, Any]) -> BrowserExecutionResult:
        self._ensure_context()
        page, page_id = self._create_page(make_current=True)
        url = str(action.get("url") or action.get("target") or action.get("value") or "").strip()
        if url:
            blocked_reason = self._validate_url(url)
            if blocked_reason:
                return BrowserExecutionResult(status="blocked", output=blocked_reason, data={"page_id": page_id})
            wait_until = str(action.get("wait_until") or "domcontentloaded").strip() or "domcontentloaded"
            timeout_ms = self._timeout_ms(action)
            response = page.goto(url, wait_until=wait_until, timeout=timeout_ms)
            status_code = getattr(response, "status", None) if response is not None else None
            return BrowserExecutionResult(
                status="ok",
                output=f"new page opened: {url}",
                data={
                    "page_id": page_id,
                    "url": str(getattr(page, "url", url) or url),
                    "status_code": status_code,
                },
            )
        return BrowserExecutionResult(
            status="ok",
            output="new page opened",
            data={"page_id": page_id, "url": str(getattr(page, "url", "") or "about:blank")},
        )

    def _action_list_pages(self, action: dict[str, Any]) -> BrowserExecutionResult:
        _ = action
        self._normalize_pages()
        pages: list[dict[str, Any]] = []
        for page_id, page in self._pages.items():
            pages.append(
                {
                    "page_id": page_id,
                    "url": str(getattr(page, "url", "") or "about:blank"),
                    "current": page_id == self._current_page_id,
                }
            )
        return BrowserExecutionResult(
            status="ok",
            output=f"listed {len(pages)} page(s)",
            data={
                "pages": pages,
                "count": len(pages),
                "current_page_id": self._current_page_id,
            },
        )

    def _action_switch_page(self, action: dict[str, Any]) -> BrowserExecutionResult:
        self._normalize_pages()
        resolved_id = self._resolve_page_id(action)
        if not resolved_id:
            return BrowserExecutionResult(
                status="failed",
                output="switch_page requires valid page_id or index",
            )
        page = self._pages.get(resolved_id)
        if page is None:
            return BrowserExecutionResult(status="failed", output=f"page not found: {resolved_id}")
        self._current_page_id = resolved_id
        self._page = page
        return BrowserExecutionResult(
            status="ok",
            output=f"switched to page {resolved_id}",
            data={
                "page_id": resolved_id,
                "url": str(getattr(page, "url", "") or "about:blank"),
            },
        )

    def _action_close_page(self, action: dict[str, Any]) -> BrowserExecutionResult:
        self._normalize_pages()
        resolved_id = self._resolve_page_id(action, allow_current=True)
        if not resolved_id:
            return BrowserExecutionResult(status="failed", output="no page available to close")
        page = self._pages.get(resolved_id)
        if page is None:
            return BrowserExecutionResult(status="failed", output=f"page not found: {resolved_id}")

        close_fn = getattr(page, "close", None)
        if callable(close_fn):
            try:
                close_fn()
            except Exception:
                pass
        self._pages.pop(resolved_id, None)
        if self._current_page_id == resolved_id:
            self._current_page_id = None
            self._page = None
        self._normalize_pages()
        return BrowserExecutionResult(
            status="ok",
            output=f"closed page {resolved_id}",
            data={
                "closed_page_id": resolved_id,
                "remaining": len(self._pages),
                "current_page_id": self._current_page_id,
            },
        )

    def _selector_from_action(self, action: dict[str, Any]) -> str:
        return str(action.get("selector") or action.get("target") or action.get("value") or "").strip()

    def _timeout_ms(self, action: dict[str, Any]) -> int:
        raw = action.get("timeout_ms")
        if raw is None:
            return self.default_timeout_ms
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return self.default_timeout_ms
        return max(100, min(300000, value))

    def _validate_url(self, raw_url: str) -> str | None:
        parsed = urlparse(raw_url)
        if parsed.scheme not in {"http", "https"}:
            return "navigate blocked: only http/https URLs are allowed"
        host = str(parsed.hostname or "").strip().lower()
        if not host:
            return "navigate blocked: URL host is required"

        if self._domain_matches(host, self.blocked_domains):
            return f"navigate blocked by domain blocklist: {host}"
        if self.allowed_domains and not self._domain_matches(host, self.allowed_domains):
            return f"navigate blocked by domain allowlist: {host}"
        return None

    @staticmethod
    def _domain_matches(host: str, rules: set[str]) -> bool:
        if not rules:
            return False
        for rule in rules:
            if host == rule or host.endswith("." + rule):
                return True
        return False

    @staticmethod
    def _is_sensitive_fill(selector: str, value: str) -> bool:
        lowered = f"{selector} {value}".lower()
        return any(token in lowered for token in _SENSITIVE_TOKENS)

    def _screenshot_output_path(self, requested: str) -> Path:
        now = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
        requested = str(requested or "").strip()
        if requested:
            candidate = Path(requested).name
            candidate = _SCREENSHOT_SAFE_RE.sub("-", candidate).strip(".-")
            if not candidate:
                candidate = f"shot-{now}.png"
            if "." not in candidate:
                candidate = candidate + ".png"
        else:
            candidate = f"shot-{now}.png"
        return self.screenshot_dir / candidate

    def _ensure_page(self):
        self._normalize_pages()
        if self._page is not None:
            return self._page

        if self._playwright_factory is None:
            try:
                from playwright.sync_api import sync_playwright  # type: ignore
            except Exception as exc:  # pragma: no cover - depends on optional dependency
                raise RuntimeError(
                    "Playwright is not installed. Install with 'pip install playwright' and run "
                    "'python -m playwright install chromium'."
                ) from exc
            self._playwright_factory = sync_playwright

        if self._playwright is None:
            manager = self._playwright_factory()
            self._playwright_manager = manager
            self._playwright = manager.start() if hasattr(manager, "start") else manager

        self._ensure_context()
        if self._page is not None:
            return self._page
        page, _page_id = self._create_page(make_current=True)
        return page

    def _close_locked(self) -> None:
        for resource_name in ("_page", "_context", "_browser", "_playwright"):
            resource = getattr(self, resource_name)
            if resource is None:
                continue
            close_fn = getattr(resource, "close", None)
            if callable(close_fn):
                try:
                    close_fn()
                except Exception:
                    pass
            setattr(self, resource_name, None)
        self._pages = {}
        self._current_page_id = None

        manager = self._playwright_manager
        if manager is not None and hasattr(manager, "stop"):
            try:
                manager.stop()
            except Exception:
                pass
        self._playwright_manager = None

    def _ensure_context(self) -> None:
        if self._browser is None:
            launcher = getattr(self._playwright, self.browser_name, None)
            if launcher is None:
                raise RuntimeError(
                    f"Unsupported Playwright browser '{self.browser_name}'. "
                    "Use chromium, firefox, or webkit."
                )
            self._browser = launcher.launch(headless=self.headless)
        if self._context is None:
            self._context = self._browser.new_context()
            set_timeout = getattr(self._context, "set_default_timeout", None)
            if callable(set_timeout):
                set_timeout(self.default_timeout_ms)
            self._pages = {}
            self._current_page_id = None

    def _create_page(self, *, make_current: bool) -> tuple[Any, str]:
        page = self._context.new_page()
        set_page_timeout = getattr(page, "set_default_timeout", None)
        if callable(set_page_timeout):
            set_page_timeout(self.default_timeout_ms)
        page_id = self._register_page(page, make_current=make_current)
        return page, page_id

    def _register_page(self, page: Any, *, make_current: bool) -> str:
        for page_id, existing in self._pages.items():
            if existing is page:
                if make_current:
                    self._current_page_id = page_id
                    self._page = page
                return page_id
        self._page_seq += 1
        page_id = f"page-{self._page_seq}"
        self._pages[page_id] = page
        if make_current:
            self._current_page_id = page_id
            self._page = page
        return page_id

    def _normalize_pages(self) -> None:
        if not self._pages:
            self._page = None
            self._current_page_id = None
            return
        stale: list[str] = []
        for page_id, page in self._pages.items():
            is_closed = getattr(page, "is_closed", None)
            if callable(is_closed):
                try:
                    if is_closed():
                        stale.append(page_id)
                except Exception:
                    stale.append(page_id)
        for page_id in stale:
            self._pages.pop(page_id, None)
        if not self._pages:
            self._page = None
            self._current_page_id = None
            return
        if self._current_page_id not in self._pages:
            self._current_page_id = next(iter(self._pages.keys()))
        self._page = self._pages.get(self._current_page_id)

    def _resolve_page_id(self, action: dict[str, Any], *, allow_current: bool = False) -> str | None:
        requested = str(action.get("page_id") or "").strip()
        if requested:
            if requested in self._pages:
                return requested
            return None

        raw_index = action.get("index")
        if raw_index is not None:
            try:
                index = int(raw_index)
            except (TypeError, ValueError):
                return None
            keys = list(self._pages.keys())
            if not keys:
                return None
            if index < 0:
                index = len(keys) + index
            if index < 0 or index >= len(keys):
                return None
            return keys[index]

        if allow_current and self._current_page_id in self._pages:
            return self._current_page_id
        return None


def _parse_bool(value: bool | None, *, default: bool) -> bool:
    if value is None:
        return bool(default)
    return bool(value)


def _parse_bool_env(name: str, *, default: bool) -> bool:
    raw = str(os.getenv(name, "")).strip().lower()
    if not raw:
        return bool(default)
    return raw in {"1", "true", "yes", "on"}


def _split_domains(raw: str) -> list[str]:
    text = str(raw or "").strip()
    if not text:
        return []
    return [item for item in _DOMAIN_SPLIT_RE.split(text) if item]


def _normalize_domains(values: list[str]) -> set[str]:
    out: set[str] = set()
    for raw in values:
        item = str(raw or "").strip().lower().strip(".")
        if item:
            out.add(item)
    return out
