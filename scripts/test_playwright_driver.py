"""Behavioral browser contract for the Playwright-backed executor driver."""
import http.server
import shutil
import tempfile
import sys
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ExecuteStage"))
from myChrome import MyChrome
from playwright_driver import (By, ChromeOptions, Keys, Select, WebDriverWait,
    PlaywrightChrome, ActionChains, InvalidSelectorException,
    StaleElementReferenceException, TimeoutException)


CHROME = Path(__file__).resolve().parents[1] / "ElectronJS" / "chrome_win64" / "chrome.exe"


class FixtureHandler(http.server.BaseHTTPRequestHandler):
    other_port = 0

    def do_GET(self):
        if self.path == "/":
            body = f"""<!doctype html><title>Fixture</title>
                <input id=query><output id=input-events></output>
                <select id=choices><option>one</option><option>two</option></select>
                <output id=select-events></output>
                <button id=open onclick="window.open('/popup','_blank')">Open</button>
                <button id=confirm onclick="if(confirm('continue?')) document.body.dataset.confirm='yes'">Confirm</button>
                <iframe id=outer src="http://127.0.0.1:{self.other_port}/outer"></iframe>
                <a id=download href=/download>Download</a>
                <script>
                query.oninput=()=>document.querySelector('#input-events').textContent='input';
                choices.onchange=()=>document.querySelector('#select-events').textContent='change';
                </script>""".encode()
            self._reply(body, "text/html; charset=utf-8")
        elif self.path == "/popup":
            self._reply(b"<!doctype html><title>Popup</title><h1>popup page</h1>", "text/html")
        elif self.path == "/inner":
            self._reply(b"<!doctype html><button id=nested>Nested frame</button>", "text/html")
        elif self.path == "/download":
            body = b"playwright-download-content"
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", "attachment; filename=fixture.txt")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self._reply(b"<!doctype html><iframe src='/inner'></iframe>", "text/html")

    def _reply(self, body, content_type):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


def serve(handler):
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


class PlaywrightDriverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.child = serve(FixtureHandler)
        FixtureHandler.other_port = cls.child.server_port
        cls.root = serve(FixtureHandler)
        cls.url = f"http://127.0.0.1:{cls.root.server_port}/"

    @classmethod
    def tearDownClass(cls):
        for server in (cls.root, cls.child):
            server.shutdown()
            server.server_close()

    def make_browser(self, profile, downloads):
        options = ChromeOptions()
        options.binary_location = str(CHROME)
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1280,900")
        options.add_argument(f"--user-data-dir={profile}")
        options.add_experimental_option("prefs", {
            "download.default_directory": str(downloads),
            "download.prompt_for_download": False,
        })
        return MyChrome(options=options)

    def make_temp(self):
        root = Path(tempfile.mkdtemp(prefix="easyspider-playwright-test-"))
        self.addCleanup(shutil.rmtree, root, True)
        return root

    def test_xpath_input_select_script_and_keyboard(self):
        root = self.make_temp()
        browser = self.make_browser(root / "profile", root / "downloads")
        self.addCleanup(browser.quit)
        browser.get(self.url)
        input_element = browser.find_element(By.XPATH, "//input[@id='query']")
        input_element.send_keys("draft")
        input_element.send_keys(Keys.CONTROL, "a")
        input_element.send_keys("final")
        self.assertEqual(input_element.get_attribute("value"), "final")
        self.assertEqual(browser.find_element(By.ID, "input-events").text, "input")
        browser.execute_script("arguments[0].dataset.executed = 'yes';", input_element)
        self.assertEqual(input_element.get_attribute("data-executed"), "yes")
        Select(browser.find_element(By.ID, "choices")).select_by_visible_text("two")
        self.assertEqual([option.text for option in Select(browser.find_element(By.ID, "choices")).options], ["one", "two"])
        self.assertEqual(browser.find_element(By.ID, "select-events").text, "change")

    def test_nested_cross_origin_iframe_lookup(self):
        root = self.make_temp()
        browser = self.make_browser(root / "profile", root / "downloads")
        self.addCleanup(browser.quit)
        browser.get(self.url)
        WebDriverWait(browser, 8).until(lambda driver: len(driver.execute_cdp_cmd(
            "Page.getFrameTree", {})["frameTree"].get("childFrames", [{}])[0].get("childFrames", [])) == 1)
        element = browser.find_element(By.XPATH, "//button[@id='nested']", iframe=True)
        self.assertEqual(element.text, "Nested frame")
        element.click()
        browser.switch_to.default_content()
        self.assertEqual(browser.find_element(By.TAG_NAME, "title").get_attribute("textContent"), "Fixture")

    def test_upload_screenshot_and_async_script(self):
        root = self.make_temp()
        browser = self.make_browser(root / "中文 Profile", root / "downloads")
        self.addCleanup(browser.quit)
        browser.get(self.url)
        browser.execute_script("document.body.insertAdjacentHTML('beforeend', '<input id=upload type=file multiple>')")
        upload = root / "upload.txt"
        upload.write_text("upload verification", encoding="utf-8")
        element = browser.find_element(By.ID, "upload")
        element.send_keys(str(upload))
        content = browser.execute_async_script("""
            const done = arguments[arguments.length-1];
            arguments[0].files[0].text().then(done);
        """, element)
        self.assertEqual(content, "upload verification")
        self.assertTrue(browser.get_screenshot_as_png().startswith(b'\x89PNG\r\n\x1a\n'))
        result = browser.execute_script("return {nested: [document.getElementById('query')], value: 7}")
        self.assertEqual(result["nested"][0].get_attribute("id"), "query")
        self.assertEqual(result["value"], 7)

    def test_select_confirm_double_click_hover_and_timeout_recovery(self):
        root = self.make_temp()
        browser = self.make_browser(root / "profile", root / "downloads")
        self.addCleanup(browser.quit)
        browser.get(self.url)
        browser.execute_script("""
            choices.onchange=()=>document.body.dataset.answer=confirm('selected?')?'yes':'no';
            query.ondblclick=()=>document.body.dataset.double='yes';
            query.onmouseover=()=>document.body.dataset.hover='yes';
        """)
        Select(browser.find_element(By.ID, "choices")).select_by_index(1)
        self.assertEqual(browser.switch_to.alert.text, 'selected?')
        browser.switch_to.alert.dismiss()
        self.assertEqual(browser.execute_script('return document.body.dataset.answer'), 'no')
        field = browser.find_element(By.ID, 'query')
        ActionChains(browser).move_to_element(field).double_click(field).perform()
        self.assertEqual(browser.execute_script('return [document.body.dataset.double, document.body.dataset.hover]'), ['yes', 'yes'])
        browser.set_script_timeout(.25)
        with self.assertRaises(TimeoutException):
            browser.execute_async_script('/* callback intentionally never invoked */')
        self.assertEqual(browser.title, 'Fixture')

    def test_stale_invalid_selector_logs_and_two_browser_threads(self):
        root = self.make_temp()
        first = self.make_browser(root / "one", root / "downloads-one")
        second = self.make_browser(root / "two", root / "downloads-two")
        self.addCleanup(first.quit)
        self.addCleanup(second.quit)
        def task(browser, value):
            browser.get(self.url)
            browser.find_element(By.ID, 'query').send_keys(value)
            return browser.find_element(By.ID, 'query').get_attribute('value')
        with ThreadPoolExecutor(max_workers=2) as pool:
            a, b = pool.submit(task, first, 'one'), pool.submit(task, second, 'two')
            self.assertEqual((a.result(), b.result()), ('one', 'two'))
        stale = first.find_element(By.ID, 'query')
        first.execute_script("arguments[0].remove()", stale)
        with self.assertRaises(StaleElementReferenceException):
            stale.click()
        with self.assertRaises(InvalidSelectorException):
            first.find_element(By.XPATH, '//*[')
        first.execute_script("console.error('fixture-console-error')")
        self.assertTrue(any(e['level']=='SEVERE' and e['message']=='fixture-console-error' for e in first.get_log('browser')))
        self.assertEqual(first.get_log('browser'), [])

    def test_mobile_emulation(self):
        options = ChromeOptions()
        options.binary_location = str(CHROME)
        options.add_argument('--headless=new')
        options.add_experimental_option('mobileEmulation', {'deviceName':'iPhone X'})
        with PlaywrightChrome(options=options) as browser:
            browser.get(self.url)
            self.assertIn('iPhone', browser.execute_script('return navigator.userAgent'))
            self.assertGreater(browser.execute_script('return navigator.maxTouchPoints'), 0)

    def test_popup_dialog_cookie_download_and_profile_persistence(self):
        root = self.make_temp()
        profile = root / "profile"
        downloads = root / "downloads"
        downloads.mkdir()
        browser = self.make_browser(profile, downloads)
        self.addCleanup(browser.quit)
        browser.get(self.url)
        original = browser.current_window_handle
        browser.find_element(By.ID, "open").click()
        deadline = time.monotonic() + 5
        while len(browser.window_handles) < 2 and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertEqual(len(browser.window_handles), 2)
        browser.switch_to.window(browser.window_handles[-1])
        self.assertEqual(browser.title, "Popup")
        browser.close()
        browser.switch_to.window(original)
        browser.find_element(By.ID, "confirm").click()
        self.assertEqual(browser.switch_to.alert.text, "continue?")
        browser.switch_to.alert.accept()
        self.assertEqual(browser.execute_script("return document.body.dataset.confirm"), "yes")
        browser.add_cookie({"name": "fixture", "value": "kept", "path": "/"})
        self.assertEqual(next(c["value"] for c in browser.get_cookies() if c["name"] == "fixture"), "kept")
        browser.execute_script("localStorage.setItem('fixture', 'persisted')")
        browser.find_element(By.ID, "download").click()
        target = downloads / "fixture.txt"
        deadline = time.monotonic() + 8
        content = None
        while time.monotonic() < deadline:
            try:
                content = target.read_bytes()
            except OSError:
                content = None
            if content == b"playwright-download-content":
                break
            time.sleep(0.05)
        self.assertEqual(content, b"playwright-download-content", browser._runtime.download_errors)
        browser.quit()

        reopened = self.make_browser(profile, downloads)
        self.addCleanup(reopened.quit)
        reopened.get(self.url)
        self.assertEqual(reopened.execute_script("return localStorage.getItem('fixture')"), "persisted")
