import tempfile
import unittest
from pathlib import Path

from novaadapt_core.browser_executor import BrowserExecutor


class _FakeResponse:
    def __init__(self, status: int = 200):
        self.status = status


class _FakeLocator:
    def __init__(self, text: str):
        self._text = text

    def inner_text(self, timeout=None):
        _ = timeout
        return self._text


class _FakePage:
    def __init__(self, page_name: str):
        self.page_name = page_name
        self.url = "about:blank"
        self.closed = False
        self.body_text = "hello page"
        self.last_click = None
        self.last_fill = None
        self.last_wait = None

    def is_closed(self):
        return self.closed

    def set_default_timeout(self, timeout_ms):
        _ = timeout_ms

    def goto(self, url, wait_until=None, timeout=None):
        _ = (wait_until, timeout)
        self.url = url
        return _FakeResponse(status=200)

    def click(self, selector, timeout=None, button="left", force=False):
        self.last_click = {
            "selector": selector,
            "timeout": timeout,
            "button": button,
            "force": force,
        }

    def fill(self, selector, value, timeout=None):
        self.last_fill = {
            "selector": selector,
            "value": value,
            "timeout": timeout,
        }

    def locator(self, selector):
        return _FakeLocator(f"text:{selector}")

    def text_content(self, selector):
        _ = selector
        return self.body_text

    def screenshot(self, path, full_page=True):
        _ = full_page
        Path(path).write_bytes(b"fake")

    def wait_for_selector(self, selector, state="visible", timeout=None):
        self.last_wait = {
            "selector": selector,
            "state": state,
            "timeout": timeout,
        }

    def evaluate(self, script, arg=None):
        if "return 42" in script:
            return 42
        return {"script": script, "arg": arg}

    def close(self):
        self.closed = True


class _FakeContext:
    def __init__(self):
        self.pages: list[_FakePage] = []
        self._page_seq = 0

    def set_default_timeout(self, timeout_ms):
        _ = timeout_ms

    def new_page(self):
        self._page_seq += 1
        page = _FakePage(page_name=f"p{self._page_seq}")
        self.pages.append(page)
        return page

    def close(self):
        for page in self.pages:
            page.close()


class _FakeBrowser:
    def __init__(self):
        self.contexts: list[_FakeContext] = []

    def new_context(self):
        context = _FakeContext()
        self.contexts.append(context)
        return context

    def close(self):
        for context in self.contexts:
            context.close()


class _FakeLauncher:
    def launch(self, headless=True):
        _ = headless
        return _FakeBrowser()


class _FakePlaywright:
    def __init__(self):
        self.chromium = _FakeLauncher()
        self.firefox = _FakeLauncher()
        self.webkit = _FakeLauncher()


class _FakePlaywrightManager:
    def __init__(self):
        self.started = False

    def start(self):
        self.started = True
        return _FakePlaywright()

    def stop(self):
        self.started = False


class BrowserExecutorTests(unittest.TestCase):
    def _executor(self, **kwargs):
        return BrowserExecutor(playwright_factory=_FakePlaywrightManager, **kwargs)

    def test_probe_reports_ok_with_fake_runtime(self):
        executor = self._executor()
        probe = executor.probe()
        self.assertTrue(probe["ok"])
        self.assertEqual(probe["transport"], "browser")
        self.assertIn("navigate", probe["capabilities"])

    def test_navigate_allows_matching_domain(self):
        executor = self._executor(allowlist=["example.com"])
        out = executor.execute_action({"type": "navigate", "target": "https://example.com/docs"})
        self.assertEqual(out.status, "ok")
        self.assertEqual(out.data["url"], "https://example.com/docs")

    def test_navigate_blocks_non_allowlisted_domain(self):
        executor = self._executor(allowlist=["example.com"])
        out = executor.execute_action({"type": "navigate", "target": "https://notion.so"})
        self.assertEqual(out.status, "blocked")
        self.assertIn("allowlist", out.output)

    def test_fill_blocks_sensitive_values_by_default(self):
        executor = self._executor()
        out = executor.execute_action({"type": "fill", "selector": "#password", "value": "hunter2"})
        self.assertEqual(out.status, "blocked")
        self.assertIn("allow_sensitive_fill=true", out.output)

    def test_fill_allows_sensitive_with_explicit_override(self):
        executor = self._executor()
        out = executor.execute_action(
            {
                "type": "fill",
                "selector": "#password",
                "value": "hunter2",
                "allow_sensitive_fill": True,
            }
        )
        self.assertEqual(out.status, "ok")

    def test_screenshot_path_is_sanitized(self):
        with tempfile.TemporaryDirectory() as tmp:
            executor = self._executor(screenshot_dir=Path(tmp))
            out = executor.execute_action({"type": "screenshot", "path": "../../my screenshot"})
            self.assertEqual(out.status, "ok")
            shot_path = Path(out.data["path"])
            self.assertTrue(shot_path.exists())
            self.assertTrue(str(shot_path).startswith(tmp))

    def test_page_lifecycle_new_list_switch_close(self):
        executor = self._executor()
        first_nav = executor.execute_action({"type": "navigate", "target": "https://example.com"})
        self.assertEqual(first_nav.status, "ok")
        first_page_id = str(first_nav.data["page_id"])
        self.assertTrue(first_page_id.startswith("page-"))

        second_page = executor.execute_action({"type": "new_page", "url": "https://notion.so"})
        self.assertEqual(second_page.status, "ok")
        second_page_id = str(second_page.data["page_id"])
        self.assertNotEqual(first_page_id, second_page_id)

        listed = executor.execute_action({"type": "list_pages"})
        self.assertEqual(listed.status, "ok")
        self.assertEqual(listed.data["count"], 2)
        self.assertEqual(listed.data["current_page_id"], second_page_id)

        switched = executor.execute_action({"type": "switch_page", "page_id": first_page_id})
        self.assertEqual(switched.status, "ok")
        self.assertEqual(switched.data["page_id"], first_page_id)

        closed = executor.execute_action({"type": "close_page", "page_id": second_page_id})
        self.assertEqual(closed.status, "ok")
        self.assertEqual(closed.data["closed_page_id"], second_page_id)
        self.assertEqual(closed.data["remaining"], 1)

        listed_after = executor.execute_action({"type": "list_pages"})
        self.assertEqual(listed_after.status, "ok")
        self.assertEqual(listed_after.data["count"], 1)
        self.assertEqual(listed_after.data["current_page_id"], first_page_id)

    def test_new_context_resets_page_state(self):
        executor = self._executor()
        first = executor.execute_action({"type": "navigate", "target": "https://example.com"})
        first_id = str(first.data["page_id"])
        _ = executor.execute_action({"type": "new_page", "url": "https://docs.example.com"})

        before = executor.execute_action({"type": "list_pages"})
        self.assertEqual(before.data["count"], 2)

        reset = executor.execute_action({"type": "new_context"})
        self.assertEqual(reset.status, "ok")
        reset_id = str(reset.data["page_id"])
        self.assertNotEqual(first_id, reset_id)

        after = executor.execute_action({"type": "list_pages"})
        self.assertEqual(after.status, "ok")
        self.assertEqual(after.data["count"], 1)
        self.assertEqual(after.data["current_page_id"], reset_id)

    def test_probe_handles_missing_playwright(self):
        def _boom_factory():
            raise RuntimeError("no playwright")

        executor = BrowserExecutor(playwright_factory=_boom_factory)
        probe = executor.probe()
        self.assertFalse(probe["ok"])
        self.assertIn("no playwright", probe["error"])


if __name__ == "__main__":
    unittest.main()
