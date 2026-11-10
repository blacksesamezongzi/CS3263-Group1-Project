# CS3263 report, experiments and presentation materials

This directory contains the research deliverables for the current Pathway implementation. English is used for the report, narration and rating packet.

The GitHub version includes source code, final report assets and PDF, presentation plans, and rating templates. Raw experiment runs (`experiments/run-*/`), API outputs, logs, generated archives, private method keys and course materials remain local. The saved-run commands below require the separately retained experiment appendix; a fresh clone does not contain that history. Run commands from `web/` in the team repository.

## Deliverables

- `report/main.tex`, `report/body.tex`, the three requirement/rating tables and `report/figures/`: revised Overleaf-ready source. The compiled report has **9 numbered body pages**, plus a title page and one reference page. A4, 11-point, single column, single spacing, one-inch margins. Five figures include task/architecture diagrams and real product screenshots. Quantitative tables score necessary requirements individually; qualitative values are explicitly pending. The body includes contribution and AI-assistance statements. No substantive analysis is hidden in the raw-data appendix.
- `report/CS3263_Project_Report.pdf`: final PDF downloaded from the successfully compiled Overleaf project.
- `presentation/video_script.md`: nine-slide storyboard and English narration for a **9:20 target**, below the latest **10-minute video maximum**. Responsible AI stays in the report. This is a plan/script, not a recorded video or finished slide deck.
- `../output/pdf/presentation_video_plan.pdf`: printable storyboard.
- `../output/CS3263_rater_materials.zip`: the only package to give raters. It contains 15 anonymous schedules, explicit 1-5 anchors, blank forms and common reference data.
- `human-evaluation/PRIVATE_method_key_DO_NOT_SHARE.json`: keep this away from raters until both have finished.
- `../output/CS3263_experiment_appendix.zip`: separate supplementary appendix with exact prompts, successful raw responses, safe service-error records, checks, CSV summaries, frozen data and provenance.
- `../output/CS3263_report_overleaf.zip`: upload into the report Overleaf project and set `main.tex` as the main document. The latest source and figures were also uploaded directly to the [existing Overleaf report project](https://www.overleaf.com/project/6af1851e5c469ea8674182d0) and compiled successfully: 0 errors, 0 warnings, 11 total pages. The proposal project was not changed.

## Results and interpretation

The main matrix is 15 model IDs by three disclosure conditions, **45 calls**. These cover 13 canonical SoCLaaS chat models plus the exact requested `gpt-6-astra` and `gpt-6.1-sol`. Model aliases, embeddings and transcription models are excluded. Gateway `x-test-*` names and descriptions are retained as supplied; upstream identities/version pinning are not independently verified.

There are **14 evaluable main schedules**, **12 service/transport failures**, and **19 received but unparseable responses**, all 19 output-limited. Only one main schedule passes every implemented hard check. Zero proven failures with unknown weekly feasibility does not count as fully verified. The 3,500-token SoCLaaS budget, compressed long context, and different frontier CLI harness substantially limit model-level conclusions. This experiment does not establish that direct LLM planning is inherently incapable.

The three typed-card CSP controls all pass the same benchmark checker. Base: 160 units/8 semesters; Mathematics: 177/9; QF: 162/8. Mathematics misses duration and balance preferences; QF misses balance. These controls do not measure a model parser's accuracy. Two separate production-parser minor probes match the intended minor and soft pin semantics and subsequently solve; they are only smoke tests.

Eight original minor-extension calls and two documented Qwen Coder replacement calls bring direct-model requests to **55**. The 15-plan human packet uses five methods on three tasks. Llama 3.1 is replaced by Qwen Coder under the recorded availability policy. **No human ratings have been collected.** The method key, checker verdicts and quantitative result tables must not be shown to raters before scoring.

## Reproduction

Use the repository Python environment with its normal dependencies and Java 11+. Artifact generation additionally needs `reportlab`, `pypdf` and `matplotlib` only if generating extra plots. No extra dependency is required by the web application.

```bash
# Evaluate saved outputs without making API calls:
.venv/bin/python research/experiments/benchmark.py evaluate

# Regenerate report tables, PDF rating packet and PDF video plan:
.venv/bin/python research/experiments/build_materials.py

# Regenerate the revised requirement-specific report tables (no model calls):
.venv/bin/python research/report/build_requirement_tables.py

# Check the benchmark's crucial invalid/missing-output and prerequisite semantics:
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest research/experiments/test_benchmark.py -q

# Compile the LaTeX report (Overleaf also works):
mkdir -p output/pdf
tectonic -X compile research/report/main.tex --outdir output/pdf
```

`benchmark.py prepare` freezes inputs and provenance. **Do not run it over the archived run**: copy the script/run directory or change `RUN` to a new dated location for a new experiment. `models` makes real SoCLaaS and Codex requests, while `csp` invokes the bounded solver. Completed raw response files are never retried automatically. `parser_probe.py` makes separate production parser calls and stores the actual typed cards. Keep `.env` local; it is neither part of the experiment archive nor required to inspect results.

The manifest captures the base Git commit, dirty-tree status, backend source hashes and data hashes. This is deliberately more specific than claiming the dirty workspace is exactly the Git commit. `evaluation_provenance.json` separately hashes the evaluator/material builder. The appendix also freezes the relevant backend sources and data so the recorded implementation is reviewable.

## Human study

Give the rater ZIP to both teammates. Ask them to independently fill their R1 or R2 rows in `blank_ratings.csv` following the different recorded order. They may leave a score blank with an uncertainty explanation. They should not discuss answers until both finish. Keep the original submitted CSVs unchanged, merge copies and analyse paired differences only after collection. Ratings are internal developer judgements, not a representative student study. A favourable result is a hypothesis, never a required answer.

## Submission checks that remain human tasks

1. Review the factual wording, references, contribution statement and AI disclosure as the named authors.
2. Check the latest report in Overleaf before submission. The online update and clean compilation are complete; repeat compilation after any further edits.
3. Collect the two raters' actual independent scores and revise the explicitly pending human-results section if time permits.
4. Turn the storyboard into slides, rehearse, record the video and verify the exported duration is at most 10:00. The recording checklist and proposed speaker assignments are included in the plan.

The newest user-provided video requirement supersedes the older course-material timing. The report retains Responsible AI, limitations and the other required written elements.

The figure/compliance revision uses the same saved experiment responses. `output/archive/report-v1/` retains the earlier report. Product screenshots use an isolated Chrome profile and production HTML/CSS, replaying the actual saved base CSP response for the degree view. See `report/figures/screenshot_provenance.json`. Lucide icons use the bundled ISC licence. All figures are included in the revised Overleaf ZIP.
