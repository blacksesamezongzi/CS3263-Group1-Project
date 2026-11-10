"""Build reviewable archives without credentials, internal CLI logs or rater leaks."""
from pathlib import Path
import hashlib
import html
import json
import platform
import shutil
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'research/experiments/run-2026-11-09'
OUT=ROOT/'output'
PDF=OUT/'pdf'
def zip_files(path,files):
 with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  for src,name in files:
   assert src.is_file(),src
   assert src.name!='.env'
   z.write(src,name)
 assert zipfile.ZipFile(path).testzip() is None

shutil.copy2(PDF/'main.pdf',PDF/'CS3263_Project_Report.pdf')
versions={'python':sys.version,'platform':platform.platform(),'machine':platform.machine(),
 'codex_cli':subprocess.check_output(['codex','--version'],text=True).strip(),
 'java':subprocess.run(['java','-version'],capture_output=True,text=True).stderr.strip(),
 'pycsp3':(ROOT/'pycsp3/version.txt').read_text().strip(),'ace_jar':'ACE-2.6.jar',
 'execution_note':'Up to 3 concurrent SoCLaaS requests and 2 concurrent frontier CLI requests; CSP controls sequentially, overlapping remote model collection. Latencies are not isolated performance measurements.'}
(RUN/'runtime_versions.json').write_text(json.dumps(versions,indent=2)+'\n')
summary=json.loads((RUN/'summary.json').read_text())
appendix=RUN/'appendix';appendix.mkdir(exist_ok=True)
intro='''# Supplementary Appendix A: frozen experiment records

This supplementary appendix contains raw research material, separate from the report body (limited to ten pages). It is not used to hide discussion, tables or substantive analysis from the page limit.

The main matrix contains 45 calls: 15 model IDs x A/AP/APR on the base task. Eight original minor extension calls plus two documented replacement calls give 55 direct-model requests. The parser probes and three typed-card CSP controls are separate.

- `inputs/`: exact nine user prompts. Every prompt embeds the same frozen compact reference data.
- `context.json`: the shared reference catalogue, complete teaching-package alternatives, exams and curriculum pools.
- `requests/`: exact SoCLaaS JSON payloads, or CLI command/standard-input record. No Authorization headers or credentials are included.
- `raw/`: exact successful SoCLaaS response objects and frontier final answers/usage. Error bodies are withheld because gateways can expose private routing details; status, elapsed time and exception category are retained. No missing answer is fabricated.
- `evaluated/` and `results.json`: deterministic checker output and atomic diagnostics.
- `summary.json`, `model_summary.csv`, `violation_incidence.csv`, `atomic_diagnostics.csv`: aggregation with explicit denominators.
- `requirement_compliance.csv`/`.json`: revised requirement-specific metrics from the same real plans. Prerequisite-course failures, missing foundation courses, minimum-unit deficits and curriculum checks are separate from timetable checks.
- `requirement_coverage.json`: all attempted model IDs and which returned an evaluable APR plan.
- `csp/` and `csp-evaluated/`: actual solver outputs and the same benchmark checker applied to those assignments.
- `parser/`: production-parser requests/responses, generated cards, semantic comparisons and subsequent solve results.
- `manifest.json`: freeze time, prompt settings, model IDs, versioned protocol, source/data hashes and dirty-worktree disclosure.
- `models.json`: model metadata returned by the gateway. Test labels and descriptions are gateway claims, not independently verified upstream identities.
- `evaluation_provenance.json` and `runtime_versions.json`: evaluator hashes and execution environment.
- `code_snapshot/` and `data_snapshot/`: the backend/compiler/checker source and raw course data used by this run. The project repository supplies the bundled PyCSP3/ACE runtime.

Read `index.html` locally for links to the individual prompts and outputs. A question mark in a result means an unresolved hard check. P means received but unparseable, E means transport/service failure. All 19 unparseable main responses reached the 3500-token output limit. These are not 19 proved invalid schedules. CLI baselines use a different hidden harness and output allowance and cannot be treated as identical API settings.

Human-rating materials and the private method key are excluded from this appendix. No human scores have been collected.
'''
(appendix/'README.md').write_text(intro)
rows=[]
for row in summary['models']:
 rows.append('<tr><td>'+html.escape(row['model'])+'</td>'+''.join('<td>'+html.escape(c)+'</td>' for c in row['cells'])+f"<td>{row['evaluable']}/3</td><td>{row['verified']}/3</td></tr>")
links=[]
for p in sorted((RUN/'raw').glob('*.json')):
 r=json.loads(p.read_text());links.append('<li>'+html.escape(f"{r['model']} / {r['profile']} / {r['level']}")+f' <a href="raw/{p.name}">raw output</a> <a href="requests/{p.name}">request</a> <a href="evaluated/{p.name}">checks</a></li>')
page='''<!doctype html><html lang="en"><meta charset="utf-8"><title>CS3263 Supplementary Appendix A</title><style>body{font:16px/1.55 system-ui;max-width:1100px;margin:48px auto;padding:0 24px;color:#17344e}table{border-collapse:collapse;width:100%}td,th{padding:8px;border-bottom:1px solid #ccd7e1;text-align:left}h1,h2{color:#103d67}a{color:#005ea8}</style><h1>Supplementary Appendix A</h1><p>Frozen prompts, actual responses, and checks. No API credentials. Human scores have not been collected. Read <a href="README.md">the archive guide</a> and <a href="manifest.json">protocol manifest</a>.</p><h2>Necessary-requirement compliance</h2><p>The revised report separates prerequisite-course failures, missing foundation courses, unit deficits and curriculum-group checks. Download <a href="requirement_compliance.csv">the metric CSV</a> or inspect <a href="requirement_compliance.json">the JSON</a>. The model/response coverage remains available below.</p><h2>Original coverage matrix</h2><p>Hard-card failures. ? = an unverified hard check, P = unparseable response, E = transport/service failure. All 19 unparseable main responses reached the output cap. Errors are not zero-violation plans. Frontier CLI settings differ from SoCLaaS API settings.</p><table><tr><th>Model ID</th><th>A</th><th>AP</th><th>APR</th><th>Evaluable</th><th>Fully verified</th></tr>'''+''.join(rows)+'</table><h2>Exact inputs</h2><ul>'+''.join(f'<li><a href="inputs/{p.name}">{p.name}</a></li>' for p in sorted((RUN/'inputs').glob('*.txt')))+'</ul><h2>Individual outputs</h2><ul>'+''.join(links)+'</ul></html>'
(appendix/'index.html').write_text(page)

report_files=[(ROOT/'research/report'/n,n) for n in ['main.tex','body.tex','academic_results.tex','temporal_results.tex','qualitative_results.tex','README_OVERLEAF.md','capture_product.mjs','build_figures.py','render_diagrams.mjs','build_requirement_tables.py']]
report_files += [(p,'figures/'+p.name) for p in sorted((ROOT/'research/report/figures').iterdir()) if p.is_file()]
report_files.append((PDF/'CS3263_Project_Report.pdf','CS3263_Project_Report.pdf'))
zip_files(OUT/'CS3263_report_overleaf.zip',report_files)

rater_files=[(PDF/'human_evaluation_packet.pdf','human_evaluation_packet.pdf')]
for n in ['README_FOR_RATERS.md','blank_ratings.csv','course_reference.csv','task_supplement.json']:
 rater_files.append((ROOT/'research/human-evaluation'/n,n))
rater_files.append((RUN/'context.json','context.json'))
zip_files(OUT/'CS3263_rater_materials.zip',rater_files)

files=[]
for p in sorted(RUN.rglob('*')):
 if not p.is_file() or p.suffix=='.log' or 'codex' in p.relative_to(RUN).parts:continue
 if 'appendix' in p.relative_to(RUN).parts:continue
 files.append((p,str(p.relative_to(RUN))))
files += [(appendix/'README.md','README.md'),(appendix/'index.html','index.html')]
files += [(p,'code_snapshot/backend/'+p.name) for p in sorted((ROOT/'backend').glob('*.py'))]
files += [(p,'data_snapshot/'+p.name) for p in sorted((ROOT/'assets/data').glob('*course_details.json'))]
files += [(ROOT/'src/courses.py','code_snapshot/src/courses.py')]
files += [(p,'scripts/'+p.name) for p in sorted((ROOT/'research/experiments').glob('*.py'))]
files += [(ROOT/'research/report/build_requirement_tables.py','scripts/build_requirement_tables.py')]
zip_files(OUT/'CS3263_experiment_appendix.zip',files)

bundle=[(OUT/n,n) for n in ['CS3263_report_overleaf.zip','CS3263_rater_materials.zip','CS3263_experiment_appendix.zip']]
bundle += [(ROOT/'research/README.md','START_HERE.md'),(PDF/'CS3263_Project_Report.pdf','CS3263_Project_Report.pdf'),(PDF/'presentation_video_plan.pdf','presentation_video_plan.pdf'),(ROOT/'research/presentation/video_script.md','presentation/video_script.md'),(ROOT/'research/presentation/video_plan.json','presentation/video_plan.json'),(ROOT/'research/human-evaluation/PRIVATE_method_key_DO_NOT_SHARE.json','ORGANISER_ONLY/PRIVATE_method_key_DO_NOT_SHARE.json')]
zip_files(OUT/'CS3263_research_deliverables.zip',bundle)
for p in OUT.glob('CS3263*.zip'):print(p.name,p.stat().st_size,'bytes',hashlib.sha256(p.read_bytes()).hexdigest()[:16])
