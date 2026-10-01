# coinspot-mcp

Python [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server for the [CoinSpot Australia API](https://www.coinspot.com.au/api) (v2).

It exposes public market data, read-only account tools, and optional trading/withdrawal tools to MCP clients such as Cursor.

## Features

- **Public API** – latest prices, buy/sell prices, open and completed order books
- **Read-only API** – balances, open orders, order history, deposits/withdrawals, send/receive, affiliate/referral payments
- **Full-access API** – quotes, deposit addresses, place/edit/cancel orders, buy/sell/swap now
- **Safety gates** – trading and withdrawals are disabled unless explicitly enabled via environment variables
- **HMAC-SHA512 auth** – signs compact JSON bodies as required by CoinSpot

API reference: [CoinSpot API v2](https://www.coinspot.com.au/v2/api) (legacy docs: [v1](https://www.coinspot.com.au/api))

## Requirements

- Python 3.12+
- A CoinSpot account and API key from [API settings](https://www.coinspot.com.au/my/api)

## Install

```bash
uv sync
```

Or with pip:

```bash
pip install -e .
```

## Configuration

Copy `.env.example` and set credentials:

```bash
export COINSPOT_API_KEY=your_api_key
export COINSPOT_API_SECRET=your_api_secret

# Optional – disabled by default
export COINSPOT_ALLOW_TRADING=false
export COINSPOT_ALLOW_WITHDRAWALS=false
```

Use a **read-only** API key for balances/history only. Use a **full-access** key for trading. Withdrawals must also be enabled on the key in CoinSpot settings.

## Run

Stdio MCP server (default for Cursor / Claude Desktop):

```bash
uv run coinspot-mcp
# or
uv run python -m coinspot_mcp
```

## Cursor MCP config

Add to your MCP settings (e.g. `~/.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "coinspot": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/coinspot-mcp", "run", "coinspot-mcp"],
      "env": {
        "COINSPOT_API_KEY": "your_api_key",
        "COINSPOT_API_SECRET": "your_api_secret",
        "COINSPOT_ALLOW_TRADING": "false",
        "COINSPOT_ALLOW_WITHDRAWALS": "false"
      }
    }
  }
}
```

## Example tools

| Tool | Auth | Description |
|------|------|-------------|
| `get_latest_prices` | None | All market prices |
| `get_latest_coin_price` | None | Price for one coin/market |
| `get_open_orders` | None | Public order book |
| `get_my_balances` | RO/Full | Account balances |
| `get_my_order_history` | RO/Full | Completed orders |
| `quote_buy_now` / `quote_sell_now` | Full | Instant quotes |
| `place_buy_order` / `place_sell_order` | Full + `COINSPOT_ALLOW_TRADING` | Place limit orders |
| `withdraw_coin` | Full + `COINSPOT_ALLOW_WITHDRAWALS` | Withdraw to an address |

## Development

```bash
uv sync
uv run pytest
```

## Security notes

- Prefer a read-only key when you only need balances and history.
- Keep `COINSPOT_ALLOW_TRADING` and `COINSPOT_ALLOW_WITHDRAWALS` off unless you intentionally want the model to place orders or withdraw funds.
- `withdraw_coin` defaults `emailconfirm` to `YES` so CoinSpot still requires email confirmation.

## License

MIT
