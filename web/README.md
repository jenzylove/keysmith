# Web app

Hand-authored static SPA — **no build step**. The three files in `dist/` are what
the backend serves (`GET /` with SPA fallback), so `web/dist` is committed as-is.

| File | Role |
|---|---|
| `dist/index.html` | shell: top bar, `#app` mount, footer policy line |
| `dist/styles.css` | the look; dark-first with a light theme via `prefers-color-scheme` |
| `dist/app.js` | the whole flow: landing → start → interview → plan → wallet → live run → result → proof |

## Flow

1. **Landing** — one line, two buttons, live box/runner status.
2. **Start** — pick a demo test wallet, or your own wallet type.
3. **Interview** — short memory questions (prefilled for demos); notes are treated as data.
4. **Plan** — profile in plain words, exact candidate count, honest expected/worst-case
   ranges, and a toggle to see the raw guesses that will run. Nothing is uploaded yet.
5. **Wallet** — only after you accept the plan: upload the file, or type the seed.
6. **Live run** — SSE stream: stage timeline, progress, seal checks, the event log, and a
   **Run the break-in test** button that fires the containment attack live.
7. **Result** — the password shown once (copy it), then the teardown receipt.
8. **Proof** — `/api/proof` results, or an honest "not run yet".

## Dev

`python scripts/devserver.py` serves this against a FakeLLM + a scripted FakeRunner,
so you can click the whole flow (and screenshot it) without live Vultr. The shipped
default runner is `NullRunner`, which refuses to fake a real run.
