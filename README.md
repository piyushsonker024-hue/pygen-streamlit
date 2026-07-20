# Pyngyn — AI Delivery Insights (Streamlit)

A task time-tracking analytics app. Upload a CSV, it finds the delivery
bottlenecks with pandas, has Claude turn the numbers into plain-English findings,
and shows them with an interactive slip rail and a parity scatter.

Everything is Python — no HTML file to maintain.

## Run it locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Your browser opens at `http://localhost:8501`. It loads the bundled sample data
immediately. Use the buttons to **upload your own CSV**, switch the slip-rail
breakdown, or **regenerate insights**.

Your CSV needs five columns: `task_id, assignee, estimated_hours, actual_hours, status`.

### Live insights (optional)

Without a key the app runs on a bundled cached insight set, so it works out of the
box. To have Claude write insights from your actual data, provide a key one of two ways:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
streamlit run app.py
```

or create `.streamlit/secrets.toml` (gitignored):

```toml
ANTHROPIC_API_KEY = "sk-ant-..."
```

The caption under the header shows which mode is active (`live: claude-sonnet-5`
or `cached`). If a live call ever fails, it falls back to cached rather than
breaking the page.

## What's in the box

```
app.py                 the Streamlit app — layout, charts, controls
analysis.py            the pandas bottleneck analysis (returns a stats dict)
insights.py            Claude call + cached fallback
sample_tasks.csv       160-task demo dataset
insights_cached.json   insight set used when no key is set
requirements.txt       streamlit, pandas, plotly, anthropic
.streamlit/config.toml theme
```

**Python computes the numbers; Claude writes the English.** Only the aggregates
go to the model, never the raw rows, so the numbers stay authoritative. The
headline is the model's own most-severe finding.

## Deploy it from GitHub — Streamlit Community Cloud (free)

A Streamlit app is a running Python server, so it doesn't go on static hosts like
Cloudflare Pages. The free, GitHub-native home for it is **Streamlit Community Cloud**:

1. Push this folder to a GitHub repo (`app.py` at the repo root).
2. Go to **share.streamlit.io** and sign in with GitHub.
3. **Create app** → pick your repo, branch `main`, main file `app.py` → **Deploy**.
4. For live insights: in the app's **Settings → Secrets**, paste
   `ANTHROPIC_API_KEY = "sk-ant-..."` and save. The app restarts with it.

You get a public `https://<your-app>.streamlit.app` URL, and every push to `main`
redeploys automatically.

> Other one-click options that also deploy Python servers from GitHub: Hugging Face
> Spaces (pick the Streamlit SDK), Render, or Railway. Same idea — connect the repo,
> set the `ANTHROPIC_API_KEY` secret, done.

## Testing

The app is covered by Streamlit's `AppTest` framework (runs the script in-process,
no browser). To exercise it:

```python
from streamlit.testing.v1 import AppTest
at = AppTest.from_file("app.py").run()
assert not at.exception
assert at.title[0].value            # hero = model's top finding
at.radio[0].set_value("Assignee").run()   # switch the slip-rail cut
at.button[1].click().run()                # regenerate insights
```
