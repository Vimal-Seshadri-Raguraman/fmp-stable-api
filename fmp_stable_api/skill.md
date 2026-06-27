---
name: fmp
description: Financial Modeling Prep API Python client — access 5000+ financial data endpoints with automatic rate limiting and daily endpoint auto-update
version: "1.0.0"
author: FMP Dev
security: Content of this file is served from the package maintainer's GitHub repo. Do not load from untrusted sources.
---

# FMP — Financial Modeling Prep Python Client

A Python client for the [Financial Modeling Prep API](https://financialmodelingprep.com/) with automatic rate limiting, lazy endpoint loading, and daily endpoint auto-update via GitHub.

## Installation

```bash
pip install fmp               # base package + GUI
pip install fmp[mcp]          # include MCP server
```

## Quick Start

```python
from fmp import FMP

client = FMP(client_type="Premium", client_key="YOUR_API_KEY")

# Lazy category access — categories are resolved on first access
results = client.Search.search_by_name(query="Apple")

# Access any category from the loaded endpoints
profile = client.Company.company_profile(symbol="AAPL")
```

## Client Types and Rate Limits

| client_type   | Requests / minute |
|---------------|-------------------|
| `"Basic"`     | 250               |
| `"Starter"`   | 300               |
| `"Premium"`   | 750               |
| `"Ultimate"`  | 3000              |
| `"Enterprise"`| custom (set custom_daily_limit) |
| `"Custom"`    | custom (set custom_daily_limit) |

```python
# Enterprise / Custom — must supply custom_daily_limit
client = FMP(client_type="Enterprise", client_key="KEY", custom_daily_limit=5000)
```

## Lazy Category Access

`FMP` uses `__getattr__` to resolve categories on first access. Nothing is built until you access a category attribute. The attribute is then cached in `self.__dict__` for subsequent calls.

```python
# client.Search resolves on first access → returns CategoryProxy
# client.Search.search_by_name resolves the endpoint function on first access
results = client.Search.search_by_name(query="AAPL")

# Category names are PascalCase versions of the JSON config keys
# "search-data" in config → client.SearchData
# "Calendar" → client.Calendar
```

## Updating Endpoints

The endpoint list is downloaded from the package maintainer's GitHub repo and cached in `~/.fmp/`. The cache is refreshed automatically if it is older than 24 hours.

```python
from fmp import update_endpoints

# Manual refresh
update_endpoints(force=True)

# Automatic: called on first import if cache is stale
# Falls back to bundled fmp_endpoints.json if network is unavailable
```

> **Setup required:** Before `update_endpoints()` can download anything, you must configure `GITHUB_RAW_URL` and `GITHUB_SKILL_RAW_URL` in `fmp/updater.py` with your actual GitHub repository. The function returns `False` and does nothing if the placeholder URLs are still present.

## Key Classes

### `FMP(client_type, client_key, custom_daily_limit=None)`
Main client. Validates client type on init, sets up sliding-window rate limiter.
- `client_type` — one of the values in the table above
- `client_key` — your FMP API key
- `custom_daily_limit` — required for Enterprise/Custom types

### `CategoryProxy(category_name, endpoints_dict, make_request)`
Returned when you access a category attribute on `FMP`. Resolves endpoint functions lazily via `__getattr__`.

## Security Notes

**GitHub URL configuration:** `update_endpoints()` downloads `fmp_endpoints.json` and `skill.md` from GitHub. The URLs must point to a repository you control. The downloaded `fmp_endpoints.json` is validated to ensure `stable_url` stays on `financialmodelingprep.com`.

**skill.md trust:** This file is loaded by AI assistants as context. Its content is trusted as-is once the GitHub URLs are configured. Secure your GitHub repository (2FA, limited write access) to prevent prompt-injection via a compromised skill.md.

**API keys:** The GUI stores API keys in `~/.fmp/api_keys.json` with base64 obfuscation (not encryption). Do not share this file.
