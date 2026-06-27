# fmp-stable-api

**Financial Modeling Prep API client** — auto-updating endpoints, GUI manager, and optional MCP server.

## Install

```bash
pip install fmp-stable-api           # API client + GUI
pip install fmp-stable-api[mcp]      # also includes the MCP server
```

## Quick start

```python
from fmp_stable_api import FMP

client = FMP(client_type="Premium", client_key="your_api_key")

# Dynamic endpoint access — categories and endpoints loaded from fmp_endpoints.json
results = client.Search.search_symbol(symbol="AAPL")

# Raw URL request
data = client.request("https://financialmodelingprep.com/stable/profile", {"symbol": "AAPL"})

# Show all available categories
client.help()

# Show endpoints in a category
client.Search.help()
```

## Endpoints auto-update

On first use and once every 24 hours, the client fetches the latest `fmp_endpoints.json`
from GitHub and caches it at `~/.fmp/fmp_endpoints.json`.
A bundled fallback is used when the network is unavailable.

```python
# Force an immediate refresh
from fmp_stable_api import update_endpoints
update_endpoints(force=True)

# Or via the client
client.update_endpoints(force=True)
```

## GUI manager

A tkinter-based GUI for browsing and editing `fmp_endpoints.json`:

```bash
fmp-gui
```

## MCP server (Claude Desktop / AI assistants)

```bash
pip install fmp[mcp]
```

Add to your Claude Desktop `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "fmp": {
      "command": "fmp-mcp",
      "env": {
        "FMP_API_KEY": "your_api_key_here",
        "FMP_CLIENT_TYPE": "Premium"
      }
    }
  }
}
```

Tools are named `{Category}__{endpoint}`, e.g. `Search__search_symbol`.

## API key tiers

| Tier | Requests / min |
|------|---------------|
| Basic | 250 |
| Starter | 300 |
| Premium | 750 |
| Ultimate | 3 000 |
| Enterprise / Custom | set via `custom_daily_limit` |

```python
# Enterprise or Custom key
client = FMP(client_type="Enterprise", client_key="key", custom_daily_limit=5000)
```

## Download to file

```python
client.download(
    "https://financialmodelingprep.com/stable/profile-bulk",
    params={"part": 0},
    filename="profiles.csv",
)
```

## Usage info

```python
print(client.get_usage_info())
# {'client_type': 'Premium', 'minute_limit': 750, 'remaining': 748, 'seconds_until_reset': 43.2}
```

## Cache files

| Path | Contents |
|------|----------|
| `~/.fmp/fmp_endpoints.json` | Downloaded endpoints config |
| `~/.fmp/skill.md` | Downloaded MCP skill file |
| `~/.fmp/.meta.json` | Cache timestamps |
| `~/.fmp/api_keys.json` | GUI API key storage |

## Security

**API Keys:**
- Never commit API keys to git. The GUI stores keys in `~/.fmp/api_keys.json` automatically.
- If you had an API key in a config file that was committed to a git repository, **rotate it immediately** in your FMP account dashboard. Treat any committed key as compromised.
- Do not share `~/.fmp/api_keys.json`.

**Endpoint Updates:**
- Downloaded `fmp_endpoints.json` is validated to ensure `stable_url` stays on `financialmodelingprep.com`. Tampered configs with off-domain base URLs are rejected.

## License

MIT
