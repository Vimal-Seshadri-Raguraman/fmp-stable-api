import json
import os
from typing import Dict, Optional, Tuple

KEYS_FILE = os.path.join(os.path.expanduser("~/.fmp"), "keys.json")

_VALID_CLIENT_TYPES = ("Basic", "Starter", "Premium", "Ultimate", "Enterprise", "Custom")


def _load() -> Dict:
    try:
        with open(KEYS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"keys": {}, "default": None}


def _save(data: Dict) -> None:
    os.makedirs(os.path.dirname(KEYS_FILE), exist_ok=True)
    with open(KEYS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


class KeyManager:
    """
    Manages named API key references.

    Keys are never stored directly — only the environment variable name that
    holds the key is recorded. The actual value is always read from the
    environment at runtime.

    ~/.fmp/keys.json stores:
        {
          "keys": {
            "alias": {
              "env_var": "FMP_KEY_ALIAS",
              "client_type": "Premium",
              "rate_limit": 500        # optional override; null means use client_type default
            }
          },
          "default": "alias"
        }

    Usage:
        km = KeyManager()
        km.add("work", env_var="FMP_KEY_WORK", client_type="Premium", rate_limit=500)
        km.set_default("work")

        client = FMP.from_key("work")   # resolves env var, applies stored rate limit
    """

    def add(
        self,
        alias: str,
        env_var: str,
        client_type: str = "Premium",
        rate_limit: Optional[int] = None,
        set_default: bool = False,
    ) -> None:
        """
        Register a named key.

        - env_var: name of the environment variable that holds the actual API key
        - client_type: your FMP subscription tier
        - rate_limit: requests/minute override. If None, uses the client_type default.
                      Required when client_type is 'Enterprise' or 'Custom'.
        """
        if client_type not in _VALID_CLIENT_TYPES:
            raise ValueError(f"Invalid client_type '{client_type}'. Choose from: {_VALID_CLIENT_TYPES}")
        if client_type in ("Enterprise", "Custom") and rate_limit is None:
            raise ValueError(f"client_type '{client_type}' requires an explicit rate_limit.")
        if rate_limit is not None and rate_limit <= 0:
            raise ValueError("rate_limit must be a positive integer.")
        data = _load()
        data["keys"][alias] = {
            "env_var": env_var,
            "client_type": client_type,
            "rate_limit": rate_limit,
        }
        if set_default or data["default"] is None:
            data["default"] = alias
        _save(data)

    def remove(self, alias: str) -> None:
        """Remove a named key entry."""
        data = _load()
        if alias not in data["keys"]:
            raise KeyError(f"No key registered under alias '{alias}'")
        del data["keys"][alias]
        if data["default"] == alias:
            remaining = list(data["keys"])
            data["default"] = remaining[0] if remaining else None
        _save(data)

    def set_default(self, alias: str) -> None:
        """Set the default alias used when no alias is passed to FMP.from_key()."""
        data = _load()
        if alias not in data["keys"]:
            raise KeyError(f"No key registered under alias '{alias}'")
        data["default"] = alias
        _save(data)

    def resolve(self, alias: Optional[str] = None) -> Tuple[str, str, Optional[int]]:
        """
        Return (api_key_value, client_type, rate_limit) for the given alias (or the default).

        rate_limit is None when no override is stored (FMP will use the client_type default).
        Raises KeyError if alias not found, ValueError if env var is not set.
        """
        data = _load()
        target = alias or data.get("default")
        if not target:
            raise KeyError("No default key set. Call KeyManager().add(..., set_default=True) first.")
        if target not in data["keys"]:
            raise KeyError(f"No key registered under alias '{target}'")
        entry = data["keys"][target]
        env_var = entry["env_var"]
        value = os.environ.get(env_var)
        if not value:
            raise ValueError(
                f"Environment variable '{env_var}' is not set. "
                f"Add it to your .env file and source it (or export it)."
            )
        return value, entry["client_type"], entry.get("rate_limit")

    def list_keys(self) -> Dict:
        """Return all registered aliases with their metadata."""
        data = _load()
        result = {}
        for alias, entry in data["keys"].items():
            result[alias] = {
                "env_var": entry["env_var"],
                "client_type": entry["client_type"],
                "rate_limit": entry.get("rate_limit"),
                "is_default": alias == data.get("default"),
                "is_set": bool(os.environ.get(entry["env_var"])),
            }
        return result

    def get_default(self) -> Optional[str]:
        """Return the current default alias, or None."""
        return _load().get("default")
