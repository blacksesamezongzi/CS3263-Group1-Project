# CS3263 Group 1 · NUS Course Planner

This repository contains the team's course-planning algorithms and the **Pathway web demo**. The web demo is on branch **`feat/course-planner-web`** and lives in **`web/`**.

## Run the web demo locally

Use Python 3.10+, Java 11+ (`java` on PATH), Git, and a modern browser. Linux/Ubuntu is supported; Windows users should use WSL2 Ubuntu. Node/npm are only needed for frontend tests.

```bash
git clone --branch feat/course-planner-web https://github.com/blacksesamezongzi/CS3263-Group1-Project.git
cd CS3263-Group1-Project/web
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
java -version
./run.sh start
```

Open **http://127.0.0.1:8000**. On Linux/WSL, `./run.sh status` checks the background process and `./run.sh stop` stops it. On macOS, use `./run.sh` in the foreground and keep that terminal open. The background launcher uses Linux process inspection.

You do **not** need a frontend build, `npm install`, a model key, or a fresh course-data download to try manual constraints and generate a plan. The page starts with 14 requirements and 2 preferences.

### Optional: enable the assistant

From `web/`:

```bash
cp .env.example .env
```

Edit your local `.env` and set `SOCLAAS_API_KEY` to your own key. `SOCLAAS_MODEL` must be a chat-capable model available to that key; the template includes a tested example. Restart the backend after editing the file. Never commit `.env` or share a personal key in source code.

The assistant turns natural-language preferences into validated constraint cards. Manual editing and CSP generation work without it.

### More setup and troubleshooting

See **[web/README.md](web/README.md)** for OS requirements, complete setup, model discovery, update steps, tests, NUSMods export and troubleshooting. API docs are available at http://127.0.0.1:8000/docs while running.

If the page shows `Failed to fetch`, check `./run.sh status`. If an old draft hides defaults, refresh with `Ctrl+F5` and use **Reset defaults**.

## Latest web and report materials

The web demo includes the SoCLaaS Interface at `/chat`, selectable gateway models, matching requirement/preference prompt cards, and optional Mathematics and Quantitative Finance minors. See [web/README.md](web/README.md) for setup and scope.

The latest [report PDF](web/research/report/CS3263_Project_Report.pdf), [LaTeX source and figures](web/research/report/), [presentation plan](web/research/presentation/video_script.md), and rating templates are under [web/research/](web/research/README.md). The report was also updated and compiled in the existing Overleaf project. Raw experiment histories, API responses, logs, generated archives, private rating keys, course teaching materials and local credentials are excluded from this repository. Replaying archived experiment outputs requires the separately retained appendix.

## Existing algorithm baseline

The root-level `planner/`, `CSP_Solver_Local/`, tests, snapshots and notebook are retained. Their original guide is preserved at **[docs/ALGORITHM_BASELINE.md](docs/ALGORITHM_BASELINE.md)**.

Run the fixed-course algorithm from the **repository root**, using the root `requirements.txt`:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m planner.run_foundation
python -m pytest -q
python -m planner.check_rules_against_nusmods
```

The web demo currently uses its bundled PyCSP3 adapter and does not invoke this separate fixed-course baseline. The integration seam for the algorithm team is `web/backend/solver_adapter.py::solve_plan(request)`; see [the web integration contract](web/docs/WEB_INTEGRATION.md).

## Planning and validation scope

The web demo uses a committed AY2026/27 snapshot, a default 160-unit target, real GE/ID/CD choices and semester-by-semester weekly feasibility checks. Invalid prerequisite/foundation results are preview-only and cannot be exported; the backend checks assignments again before producing NUSMods JSON.

A complete graduation audit, all preclusions and personal exceptions, internship/FYP eligibility, and year-long course modelling are still incomplete. Later years assume the reference-year offering and timetable patterns repeat. Read the respective guides before treating a generated result as a final academic decision.
