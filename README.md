# coinspot-mcp

Python [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server for the [CoinSpot Australia API](https://www.coinspot.com.au/api) (v2).

## Auth model

1. **MCP connection auth (required for Lambda/HTTP)**  
   Clients must send `Authorization: Bearer <COINSPOT_MCP_AUTH_TOKEN>` on every request to the MCP endpoint.

2. **Per-user CoinSpot credentials (required for account tools)**  
   Authenticated tools require `coinspot_api_key` and `coinspot_api_secret` arguments supplied by the calling LLM for that end-user’s CoinSpot account.  
   Public market tools do not need CoinSpot credentials.

## Features

- **Public API** – latest prices, buy/sell prices, open and completed order books
- **Read-only API** – balances, open orders, order history, deposits/withdrawals, send/receive, affiliate/referral payments
- **Full-access API** – quotes, deposit addresses, place/edit/cancel orders, buy/sell/swap now
- **Per-user CoinSpot credentials** – passed as tool arguments from the LLM
- **MCP bearer auth** – required for remote Function URL access
- **Least-privilege exposure** – trading/withdrawal tools only registered when enabled
- **Runtime guards** – optional confirm token, amount caps, withdrawal address allowlist
- **Audit logging** – redacts API keys/secrets from logs
- **AWS Lambda packaging** – Streamable HTTP via Mangum + SAM

API reference: [CoinSpot API v2](https://www.coinspot.com.au/v2/api)

## Requirements

- Python 3.12+
- CoinSpot API keys generated per user from [API settings](https://www.coinspot.com.au/my/api)

## Install

```bash
uv sync
```

## Configuration

```bash
# Required for Lambda/HTTP MCP gateway access
export COINSPOT_MCP_AUTH_TOKEN=long-random-mcp-bearer-token

# Optional – destructive tools disabled by default
export COINSPOT_ALLOW_TRADING=false
export COINSPOT_ALLOW_WITHDRAWALS=false
export COINSPOT_DESTRUCTIVE_CONFIRM_TOKEN=long-random-string
export COINSPOT_MAX_ORDER_AMOUNT=0.01
export COINSPOT_MAX_WITHDRAW_AMOUNT=0.01
export COINSPOT_WITHDRAW_ADDRESS_ALLOWLIST=bc1qyouraddress
```

CoinSpot user keys are **not** configured as server env vars in multi-user mode. The LLM passes them per tool call.

## Run (local stdio)

```bash
uv run coinspot-mcp
```

## Example tools

| Tool | MCP bearer | CoinSpot key/secret args | Description |
|------|------------|--------------------------|-------------|
| `get_latest_prices` | HTTP only | No | Public prices |
| `get_my_balances` | HTTP only | Yes | User balances |
| `quote_buy_now` | HTTP only | Yes | Instant quote |
| `place_buy_order` | HTTP only | Yes + trading flag | Place order |
| `withdraw_coin` | HTTP only | Yes + withdraw flag | Withdraw coins |

## AWS Lambda (SAM)

### Build

```bash
uv sync
sam validate --lint
sam build
```

### Deploy

```bash
sam deploy --guided \
  --parameter-overrides \
    "McpAuthToken=$(openssl rand -hex 32)" \
    "AllowTrading=false" \
    "AllowWithdrawals=false"
```

Outputs:

- `McpEndpoint` → `https://<function-url>/mcp`

### Client config (HTTP MCP)

```json
{
  "mcpServers": {
    "coinspot": {
      "url": "https://YOUR_FUNCTION_URL/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_MCP_AUTH_TOKEN"
      }
    }
  }
}
```

Then, when calling account tools, the LLM must provide that user’s:

- `coinspot_api_key`
- `coinspot_api_secret`

## Security notes

- Putting CoinSpot secrets in LLM tool arguments means they enter model context. Prefer short-lived/read-only keys and strong host controls.
- MCP bearer token protects the gateway; it is separate from CoinSpot credentials.
- Audit logs redact `coinspot_api_key` / `coinspot_api_secret`.
- `withdraw_coin` always forces CoinSpot `emailconfirm=YES`.
- Keep trading/withdrawal tools disabled unless intentionally enabled.

## Development

```bash
uv sync
uv run pytest
```

## License

MIT
