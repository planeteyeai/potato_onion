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

Render’s default Python is **3.14**, which breaks Streamlit charts via Altair (`TypedDict ... closed`). Pin **3.11.9**.

1. Connect this GitHub repo in [Render](https://dashboard.render.com).
2. **New → Blueprint** (uses `render.yaml`) **or** **New → Web Service**:

| Setting | Value |
|---------|--------|
| Runtime | Python |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `streamlit run app.py --server.port $PORT --server.address 0.0.0.0 --server.headless true` |

3. In **Environment**, set:
   - **`PYTHON_VERSION`** = `3.11.9` (required; `runtime.txt` is ignored by Render)
   - **`LIVE_FEED_URL`** = `https://cdn.jsdelivr.net/gh/Internsplaneteyeinfra/onion_potato_commodity@main/feeds/agmarknet_latest.json`
   - Optional **`LIVE_API_TOKEN`** = your [data.gov.in](https://data.gov.in) API key
4. **Manual Deploy → Clear build cache & deploy** after changing `PYTHON_VERSION`.

Do not commit API keys. Free Render instances sleep when idle.

## Live prices without an India host

**Short answer:** Render will usually **not** get true second-by-second live data.gov.in prices (API often times out from overseas). Use the **CDN feed** instead.

How it works:

1. `feeds/agmarknet_latest.json` holds a real AGMARKNET snapshot in GitHub.
2. [jsDelivr](https://cdn.jsdelivr.net/gh/Internsplaneteyeinfra/onion_potato_commodity@main/feeds/agmarknet_latest.json) serves that file worldwide (CDN).
3. On Render the app loads **CDN first**, then tries data.gov.in, then local seed.

Refresh the feed (best from a PC in India):

```bash
python scripts/refresh_agmarknet_feed.py
git add feeds/agmarknet_latest.json agmarknet_seed.json
git commit -m "chore: refresh AGMARKNET CDN feed"
git push
```

A GitHub Action also tries every 3 hours (`workflow_dispatch` in Actions). US runners often fail the same way as Render — running the script on your laptop in India is the reliable refresh.

Optional: add repo secret `LIVE_API_TOKEN` for the Action.
