# Onion & Potato Commodity Intelligence

Live mandi dashboard for onion and potato (AGMARKNET via data.gov.in), with procurement, finance, storage, risk charts, and report downloads.

## Local run

```bash
pip install -r requirements.txt
copy config.example.json config.json
# put your data.gov.in API key in config.json as live_api_token
streamlit run app.py
```

Or use `run.bat` / `./run.sh`.

## Render deploy

1. Connect this GitHub repo in [Render](https://dashboard.render.com).
2. **New → Blueprint** (uses `render.yaml`) **or** **New → Web Service** with:

| Setting | Value |
|---------|--------|
| Runtime | Python 3.11 |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `streamlit run app.py --server.port $PORT --server.address 0.0.0.0 --server.headless true` |

3. Set environment variable **`LIVE_API_TOKEN`** to your [data.gov.in](https://data.gov.in) API key.
4. Optional: `LIVE_API_URL` (defaults to the AGMARKNET resource URL).

Do not commit API keys. Free Render instances sleep when idle.

## Config priority

`LIVE_API_TOKEN` env → Streamlit secrets → `config.json` → public sample key (rate-limited).
