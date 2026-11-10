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

### SoCLaaS Interface

Open **http://127.0.0.1:8000/chat**, or choose **Model chat** in the planner navigation. The standalone interface uses the existing backend `.env` key. Its initial model is `SOCLAAS_MODEL`, the same model used by Pathway.

Click the **model name at the top** to search and select any model returned by the gateway for your key. Selection immediately changes the model ID sent with subsequent requests; it does not edit `.env` or change the planner's model. There is no fallback to Qwen if another model fails. Each reply and exported run records the selected model and the model ID reported by the gateway.

- **LLM / VLM:** streamed conversations through `/v1/chat/completions`. VLM models accept PNG/JPEG/WebP/GIF uploads or pasted images using the **＋** button. Chat generation shares Pathway's temperature **0** and maximum output tokens **3500**.
- **Embeddings:** text goes to `/v1/embeddings`; the returned vectors appear as JSON. This operates on the current input, without conversation history.
- **Audio:** attach one supported audio file to call `/v1/audio/transcriptions`, for example with Whisper. This operates on the current audio file. Files are limited to 6 MB each and the current attachment total to 6 MB.

Model capabilities and aliases come from the live `/v1/models` list rather than a hard-coded menu. **Refresh** reloads that list. The **Same model as Pathway** caption appears only when the selected model (or its declared alias) matches the planner model. API/model failures are displayed explicitly.

Being listed indicates access and capabilities, not live backend health. A model can remain listed while returning **HTTP 503 / no healthy provider backends**. This means its SoCLaaS service is unavailable; wait and retry or explicitly choose another model. The interface distinguishes authentication, access, rate-limit and service errors, records the HTTP status in exported failed runs, and never silently switches models or retries an experiment.

The interface supports multiple conversations, stop/retry, regeneration, response copying and JSON export. Conversations and attachments are saved in this browser under a separate key from the planner draft. The backend forwards them to SoCLaaS and does not save chat files to disk. Large attachments may exceed browser storage; export important runs. Partial/failed replies are excluded from future model context. Embedding/transcription output is also excluded from later chat context.

The simplified UI has no settings panel or system-prompt editor. Requests contain your messages and attachments, with **no injected system prompt, catalogue, constraint cards, CSP, retrieval or automatic academic checks**. Older saved chats with a custom system prompt remain visible/exportable, but require a new chat before sending more messages, so old instructions cannot silently affect a run.

The welcome page offers **14 Requirements and 2 Preferences prompt cards** drawn from the same `default_cards()` definition as the planner. Choose a card to append its text to the editable draft, or use **Add all defaults** to insert the full set. Expand **Show all requirements** to browse every card. Nothing is sent automatically: you can edit the draft before sending. The foundation prompt includes the complete required-course list. Cards are available for chat/VLM models; embeddings and transcription keep their own input modes. Start a **New chat** to return to the prompt library.

### Optional minors: Mathematics and Quantitative Finance

In **My study plan → Make room for a minor**, choose **Add minor** for Mathematics or Quantitative Finance, or **Use a prompt** to discuss it with the assistant. The manual constraint editor also supports **Complete a minor**. Selected programmes appear in a separate **Minors** tab as hard constraints; removing a card removes that programme from subsequent searches. Neither minor is enabled by default.

The templates follow the Department of Mathematics' **AY2021/22-onwards** tables: [Mathematics](https://www.math.nus.edu.sg/ug/majmin/minors/mamin/) and [Quantitative Finance](https://www.math.nus.edu.sg/ug/majmin/minors/qfmin/). The CSP allocates distinct courses to the programme's groups, checks at least 20 units, at least 12 distinct units outside the CS-major/other-selected-minor pools, and a maximum of 8 units shared with other programmes. A course cannot be counted towards three programme requirements. Degree units are counted only once. The reference-year QF template uses Option B because MA2301 ceased being offered from AY2025/26.

Generated plans show a separate minor summary with each group's courses, distinct/shared units and official source links. Both minors can be selected together. An independent checker verifies their allocations, and the JSON export endpoint checks the chosen minors again before download. Prerequisite order, explicit course preclusions, semester offerings, exams and weekly class selection participate in the search. The H2 Mathematics profile waives a course's entry condition when its only course prerequisites are MA1301/MA1301X; it never marks a university course as already completed.

The **SoCLaaS Interface** also has a **Minors** prompt category with the same programme definitions. **Add all defaults** continues to add only the 16 base requirement/preference cards; choosing a minor is explicit. Prompt cards insert editable text and do not run the CSP.

The original course snapshot is retained, with **57 additional real AY2026/27 courses** and supporting prerequisite options in `assets/data/minor_course_details.json` (338 courses in total). Search the catalogue by **Math minor** or **QF minor**. Maintainers can refresh this supplemental snapshot with `.venv/bin/python scripts/refresh_minor_catalogue.py`; restart the backend afterward. Inactive minor supplements do not expand the default solver's elective pool.

Students must still declare a minor in EduRec before semester 5. The planner assumes NUS-earned course credits and does not perform declaration, assess personal exemptions/second-major eligibility, or implement every programme/grade-based CourseReg restriction. The primary-major pool is the app's prescribed CS foundation set; this remains a planning aid rather than a complete graduation certification.

For each comparison, start a new chat, select Pathway's model, and supply the same task, course-data snapshot and student assumptions. **Export chat** saves the exact requests, responses, selected/returned model IDs, parameters, timestamps, response times, finish reason and token usage when supplied by the gateway. Switching models within a chat is allowed and is recorded per response; use separate chats when comparing independent runs. Export before regenerating if you want to keep both attempts.

Assess raw-model and planner outputs with the same independent prerequisite, graduation and timetable criteria. A shared model does not by itself control prompt/context differences or the planner's solver/tool access. Temperature 0 does not guarantee identical repeated responses. Credentials remain on the backend and are never included in exported metadata.

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

Direct-model chat (/chat) → same SoCLaaS model → raw streamed response
```

The integration seam is **`backend/solver_adapter.py::solve_plan(request)`**. Its assignments map course codes to overall semesters: `1 = Y1S1`, `3 = Y2S1`, and `0 = not selected`. The web app currently uses its own bundled PyCSP3 adapter; it does **not** call the separate root-level `planner.run_foundation` baseline. Algorithm teammates can replace the adapter while keeping the versioned API. See [WEB_INTEGRATION.md](docs/WEB_INTEGRATION.md) and `/docs` for the exact schema and validation requirements.

### Run tests from `web/`

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q tests/test_api.py tests/test_chat.py tests/test_minors.py
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

- The default standard-CS target is 160 units. The bundled AY2026/27 catalogue has 338 real courses: the original 281-course CS/GE/ID/CD pool plus 57 minor/prerequisite courses. Graduate-level and year-long GEN variants may be browse-only.
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
