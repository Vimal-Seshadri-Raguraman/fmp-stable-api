# current/publish/fmp/endpoints.py
import json
import keyword
import os
import warnings
from typing import Callable, Dict, List, Optional


_BUNDLED = os.path.join(os.path.dirname(__file__), "fmp_endpoints.json")

TIERS = ["FREE", "STARTER", "PREMIUM", "ULTIMATE"]
ACCESS_LEVELS = ["FULL", "LIMITED", "NO_ACCESS"]
DEFAULT_ACCESS = {tier: "FULL" for tier in TIERS}


def load_config() -> Dict:
    """Load endpoints config via updater if available, else read bundled file."""
    try:
        from .updater import load_endpoints
        return load_endpoints()
    except ImportError:
        pass
    with open(_BUNDLED, "r", encoding="utf-8") as f:
        return json.load(f)


def get_base_url(config: Dict) -> str:
    return config.get("stable_url", "https://financialmodelingprep.com/stable")


def safe_param_name(name: str) -> str:
    """Return a Python-safe version of an API parameter name."""
    return f"{name}_" if keyword.iskeyword(name) else name


def restore_param_names(kwargs: Dict) -> Dict:
    """Convert safe parameter names back to their original API names."""
    result = {}
    for key, value in kwargs.items():
        if key.endswith("_") and keyword.iskeyword(key[:-1]):
            result[key[:-1]] = value
        else:
            result[key] = value
    return result


def build_endpoint_func(
    path: str,
    required_params: List[str],
    optional_params: List[str],
    make_request: Callable,
    access: Optional[Dict] = None,
    tier: Optional[str] = None,
) -> Callable:
    """
    Return a callable that validates required params and calls make_request.

    The returned function accepts keyword arguments using safe param names
    (e.g. `from_` instead of `from`).
    """
    safe_required = [safe_param_name(p) for p in required_params]
    safe_optional = [safe_param_name(p) for p in optional_params]
    all_safe = set(safe_required + safe_optional)

    def endpoint_func(**kwargs):
        if tier and access:
            tier_access = access.get(tier, "FULL")
            if tier_access == "NO_ACCESS":
                raise PermissionError(
                    f"This endpoint is not available on the {tier} tier. "
                    "Upgrade your plan to access it."
                )
            if tier_access == "LIMITED":
                warnings.warn(
                    f"This endpoint has LIMITED access on the {tier} tier. "
                    "The response may be restricted.",
                    stacklevel=2,
                )

        # Validate required params
        for param in safe_required:
            if param not in kwargs:
                original = param[:-1] if param.endswith("_") else param
                raise ValueError(f"Required parameter '{original}' not provided")

        # Filter to known params only, then restore original names
        filtered = {k: v for k, v in kwargs.items() if k in all_safe}
        api_params = restore_param_names(filtered)
        return make_request(path, api_params)

    # Build a helpful docstring
    lines = [f"Endpoint: {path}"]
    if required_params:
        safe_names = [safe_param_name(p) for p in required_params]
        lines.append(f"Required: {', '.join(safe_names)}")
    if optional_params:
        safe_names = [safe_param_name(p) for p in optional_params]
        lines.append(f"Optional: {', '.join(safe_names)}")
    endpoint_func.__doc__ = "\n".join(lines)

    return endpoint_func


def list_categories(config: Dict) -> List[str]:
    return list(config.get("endpoints", {}).keys())


def list_endpoints(config: Dict, category: str) -> Dict:
    """Return {endpoint_name: config_dict} for a given category."""
    return config.get("endpoints", {}).get(category, {})
