"""Shared Playwright fingerprint consistency helpers.
The project still needs a small amount of browser instrumentation for the
designer and executor.  This module keeps that instrumentation consistent
across the Python executor and the AI prototype instead of letting each entry
point choose different language or CPU values.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path


def _locale(value: str | None) -> str:
    value = str(value or os.environ.get("EASYSPIDER_LOCALE", "zh-CN")).strip()
    return value or "zh-CN"


def locale_languages(locale: str | None = None) -> list[str]:
    """Return the normal Chromium language list for a locale."""
    value = _locale(locale)
    base = value.split("-", 1)[0]
    return [value, base] if base and base != value else [value]


def hardware_concurrency(value: int | str | None = None) -> int:
    """Use the host's logical CPU count unless explicitly configured.

    Chromium reports the host count in this environment.  Keeping the same
    value in the main page, iframe and Worker avoids the inconsistency created
    by the upstream stealth script's fixed value of four.
    """
    raw = value if value is not None else os.environ.get("EASYSPIDER_HARDWARE_CONCURRENCY")
    try:
        count = int(raw) if raw is not None else (os.cpu_count() or 4)
    except (TypeError, ValueError):
        count = os.cpu_count() or 4
    return max(1, min(count, 256))


def _stealth_candidates() -> list[Path]:
    configured = os.environ.get("EASYSPIDER_STEALTH_SCRIPT", "").strip()
    here = Path(__file__).resolve().parent
    candidates = [Path(configured)] if configured else []
    candidates.extend(
        [
            here / "stealth.min.js",
            here.parent / "ElectronJS" / "stealth.min.js",
            here.parent / "stealth.min.js",
            Path.cwd() / "stealth.min.js",
        ]
    )
    result: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        try:
            candidate = candidate.expanduser().resolve()
        except OSError:
            continue
        if candidate not in seen:
            seen.add(candidate)
            result.append(candidate)
    return result


def stealth_source(locale: str | None = None, cpu_count: int | str | None = None) -> str:
    """Load the bundled stealth source with values matching this browser.

    The bundled script is retained for the existing evasions.  Its generated
    defaults (`['en-US', 'en']` and `4`) are replaced with the values Chrome
    exposes to Workers in the current profile.  If the optional file is not
    present, the safe baseline still hides ``navigator.webdriver``.
    """
    source = ""
    for candidate in _stealth_candidates():
        if candidate.is_file():
            source = candidate.read_text(encoding="utf-8")
            break

    languages = json.dumps(locale_languages(locale), separators=(",", ":"))
    cpu = str(hardware_concurrency(cpu_count))
    if source:
        source, language_replacements = re.subn(
            r"opts:\{languages:\[\]\}",
            f"opts:{{languages:{languages}}}",
            source,
            count=1,
        )
        source, cpu_replacements = re.subn(
            r"opts:\{hardwareConcurrency:4\}",
            f"opts:{{hardwareConcurrency:{cpu}}}",
            source,
            count=1,
        )
        # Keep this fallback useful if a future generated stealth file changes
        # its argument spelling.
        if language_replacements == 0:
            source += f"\nObject.defineProperty(Object.getPrototypeOf(navigator), 'languages', {{get: () => Object.freeze({languages})}});"
        if cpu_replacements == 0:
            source += f"\nObject.defineProperty(Object.getPrototypeOf(navigator), 'hardwareConcurrency', {{get: () => {cpu}}});"

    # The bundled stealth script removes the prototype getter.  Only patch the
    # prototype as a fallback; defining an own property on `navigator` is an
    # observable difference that modern detectors report as tampering.
    source += "\ntry { if (navigator.webdriver !== undefined) Object.defineProperty(Object.getPrototypeOf(navigator), 'webdriver', {get: () => undefined}); } catch (_) {}"
    return source


def context_settings(options) -> dict:
    """Build stable context settings from compatibility options and env vars."""
    experimental = getattr(options, "experimental_options", {}) or {}
    locale = _locale(experimental.get("locale"))
    timezone = str(
        experimental.get("timezoneId")
        or os.environ.get("EASYSPIDER_TIMEZONE", "Asia/Shanghai")
    ).strip() or "Asia/Shanghai"
    return {
        "locale": locale,
        "timezone_id": timezone,
        "init_script": stealth_source(locale, experimental.get("hardwareConcurrency")),
    }
