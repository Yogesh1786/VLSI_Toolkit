# Deploying VLSI Toolkit: frontend on Vercel, backend on Render

```text
Browser ──► https://vlsi-toolkit.vercel.app            (Vercel: React app from web/)
               │  every /api/... call goes to
               ▼
            https://vlsi-toolkit-api.onrender.com      (Render: FastAPI from api/ + vlsi_toolkit/)
```

Two settings connect the two halves:

| Setting        | Set on | Value              | Why                                                  |
| -------------- | ------ | ------------------ | ---------------------------------------------------- |
| `VITE_API_URL` | Vercel | the Render address | tells the React app where the API is                 |
| `CORS_ORIGINS` | Render | the Vercel address | lets the browser accept answers from another address |

Files used: `render.yaml` + `requirements.txt` + `.python-version` (Render), `web/vercel.json` (Vercel).

---

## Step 1: push the code to GitHub

1. Create an **empty** repository at https://github.com/new, e.g. `VLSI_Toolkit`
   (do not add a README or .gitignore).
2. In the `VLSI_Toolkit` folder:

   ```bash
   git remote add origin https://github.com/Yogesh1786/VLSI_Toolkit.git
   git push -u origin main
   ```

Later changes: `git add .` → `git commit -m "..."` → `git push`. Both Render and Vercel redeploy automatically.

## Step 2: backend on Render (do this first, Vercel needs its address)

1. Sign up at https://render.com with **GitHub**.
2. **New + → Blueprint** → connect GitHub → pick `VLSI_Toolkit`.
   Render reads `render.yaml` and shows one service, `vlsi-toolkit-api` (free plan, Singapore).
3. It asks for **`CORS_ORIGINS`**. You don't know the Vercel address yet: type `http://localhost:5173` for now.
4. Click **Apply** / **Deploy Blueprint**. The first build takes 2–4 minutes.
5. Copy the service address from the top of the page, e.g. `https://vlsi-toolkit-api.onrender.com`.
   Check it: open `https://vlsi-toolkit-api.onrender.com/api/health` and you should see `"ok":true,"hosted":true`.
   The API documentation is at `/docs`.

<details><summary>Without the Blueprint (manual setup)</summary>

**New + → Web Service** → pick the repository, then:

| Field                        | Value                                              |
| ---------------------------- | -------------------------------------------------- |
| Language                     | Python 3                                           |
| Branch                       | `main`                                             |
| Root Directory               | _(empty)_                                          |
| Build Command                | `pip install -r requirements.txt`                  |
| Start Command                | `uvicorn api.main:app --host 0.0.0.0 --port $PORT` |
| Instance Type                | Free                                               |
| Health Check Path (Advanced) | `/api/health`                                      |
| Environment Variable         | `CORS_ORIGINS` = your Vercel address               |

</details>

## Step 3: frontend on Vercel

1. Sign in at https://vercel.com with **GitHub** → **Add New… → Project** → import `VLSI_Toolkit`.
2. Settings:
   - **Root Directory:** click _Edit_ and choose **`web`** (important)
   - **Framework Preset:** Vite (detected)
   - Build / Output: leave the defaults (`npm run build`, `dist`)
   - **Environment Variables:** `VITE_API_URL` = `https://vlsi-toolkit-api.onrender.com` (your Render address, no `/` at the end)
3. **Deploy**. Copy your address, e.g. `https://vlsi-toolkit.vercel.app`.

## Step 4: connect them

1. Render → `vlsi-toolkit-api` → **Environment** → edit `CORS_ORIGINS` →
   `https://vlsi-toolkit.vercel.app` → **Save, rebuild and deploy**.
   Several addresses are allowed, separated by commas (no spaces needed, no `/` at the end).
2. Open the Vercel address. The tools should load the examples and show results.

Optional, for Vercel _preview_ deployments (each branch or pull request gets its own address): add
`CORS_ORIGIN_REGEX` = `https://vlsi-toolkit-.*\.vercel\.app` on Render.

> `VITE_API_URL` is baked in when the React app is **built**. If you change it on Vercel, redeploy
> (Deployments → ⋯ → Redeploy) for it to take effect.

---

## What is different online

| Feature                     | On your computer           | Online                                                                                           |
| --------------------------- | -------------------------- | ------------------------------------------------------------------------------------------------ |
| Tools with Example / Upload | ✔                          | ✔                                                                                                |
| Project Workspace           | Open any folder            | Bundled `examples/` only. Opening folders is blocked, so visitors can't read files on the server |
| Trends / saved runs         | Kept in `~/.vlsi_toolkit/` | Temporary: shared by all visitors, **lost on every deploy or restart**                           |
| ngspice sweep `--run`       | If ngspice is installed    | Not available                                                                                    |

Hosted mode switches on automatically on Render (`RENDER` variable) and Vercel. On other hosts set `VT_HOSTED=1`.

**Render free plan:** the server **sleeps after 15 minutes without requests**. The next visitor waits up to
about a minute while it wakes up (the app shows "Cannot reach the API server… wait a moment"; it
retries every 15 s by itself). Free instances have 0.1 CPU and 512 MB RAM, enough for this toolkit.

> The site is **public**. Don't upload company RTL, reports or netlists to it. Use the local app
> (`start_app.bat`) for real project data.

## Troubleshooting

| Symptom                                               | Fix                                                                                                                     |
| ----------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| Browser console: _blocked by CORS policy_             | `CORS_ORIGINS` on Render must be exactly the Vercel address (`https://…vercel.app`, no `/` at the end). Save → redeploy |
| Every tool says _Cannot reach the API server at …_    | Render is waking up (wait 1 min), or `VITE_API_URL` is wrong. Open `<render address>/api/health` directly               |
| Tools call `vercel.app/api/...` and get 404           | `VITE_API_URL` was not set when the site was built: set it and **Redeploy**                                             |
| Refreshing a page such as `/lint` gives 404 on Vercel | Root Directory must be `web` so `web/vercel.json` (page fallback) is used                                               |
| Render build fails on the Python version              | `.python-version` sets 3.12; check the build log, or set `PYTHON_VERSION` to a full version such as `3.12.8`            |
| _API server is outdated_ banner                       | Render is still running the old version: wait for its deploy to finish, then refresh                                    |
