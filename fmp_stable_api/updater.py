# current/publish/fmp/updater.py
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Dict

import requests

GITHUB_RAW_URL = "https://raw.githubusercontent.com/Vimal-Seshadri-Raguraman/fmp-stable-api/main/fmp_stable_api/fmp_endpoints.json"
GITHUB_SKILL_RAW_URL = "https://raw.githubusercontent.com/Vimal-Seshadri-Raguraman/fmp-stable-api/main/fmp_stable_api/skill.md"

CACHE_DIR = os.path.expanduser("~/.fmp")
ENDPOINTS_CACHE = os.path.join(CACHE_DIR, "fmp_endpoints.json")
SKILL_CACHE = os.path.join(CACHE_DIR, "skill.md")
META_FILE = os.path.join(CACHE_DIR, ".meta.json")

BUNDLED_ENDPOINTS = os.path.join(os.path.dirname(__file__), "fmp_endpoints.json")
BUNDLED_SKILL = os.path.join(os.path.dirname(__file__), "skill.md")

STALE_AFTER_HOURS = 24

_PLACEHOLDER_TOKENS = ("YOUR_USERNAME", "YOUR_REPO")

_ALLOWED_BASE_URL_PREFIX = "https://financialmodelingprep.com/"


def _urls_are_configured() -> bool:
    """Return False if the GitHub URLs still contain placeholder tokens."""
    return not any(
        token in GITHUB_RAW_URL or token in GITHUB_SKILL_RAW_URL
        for token in _PLACEHOLDER_TOKENS
    )


def _validate_endpoints_json(data: Dict) -> None:
    """Raise ValueError if downloaded endpoints JSON looks malformed or unsafe."""
    if not isinstance(data, dict):
        raise ValueError("Endpoints JSON must be a dict")
    stable_url = data.get("stable_url", "")
    if stable_url and not stable_url.startswith(_ALLOWED_BASE_URL_PREFIX):
        raise ValueError(
            f"Remote stable_url '{stable_url}' is not on the allowed domain "
            f"({_ALLOWED_BASE_URL_PREFIX}). Refusing to cache."
        )


def _ensure_cache_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)


def _read_meta() -> Dict:
    try:
        with open(META_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def _write_meta(meta: Dict):
    _ensure_cache_dir()
    with open(META_FILE, "w") as f:
        json.dump(meta, f)


def _is_stale(meta: Dict) -> bool:
    raw = meta.get("last_checked")
    if not raw:
        return True
    try:
        checked_at = datetime.fromisoformat(raw)
        if checked_at.tzinfo is None:
            checked_at = checked_at.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - checked_at > timedelta(hours=STALE_AFTER_HOURS)
    except Exception:
        return True


def load_endpoints() -> Dict:
    """Return best available endpoints config: cache > bundled fallback."""
    if os.path.exists(ENDPOINTS_CACHE):
        try:
            with open(ENDPOINTS_CACHE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    with open(BUNDLED_ENDPOINTS, "r", encoding="utf-8") as f:
        return json.load(f)


def get_skill_md_path() -> str:
    """Return path to best available skill.md: cache > bundled fallback."""
    return SKILL_CACHE if os.path.exists(SKILL_CACHE) else BUNDLED_SKILL


def update_endpoints(force: bool = False) -> bool:
    """
    Check GitHub for updated endpoints and skill.md; download if stale.

    Returns True if any file was updated, False if skipped or on error.

    SECURITY NOTE: Requires GITHUB_RAW_URL / GITHUB_SKILL_RAW_URL to be
    configured with a real, owned GitHub repository (not the placeholder).
    The downloaded endpoints JSON must have stable_url on financialmodelingprep.com.
    The skill.md content is trusted as-is once the repo URLs are configured —
    secure your GitHub repository access accordingly.
    """
    if not _urls_are_configured():
        return False

    meta = _read_meta()
    if not force and not _is_stale(meta):
        return False

    now_iso = datetime.now(timezone.utc).isoformat()
    updated = False

    # --- fmp_endpoints.json ---
    try:
        resp = requests.get(GITHUB_RAW_URL, timeout=10)
        resp.raise_for_status()
        remote = resp.json()
        _validate_endpoints_json(remote)
        remote_ts = remote.get("last_updated", "")
        cached_ts = meta.get("endpoints_last_updated", "")
        if remote_ts != cached_ts:
            _ensure_cache_dir()
            with open(ENDPOINTS_CACHE, "w", encoding="utf-8") as f:
                json.dump(remote, f, indent=2, ensure_ascii=False)
            meta["endpoints_last_updated"] = remote_ts
            updated = True
    except (requests.RequestException, ValueError, json.JSONDecodeError):
        pass

    # --- skill.md ---
    try:
        resp = requests.get(GITHUB_SKILL_RAW_URL, timeout=10)
        resp.raise_for_status()
        content = resp.text
        if len(content) != meta.get("skill_md_len", -1):
            _ensure_cache_dir()
            with open(SKILL_CACHE, "w", encoding="utf-8") as f:
                f.write(content)
            meta["skill_md_len"] = len(content)
            updated = True
    except (requests.RequestException, OSError):
        pass

    meta["last_checked"] = now_iso
    _write_meta(meta)
    return updated
