# Pathway · NUS CS Course Planner

A local web demo for CS3263 Group 1. Students can search real NUS courses, edit requirement/preference cards, describe their preferences to a SoCLaaS-backed assistant, generate a semester plan with the bundled PyCSP3 engine, and export the plan to NUSMods.

The team repository keeps this app in **`web/`**, separate from the existing root-level algorithm baseline. Run the following commands from `web/`, not the repository root.

## 1. Requirements

| Tool | Needed for |
| --- | --- |
| Git | Cloning the repository |
| Python 3.10+ and `venv` | Backend, preference parsing and solver adapter |
| Java 11+ on `PATH` | Bundled ACE / PyCSP3 solver |
| A modern browser | Using the web interface |
| Node.js 24+ and npm, optional | Frontend regression tests only |
| SoCLaaS API key, optional | Natural-language preference chat only |

There is **no frontend build step**. You do not need `npm install` to run the app. The course metadata and reference timetables are included, so manual constraints and planning do not require a model key or a data download.

The app was tested on Linux with Python 3.13.11, OpenJDK 11 and Node.js 24.16.0. Windows users should use **WSL2 with Ubuntu** for the complete solver and background launcher. On macOS, use the foreground launch described below; `run.sh start/stop` uses Linux process inspection.

## 2. Clone and install

The repository is private; sign in to a GitHub account with access before cloning. The web handoff is on `feat/course-planner-web`:

```bash
git clone --branch feat/course-planner-web https://github.com/blacksesamezongzi/CS3263-Group1-Project.git
cd CS3263-Group1-Project/web
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
java -version
```

On Ubuntu/WSL, if `venv` or Java is missing, install the system prerequisites first:

```bash
sudo apt update
sudo apt install git python3 python3-venv default-jre
```

If you already have this standalone web checkout, start from the directory containing `run.sh` instead of cloning again.

## 3. Start the website

### Linux / WSL: keep it running in the background

```bash
./run.sh start
```

Open **http://127.0.0.1:8000**. Keep using the same address: `localhost` and `127.0.0.1` have separate browser drafts.

```bash
./run.sh status                  # Check readiness
./run.sh stop                    # Stop the background process
```

Logs are written to `.run/server.log`. The process runs independently of the launching terminal. This does not install a system service or start the app automatically after a reboot.

### Foreground development: Linux, WSL or macOS

```bash
./run.sh
```

Keep that terminal open. Press `Ctrl+C` to stop it. Do not run both foreground and background instances on port 8000.

The launch script automatically uses the local `.venv`; activating it is not required after installation. It loads `.env` when that file exists.

### Check that startup worked

The page should show **16 default cards: 14 requirements and 2 preferences**. Useful endpoints:

- http://127.0.0.1:8000/api/health — backend and model-configuration status
- http://127.0.0.1:8000/api/config — defaults, course catalogue and reference data
- http://127.0.0.1:8000/docs — interactive API documentation

## 4. Enable preference chat, optional

The site and CSP work without an API key. To enable chat, copy the example file and edit it locally:

```bash
cp .env.example .env
```

```dotenv
SOCLAAS_API_KEY=your-personal-key
SOCLAAS_MODEL=qwen3.6:35b
SOCLAAS_BASE_URL=https://soclaas-api.comp.nus.edu.sg/v1
```

Restart the backend after changing `.env`. Use the ID of a chat-capable model available to your key; `GET /api/models` lists available IDs after the backend key is configured. The example model was smoke-tested, but availability depends on the gateway and key.

See the [official SoCLaaS API setup guide](https://soclaas.comp.nus.edu.sg/guides/api.html). Keys are read only by the backend. **Never commit `.env` or put a key in frontend code.** Each group member should configure their own local key. `.env`, `.venv`, `.run`, `node_modules`, editor settings and generated output are excluded from Git.

## 5. Try the complete demo

1. Open the website and inspect the default requirement cards. **Reset defaults** restores the full list; **Course catalogue** searches real courses by code, title or category.
2. Add a constraint manually or ask the assistant, for example: `I want to take CS2102 in semester 3.` The reply adds one or more cards containing structured solver rules.
3. Click **Generate my plan**. Generation searches the degree assignment and checks a complete class selection for each active semester. Allow time for refinement; the outer solver limit is 110 seconds.
4. Check the degree plan and **Weekly timetable**. CS2101 and CS2103T must be in the same semester; the project maps CS2101 attendance to the matching CS2103T teaching group.
5. Click **Export to NUSMods → Download Planner JSON**. Open [NUSMods Planner](https://nusmods.com/planner), click **Upload**, and choose the JSON file. Import replaces the existing Planner in that browser.

Changing constraints or settings invalidates the previous export. Deleting a card removes all of its nested rules from the next CSP request. An independent foundation/prerequisite audit still runs: invalid academic results are **preview-only**, show their unmet requirements and cannot be exported. The download endpoint checks the actual assignments again.

Browser drafts are stored locally. An empty legacy draft restores defaults; a list explicitly emptied by the user remains empty until reset. The app does not share drafts or plans across browsers or computers.

## 6. Troubleshooting

| Symptom | What to do |
| --- | --- |
| `Failed to fetch` / backend unavailable | Run `./run.sh status`, then `./run.sh start` if needed. Reload or click **Retry connection**. |
| Empty cards or old UI | Press `Ctrl+F5` and click **Reset defaults**. Use the same browser address consistently. |
| Port 8000 already in use | Stop the previous instance with `./run.sh stop`; if it was started in a foreground terminal, stop it there with `Ctrl+C`. |
| `.venv/bin/uvicorn` missing | From `web/`, create `.venv` and install `requirements.txt`. |
| Solver cannot run | Confirm `java -version`, check `.run/server.log`, and confirm you launched from `web/`. |
| Chat is not configured / HTTP 401 or 403 | Check your own `.env` key and model, then restart. Manual constraints still work. |
| No feasible plan / timeout | Remove conflicting user rules, relax workload settings or increase the search horizon. A timeout is not a proof of infeasibility. |
| Export disabled | Regenerate after edits. If the academic audit fails, restore core/prerequisite cards and fix the listed requirements. |
| Data changed after refresh | Restart the backend so generation and weekly display load the same snapshot. |

## 7. Developer handoff

```text
web/
├── backend/                       FastAPI, SoCLaaS, rule schemas and verification
│   └── solver_adapter.py          Dynamic PyCSP3 integration entry point
├── frontend/                      HTML, CSS and JavaScript; no build step
├── assets/data/course_details.json Course metadata, provenance and meetings
├── scripts/                       Background launcher and catalogue refresh
├── src/ and pycsp3/                Web adapter's bundled solver dependencies
├── tests/                         API/solver and DOM regressions
├── docs/WEB_INTEGRATION.md         Detailed integration contract
├── requirements.txt
└── run.sh
```

```text
Chat → SoCLaaS → validated constraint cards
Cards → isolated degree solver ↔ complete weekly class-choice search
      → independent academic checks → semester plan → checked JSON export
```

The integration seam is **`backend/solver_adapter.py::solve_plan(request)`**. Its assignments map course codes to overall semesters: `1 = Y1S1`, `3 = Y2S1`, and `0 = not selected`. The web app currently uses its own bundled PyCSP3 adapter; it does **not** call the separate root-level `planner.run_foundation` baseline. Algorithm teammates can replace the adapter while keeping the versioned API. See [WEB_INTEGRATION.md](docs/WEB_INTEGRATION.md) and `/docs` for the exact schema and validation requirements.

### Run tests from `web/`

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q tests/test_api.py
npm ci
npm test
```

The Python suite launches real Java/PyCSP3 jobs. The JS suite uses jsdom to check DOM events, saved drafts and request payloads. Node.js 24+ is sufficient for the locked jsdom dependency. Browser rendering and animation appearance still need manual review.

### Update your checkout

For a background instance on Linux/WSL:

```bash
./run.sh stop
git pull --ff-only
.venv/bin/python -m pip install -r requirements.txt
./run.sh start
```

For foreground development, stop the terminal process before updating and run `./run.sh` again afterwards.

## 8. Data, rules and current limits

- The default standard-CS target is 160 units. The bundled AY2026/27 catalogue has 281 real courses, including officially listed ID/CD and GE choices. Graduate-level and year-long GEN variants may be browse-only.
- Degree sources: [CS cohort requirements](https://www.comp.nus.edu.sg/cug/per-cohort/cs/cs-26-27/), [SoC Common Curriculum](https://www.comp.nus.edu.sg/cug/soc-22-23/), [approved GE list](https://www.nus.edu.sg/registrar/academic-information-policies/undergraduate-students/general-education/list-of-courses-approved-under-the-ge-pillars), and [NUSMods reference data](https://api.nusmods.com/v2/2026-2027/). Cards and course entries include relevant links.
- Later academic years assume the reference offerings, exam dates and meetings repeat. CS2101 shares the CS2103T tutorial/communication package according to the project's confirmed mapping.
- The student profile assumes satisfied English placement and, by default, H2/A-level Mathematics. The Mathematics checkbox changes the bridging-course route; it does not mark CS1231S or other university courses as already completed.
- Weekly conflicts are fed back into degree search. Missing lesson data stops strict validation; explicitly enabled conditional plans list the unverified courses.
- Full degree-category rules, preclusions, personal exemptions, internships/FYP and year-long course modelling remain incomplete. Passing the implemented audit is not a complete graduation certification.
- This is a local prototype without login or multi-user persistent storage.

The snapshot is already committed. Refreshing is a maintainer operation, not a setup step:

```bash
.venv/bin/python scripts/refresh_catalogue.py
```

The refresh script parses the official ID/CD list and matches it to NUSMods offerings. Its recorded GE membership must be reviewed when the Registrar's approved list changes. Restart after refreshing data.
