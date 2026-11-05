# Deploying the library agent

The app is one container. FastAPI serves the API **and** the built React site on a single port, with SQLite inside the container.
On first start it seeds the demo data automatically (about 10 s).

## Option A: Render (free, recommended)

You need a free account at **render.com**. Sign up with your GitHub account; no card is needed for the free plan.

1. In Render: **New + → Blueprint**.
2. Connect GitHub and give Render access to the **`KrisJeffordImmanuvel/FAI`** repository.
3. Pick the repository and branch **`main`**. Render reads `render.yaml` and shows one web service, **circulus-library-agent**. Click **Apply** (or **Deploy Blueprint**).
4. The first build takes about 5–10 minutes. When the status turns **Live**, open the URL shown at the top. It will look like `https://circulus-library-agent.onrender.com`; Render adds a suffix if that name is taken.
5. Sign in with the demo accounts shown on the login page.

**Logs tab = terminal output.** Render's **Logs** tab shows the same live agent output as your laptop's terminal: cycles, rules fired, notifications and user actions.

Every `git push` to `main` redeploys automatically (`autoDeploy: true`).

<details>
<summary>Without the Blueprint (manual setup)</summary>

**New + → Web Service** → pick the repo → **Language/Runtime: Docker** → **Instance type: Free** → under *Advanced*:
- Health check path: `/api/health`
- Environment variable `LIBRARY_SECRET` = any long random text

Then **Create Web Service**.
</details>

### What to expect on the free plan
- **It sleeps after about 15 minutes without visitors.** The next visit takes about a minute to wake up. Open the link a few minutes before your viva.
- **Data resets whenever the service restarts or redeploys.** Every start seeds fresh demo data, which is ideal for a demo. Keeping data across restarts needs a paid persistent disk.
- **Anyone with the link can use the demo logins**, because they're printed on the login page. That includes *Reset simulation*, which resets the data for everyone. Share the link only with people who need it.

## Option B: any Docker host (Railway, Fly.io, Hugging Face Spaces, a VPS…)

```bash
docker build -t library-agent .
docker run -p 8000:8000 -e LIBRARY_SECRET=change-me library-agent
```
Then open http://localhost:8000.

The container listens on **`$PORT`** (default 8000), which most platforms set automatically. Useful environment variables:

| Variable | Purpose |
|---|---|
| `PORT` | Port to listen on (set by the platform) |
| `LIBRARY_SECRET` | Signs login tokens; set a long random value |
| `LIBRARY_CONSOLE_LOG` | `1` (default) prints the agent's decisions to the logs |
| `LIBRARY_ACCESS_LOG` | `1` also logs every HTTP request |

## What was tested
- The production image starts from an empty disk, seeds itself and is ready in about 8 s.
- The Docker health check reports *healthy*, and the container runs as a non-root user.
- Login, page deep links (e.g. `/catalog`), an agent cycle, the full guided demo and *Reset simulation* all work in a browser against the container.
