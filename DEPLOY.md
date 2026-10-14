# Deploying VLSI Toolkit (GitHub → Vercel)

The whole app (React frontend **and** FastAPI backend) deploys as **one Vercel project**:

```text
                         ┌──────────────── Vercel project ────────────────┐
Browser ── https://… ──► │  CDN: React app (web/dist)                     │
                         │  /api/*  ──►  Python function: api/main.py     │
                         │              (FastAPI + vlsi_toolkit/)         │
                         └────────────────────────────────────────────────┘
```

Same address for both, so the frontend needs no API URL setting.

| File                | What it tells Vercel                                                                           |
| ------------------- | ---------------------------------------------------------------------------------------------- |
| `pyproject.toml`    | Python dependencies, the app entrypoint (`api.main:app`), and the build command for the React app |
| `.python-version`   | Use Python 3.12                                                                                |
| `vercel.json`       | Function settings: 30 s timeout, leave tests and `node_modules` out of the bundle              |
| `requirements.txt`  | Only what the server needs (heavy optional extras are in `requirements-extras.txt`)            |

## Step 1: push the code to GitHub

1. On https://github.com/new create a repository, e.g. **`VLSI_Toolkit`**.
   Do **not** tick "Add a README" or ".gitignore": the project already has them.
2. In a terminal in the `VLSI_Toolkit` folder:

   ```bash
   git init -b main          # once: makes this folder its own repository
   git add .
   git commit -m "VLSI Toolkit: CLI, API and React web app"
   git remote add origin https://github.com/Yogesh1786/VLSI_Toolkit.git
   git push -u origin main
   ```

   The first push opens a browser window to sign in to GitHub (Git Credential Manager).

Later changes: `git add .` → `git commit -m "what changed"` → `git push`. Vercel redeploys automatically.

## Step 2: import the repository in Vercel

1. Sign in at https://vercel.com with **Continue with GitHub**.
2. **Add New… → Project**, pick `VLSI_Toolkit`, click **Import**
   (if it is not listed: *Adjust GitHub App Permissions* and allow the repository).
3. Settings:
   - **Framework Preset:** `FastAPI` (detected automatically)
   - **Root Directory:** `./`
   - Build command, output directory, install command: leave the defaults (they come from `pyproject.toml`)
   - Environment variables: none needed
4. Click **Deploy**. After 1–2 minutes you get `https://vlsi-toolkit-xxxx.vercel.app`.

Check it: open `/api/health` on that address. It should show `"ok": true` and `"hosted": true`.

## What is different online

| Feature                     | On your computer                  | On Vercel                                                                  |
| --------------------------- | --------------------------------- | -------------------------------------------------------------------------- |
| Tools with Example / Upload | ✔                                 | ✔ (uploads up to about **4 MB** per request, Vercel's limit)               |
| Project Workspace           | Open any folder on your computer  | Shows the bundled `examples/` project only. Opening folders is blocked, so visitors cannot read files on the server |
| Trends / saved runs         | Kept in `~/.vlsi_toolkit/`        | Kept in the server's temp folder: shared by all visitors and **lost on every redeploy or restart** |
| ngspice sweep `--run`       | If ngspice is installed           | Not available                                                              |

Hosted mode switches on automatically on Vercel (`VERCEL=1`). On another host, set `VT_HOSTED=1`.

> The deployed site is **public**: anyone with the link can use it. Don't upload company RTL, reports or
> netlists to it; use the local app (`start_app.bat`) for real project data.
> To limit access, turn on *Vercel Authentication* under Project → Settings → Deployment Protection.

## Troubleshooting

| Symptom                               | Fix                                                                                                 |
| ------------------------------------- | --------------------------------------------------------------------------------------------------- |
| Build log: `npm: command not found` or the React build fails | Set **Build Command** in Project → Settings → Build & Development to `npm --prefix web ci && npm --prefix web run build` |
| Page loads but every tool says *API server not running* | Open `/api/health`. If it is a 404 or 500, check the **Functions** logs in the Vercel dashboard |
| `413 Payload Too Large`               | The uploaded file is over Vercel's ~4.5 MB request limit; use the local app for big VCD/DEF files   |
| *API server is outdated* banner       | The browser has an old page cached: hard-refresh (Ctrl+F5)                                          |
