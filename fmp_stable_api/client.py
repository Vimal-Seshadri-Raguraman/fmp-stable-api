# current/publish/fmp/client.py
import os
import time
from typing import Callable, Dict, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .rate_limiter import RateLimiter
from .endpoints import (
    load_config,
    get_base_url,
    build_endpoint_func,
    list_categories,
    list_endpoints,
    safe_param_name,
)

API_KEY_TYPES = {
    "Basic": 250,
    "Starter": 300,
    "Premium": 750,
    "Ultimate": 3000,
    "Enterprise": None,
    "Custom": None,
}

CLIENT_TYPE_TO_TIER = {
    "Basic": "FREE",
    "Starter": "STARTER",
    "Premium": "PREMIUM",
    "Ultimate": "ULTIMATE",
    "Enterprise": "ULTIMATE",
    "Custom": "ULTIMATE",
}


class CategoryProxy:
    """
    Lazy proxy for a single endpoint category.

    Attribute access resolves endpoint function names on demand:
        client.Search.search_symbol(symbol="AAPL")
    """

    def __init__(self, category_name: str, endpoints: Dict, make_request: Callable, tier: str = "FREE"):
        object.__setattr__(self, "_category_name", category_name)
        object.__setattr__(self, "_endpoints", endpoints)
        object.__setattr__(self, "_make_request", make_request)
        object.__setattr__(self, "_tier", tier)
        object.__setattr__(self, "_cache", {})

    def __getattr__(self, name: str) -> Callable:
        cache = object.__getattribute__(self, "_cache")
        if name in cache:
            return cache[name]

        endpoints = object.__getattribute__(self, "_endpoints")
        make_request = object.__getattribute__(self, "_make_request")
        tier = object.__getattribute__(self, "_tier")

        # Match by snake_case function name
        for endpoint_key, config in endpoints.items():
            func_name = endpoint_key.replace("-", "_").replace(" ", "_").lower()
            if func_name and func_name[0].isdigit():
                func_name = f"_{func_name}"
            if func_name == name:
                fn = build_endpoint_func(
                    path=config.get("path", endpoint_key),
                    required_params=config.get("required_params", []),
                    optional_params=config.get("optional_params", []),
                    make_request=make_request,
                    access=config.get("access", {}),
                    tier=tier,
                )
                fn.__name__ = name
                cache[name] = fn
                return fn

        category = object.__getattribute__(self, "_category_name")
        raise AttributeError(f"No endpoint '{name}' in category '{category}'")

    def help(self) -> None:
        category = object.__getattribute__(self, "_category_name")
        endpoints = object.__getattribute__(self, "_endpoints")
        tier = object.__getattribute__(self, "_tier")
        print(f"\n{'='*60}")
        print(f"Category: {category}  (your tier: {tier})")
        print(f"{'='*60}")
        for endpoint_key, config in endpoints.items():
            func_name = endpoint_key.replace("-", "_").replace(" ", "_").lower()
            desc = config.get("description", "")
            req = [safe_param_name(p) for p in config.get("required_params", [])]
            opt = [safe_param_name(p) for p in config.get("optional_params", [])]
            access = config.get("access", {})
            tier_access = access.get(tier, "FULL") if access else "FULL"
            badge = "" if tier_access == "FULL" else f"  [{tier_access}]"
            print(f"\n  {func_name}{badge}")
            if desc:
                print(f"    {desc}")
            if req:
                print(f"    Required: {', '.join(req)}")
            if opt:
                print(f"    Optional: {', '.join(opt)}")
        print(f"\n{'='*60}\n")


class FMP:
    """Financial Modeling Prep API client."""

    @classmethod
    def _to_attr_name(cls, category_key: str) -> str:
        """Convert a category key to its PascalCase attribute name."""
        return "".join(w.title() for w in category_key.replace("-", " ").split())

    @classmethod
    def from_key(cls, alias: Optional[str] = None, client_type: str = "Premium") -> "FMP":
        """
        Create an FMP client from a KeyManager alias or directly from an env var name.

        If alias is registered in KeyManager, uses the stored client_type and rate_limit.
        If alias is not registered but exists as an environment variable, reads the key
        from that env var directly (client_type param applies in this case).

        Usage:
            # KeyManager alias (recommended — stores client_type and rate_limit)
            client = FMP.from_key('work')
            client = FMP.from_key()           # uses default alias

            # Env var name directly (no prior registration needed)
            client = FMP.from_key('FMP_KEY_1')
            client = FMP.from_key('FMP_KEY_1', client_type='Basic')
        """
        import os
        from .key_manager import KeyManager
        try:
            key_value, resolved_type, rate_limit = KeyManager().resolve(alias)
            return cls(client_type=resolved_type, client_key=key_value, custom_daily_limit=rate_limit)
        except KeyError:
            # Not a registered alias — try treating it as an env var name directly
            if alias and os.environ.get(alias):
                return cls(client_type=client_type, client_key=os.environ[alias])
            raise

    def __init__(
        self,
        client_type: str,
        client_key: Optional[str] = None,
        custom_daily_limit: Optional[int] = None,
    ):
        if client_key is None:
            client_key = os.environ.get("FMP_API_KEY")
        if not client_key:
            raise ValueError(
                "No API key provided. Pass client_key= or set the FMP_API_KEY environment variable."
            )
        if client_type not in API_KEY_TYPES:
            raise ValueError(
                f"Invalid client_type '{client_type}'. "
                f"Must be one of: {list(API_KEY_TYPES.keys())}"
            )

        if custom_daily_limit is not None:
            minute_limit = custom_daily_limit
        elif client_type in ("Enterprise", "Custom"):
            raise ValueError(
                f"{client_type} client_type requires custom_daily_limit parameter"
            )
        else:
            minute_limit = API_KEY_TYPES[client_type]

        self._api_key = client_key
        self._client_type = client_type
        self._tier = CLIENT_TYPE_TO_TIER.get(client_type, "FREE")
        self._minute_limit = minute_limit
        self._rate_limiter = RateLimiter(minute_limit)

        # Load config and derive base URL; auto-refresh if cache is stale (>24h)
        self._config = load_config()
        self._base_url = get_base_url(self._config)
        try:
            from .updater import update_endpoints
            if update_endpoints():
                self._config = load_config()
                self._base_url = get_base_url(self._config)
        except Exception:
            pass

        # HTTP session with retry
        self._session = self._build_session()

    @property
    def _category_map(self):
        if not hasattr(self, '_category_map_cache'):
            config = load_config()
            object.__setattr__(self, '_category_map_cache',
                {self.__class__._to_attr_name(k): k for k in list_categories(config)})
        return self._category_map_cache

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        retry = Retry(
            total=2,
            backoff_factor=2,
            status_forcelist=[500, 502, 503, 504],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        session.headers.update({
            "User-Agent": "fmp-python-client/1.0",
            "Accept": "application/json",
        })
        return session

    def __getattr__(self, name: str) -> "CategoryProxy":
        # Avoid infinite recursion for private/dunder attrs
        if name.startswith("_"):
            raise AttributeError(name)

        category_map = self._category_map

        if name not in category_map:
            raise AttributeError(
                f"'{name}' is not a valid category. "
                f"Available: {list(category_map.keys())}"
            )

        config = load_config()
        category_key = category_map[name]
        endpoints_dict = list_endpoints(config, category_key)
        proxy = CategoryProxy(name, endpoints_dict, self._make_request, self._tier)
        self.__dict__[name] = proxy
        return proxy

    def _make_request(self, path: str, params: Optional[Dict] = None) -> Dict:
        url = f"{self._base_url}/{path.lstrip('/')}"
        return self.request(url, params)

    def request(self, url: str, params: Optional[Dict] = None) -> Dict:
        """Make a GET request to any FMP URL."""
        self._rate_limiter.acquire()

        if params is None:
            params = {}
        params["apikey"] = self._api_key

        response = self._session.get(url, params=params, timeout=30)

        if response.status_code == 429:
            time.sleep(60)
            raise Exception("Rate limit exceeded by API. Retry after 60s.")
        if response.status_code == 401:
            raise Exception("Invalid API key.")
        if response.status_code != 200:
            raise Exception(f"API error {response.status_code}: {response.text}")

        content_type = response.headers.get("content-type", "").lower()
        if "csv" in content_type:
            return {"csv_data": response.text, "content_type": "csv"}
        return response.json()

    def download(
        self,
        url: str,
        params: Optional[Dict] = None,
        filename: Optional[str] = None,
    ) -> str:
        """Download a URL to a file; returns the saved filename."""
        self._rate_limiter.acquire()

        if params is None:
            params = {}
        params["apikey"] = self._api_key

        response = self._session.get(url, params=params, timeout=30)

        if response.status_code == 401:
            raise Exception("Invalid API key.")
        if response.status_code != 200:
            raise Exception(f"API error {response.status_code}: {response.text}")

        if filename is None:
            from urllib.parse import urlparse
            path = urlparse(url).path
            base = path.split("/")[-1] or "download"
            content_type = response.headers.get("content-type", "").lower()
            if not any(base.endswith(ext) for ext in (".csv", ".json", ".txt")):
                base += ".csv" if "csv" in content_type else ".json"
            filename = base

        with open(filename, "wb") as f:
            f.write(response.content)
        return filename

    def get_usage_info(self) -> Dict:
        return {
            "client_type": self._client_type,
            "minute_limit": self._minute_limit,
            "remaining": self._rate_limiter.get_remaining(),
            "seconds_until_reset": self._rate_limiter.seconds_until_reset(),
        }

    def update_endpoints(self, force: bool = False) -> bool:
        """Manually trigger an endpoint + skill.md refresh from GitHub."""
        from .updater import update_endpoints as _update
        updated = _update(force=force)
        if updated:
            self._config = load_config()
            self._base_url = get_base_url(self._config)
            # Clear the cached category map so it rebuilds on next access
            if hasattr(self, '_category_map_cache'):
                del self.__dict__['_category_map_cache']
            # Clear any cached CategoryProxy instances
            to_remove = [k for k in self.__dict__ if not k.startswith('_')]
            for k in to_remove:
                del self.__dict__[k]
        return updated

    def help(self) -> None:
        config = load_config()
        print(f"\n{'='*70}")
        print("FMP API Client — Available Categories")
        print(f"{'='*70}")
        for attr_name, category_key in self._category_map.items():
            endpoints = list_endpoints(config, category_key)
            print(f"  {attr_name} ({len(endpoints)} endpoints)")
        print(f"\n{'='*70}")
        print("Usage:")
        print("  client.CategoryName.help()             list endpoints in category")
        print("  client.CategoryName.endpoint_name(...) call an endpoint")
        print("  client.request(url, params)            raw URL request")
        print("  client.update_endpoints(force=True)    force refresh from GitHub")
        print(f"{'='*70}\n")
