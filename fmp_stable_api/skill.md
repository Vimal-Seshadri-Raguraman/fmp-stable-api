---
name: fmp
description: Financial Modeling Prep API Python client — 263 stable endpoints across 28 categories, automatic rate limiting, key management, and daily endpoint auto-update
version: "2.1.1"
author: FMP Dev
security: Content of this file is served from the package maintainer's GitHub repo. Do not load from untrusted sources.
---

# FMP — Financial Modeling Prep Python Client

A Python client for the [Financial Modeling Prep API](https://financialmodelingprep.com/) (stable API, base URL `https://financialmodelingprep.com/stable/`) with automatic rate limiting, lazy endpoint loading, named key management, an optional MCP server, and daily endpoint auto-update via GitHub.

## Installation

```bash
pip install fmp-stable-api          # client + GUI manager
pip install fmp-stable-api[mcp]     # also installs the MCP server
```

The import name is `fmp_stable_api`.

## Quick Start

```python
from fmp_stable_api import FMP

client = FMP(client_type="Ultimate", client_key="YOUR_API_KEY")

# Categories and endpoints are resolved lazily from fmp_endpoints.json
results = client.Search.search_name(query="Apple")
profile = client.Company.profile(symbol="AAPL")
prices  = client.Chart.light(symbol="AAPL", from_="2025-01-01", to="2025-03-31")

# Discover what is available
client.help()            # lists every category
client.Analyst.help()    # lists endpoints in a category with their parameters
```

If `client_key` is omitted, the client reads the `FMP_API_KEY` environment variable.

## Calling Endpoints

- Every endpoint is a keyword-only function: `client.<Category>.<endpoint>(**params)`.
- Parameter names match the FMP query parameters. Names that collide with Python keywords get a trailing underscore: pass `from_` for `from`. Everything else (`to`, `symbol`, `limit`, `period`, `page`) is unchanged.
- Missing required parameters raise `ValueError`. Unknown parameters are silently dropped.
- Each endpoint's docstring lists its path and required/optional parameters.

```python
client.Financials.income_statement(symbol="AAPL", period="annual", limit=5)
client.News.news_stock(symbols="AAPL,MSFT", from_="2025-06-01", to="2025-06-30")
client.Technical_Indicators.relative_strength_index(symbol="AAPL", periodLength=14, timeframe="1day")
```

Raw requests and file downloads are also available:

```python
client.request("https://financialmodelingprep.com/stable/profile", {"symbol": "AAPL"})
client.download("https://financialmodelingprep.com/stable/profile-bulk", params={"part": 0}, filename="profiles.csv")
```

## Categories

Category attribute names are the endpoint-config keys with each word title-cased. Keys containing underscores keep them, so `Sec_Filings` and `Form_13F` are accessed exactly as written.

| Category | Endpoints | Covers |
|---|---|---|
| `Search` | 7 | symbol, name, CIK, CUSIP, ISIN search; stock screener; exchange variants |
| `Directory` | 11 | symbol lists, CIK list, symbol changes, ETF list, available exchanges/sectors/industries/countries |
| `Calendar` | 9 | dividends, earnings, IPOs, stock splits (per symbol and calendar views) |
| `Chart` | 10 | end-of-day light/full/unadjusted/dividend-adjusted; intraday 1min to 4hour |
| `Company` | 17 | profile, notes, peers, delisted, employees, market cap, shares float, M&A, executives and compensation |
| `Economics` | 4 | treasury rates, economic indicators, economic calendar, market risk premium |
| `Funds` | 9 | ETF holdings/info/weightings/exposure; mutual fund disclosures |
| `Commodities` | 9 | commodities list, quotes, batch quotes, EOD and intraday charts |
| `Earnings_Transcripts` | 4 | latest transcripts, transcript by symbol/year/quarter, transcript dates |
| `Financials` | 27 | income/balance/cash-flow statements (annual, quarter, TTM, growth, as-reported), key metrics, ratios, scores, owner earnings, enterprise values, segmentation, 10-K reports |
| `Indexes` | 15 | index list, quotes, S&P 500 / Nasdaq / Dow constituents and history, index charts |
| `Bulk` | 18 | bulk CSV downloads: profiles, ratings, DCF, scores, statements, EOD prices |
| `Technical_Indicators` | 9 | SMA, EMA, WMA, DEMA, TEMA, RSI, standard deviation, Williams %R, ADX |
| `Market_Hours` | 3 | exchange hours, holidays, all-exchange hours |
| `Quote` | 16 | single/batch quotes, short quotes, price change, aftermarket quotes/trades, full-exchange and asset-class batch quotes |
| `News` | 10 | FMP articles; latest and searchable stock, crypto, forex, general news and press releases |
| `Form_13F` | 8 | institutional ownership filings, extracts, holder analytics and summaries |
| `Analyst` | 8 | analyst estimates, ratings snapshot/history, price targets, grades |
| `Market_Performance` | 11 | sector and industry performance and PE (snapshot and historical), gainers, losers, most active |
| `Sec_Filings` | 12 | latest 8-K and financial filings, filing search by symbol/CIK/form type, company search, SEC profile, SIC classification |
| `Insider_Trades` | 6 | latest and searchable insider trades, statistics, transaction types, beneficial ownership |
| `Discounted_Cash_Flow` | 4 | DCF, levered DCF, custom DCF with adjustable assumptions |
| `Forex` | 9 | currency pairs list, quotes, batch quotes, EOD and intraday charts |
| `Crypto` | 9 | cryptocurrency list, quotes, batch quotes, EOD and intraday charts |
| `Senate` | 6 | Senate and House financial disclosures and trades, by symbol or name |
| `Esg` | 3 | ESG disclosures, ratings, benchmark |
| `Commitment_Of_Traders` | 3 | COT report, analysis, report list |
| `Fundraisers` | 6 | crowdfunding and equity offerings: latest, search, by CIK |

Total: 263 endpoints. Run `client.<Category>.help()` for exact endpoint names and parameters; the list above is current as of the bundled `fmp_endpoints.json` and may grow after an auto-update.

## Client Types and Rate Limits

| client_type | Requests / minute |
|---|---|
| `"Basic"` | 250 |
| `"Starter"` | 300 |
| `"Premium"` | 750 |
| `"Ultimate"` | 3000 |
| `"Enterprise"` | custom (set `custom_daily_limit`) |
| `"Custom"` | custom (set `custom_daily_limit`) |

```python
client = FMP(client_type="Enterprise", client_key="KEY", custom_daily_limit=5000)
client.get_usage_info()   # {'client_type': ..., 'minute_limit': ..., 'remaining': ..., 'seconds_until_reset': ...}
```

The rate limiter is a sliding window; calls block until capacity is available. Each endpoint also carries a per-tier access level. Calling an endpoint marked `NO_ACCESS` for your tier raises `PermissionError`; `LIMITED` emits a warning and still makes the call.

## API Keys and KeyManager

Keys are never written to disk by the client. `KeyManager` stores only the name of an environment variable per alias, plus the client type and an optional rate-limit override, in `~/.fmp/keys.json`.

```python
from fmp_stable_api import FMP, KeyManager

km = KeyManager()
km.add("work", env_var="FMP_KEY_WORK", client_type="Ultimate", set_default=True)

client = FMP.from_key("work")        # reads $FMP_KEY_WORK, applies stored client type
client = FMP.from_key()              # uses the default alias
client = FMP.from_key("FMP_KEY_1")   # any env var name works without registration
```

Put keys in a `.env` file (see `.env.example`) and load it before running: `set -a && . .env && set +a`. The `.env` file is git-ignored.

## Getting This Guide Programmatically

An agent or script can fetch this document at runtime instead of reading the file:

```python
from fmp_stable_api import get_skill
text = get_skill()          # module-level
text = client.get_skill()   # or from any client instance
```

Over MCP, call the parameterless `get_skill` tool. Both return the cached copy from `~/.fmp/skill.md` when present, otherwise the bundled one.

## Updating Endpoints

The endpoint list and this file are downloaded from the maintainer's GitHub repo and cached in `~/.fmp/`. The cache refreshes automatically on client init when it is older than 24 hours, or when the remote `last_updated` value changes. The bundled copies are used when the network is unavailable.

```python
from fmp_stable_api import update_endpoints

update_endpoints(force=True)          # module-level
client.update_endpoints(force=True)   # or via the client; clears cached categories
```

## MCP Server

```bash
pip install fmp-stable-api[mcp]
FMP_API_KEY=your_key FMP_CLIENT_TYPE=Ultimate fmp-mcp
```

Tools are exposed as `{Category}__{endpoint}`, for example `Search__search_symbol` or `Analyst__price_target_summary`, with the same parameter names as the Python client.

## GUI Manager

`fmp-gui` opens a tkinter editor for `fmp_endpoints.json` (categories, endpoints, parameters, per-tier access) and a local API key store.

## Key Classes

### `FMP(client_type, client_key=None, custom_daily_limit=None)`
Main client. Validates the client type, sets up the rate limiter, and loads the endpoint config lazily.

### `FMP.from_key(alias=None, client_type="Premium")`
Builds a client from a `KeyManager` alias or an environment variable name.

### `CategoryProxy`
Returned by `client.<Category>`. Resolves endpoint functions on first access and caches them. Has a `help()` method.

### `KeyManager`
`add`, `remove`, `set_default`, `list_keys`, `resolve`. See above.

## Security Notes

**Endpoint config trust:** downloaded `fmp_endpoints.json` is validated so that `stable_url` stays on `financialmodelingprep.com`; anything else is rejected and the cache is not updated.

**skill.md trust:** this file is loaded by AI assistants as context and is trusted as-is once downloaded. Keep the GitHub repository secured (2FA, limited write access) to prevent prompt injection through a modified skill.md.

**API keys:** the GUI stores keys in `~/.fmp/api_keys.json` with base64 obfuscation, not encryption. Do not share that file or commit any `.env`.
