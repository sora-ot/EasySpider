"""Verify the Chrome through Playwright bundled in a Windows EasySpider package."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ExecuteStage"))
from playwright_driver import webdriver, By


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--stage",
        type=Path,
        default=Path(".temp_to_pub/EasySpider_windows_x64"),
        help="root of the staged Windows package",
    )
    parser.add_argument("--url", default="https://example.com/")
    args = parser.parse_args()

    app = args.stage.resolve() / "EasySpider" / "resources" / "app"
    chrome_binary = app / "chrome_win64" / "chrome.exe"
    if not chrome_binary.is_file():
        raise FileNotFoundError(f"bundled browser files are missing below {app}")

    options = webdriver.ChromeOptions()
    options.binary_location = str(chrome_binary)
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--ignore-certificate-errors")

    driver = webdriver.Chrome(options=options)
    try:
        driver.set_page_load_timeout(30)
        driver.get(args.url)
        heading = driver.find_element(By.TAG_NAME, "h1").text.strip()
        assert driver.title == "Example Domain", driver.title
        assert heading == "Example Domain", heading
        print(
            json.dumps(
                {
                    "url": driver.current_url,
                    "title": driver.title,
                    "heading": heading,
                    "browser_version": driver.execute_cdp_cmd("Browser.getVersion", {})["product"],
                    "platform": sys.platform,
                    "chrome_binary": str(chrome_binary),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
