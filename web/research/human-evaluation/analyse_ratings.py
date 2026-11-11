#!/usr/bin/env python3
"""Analyse the single-rater qualitative evaluation (report section 4.3).

Standard library only. Run it ONLY after the completed ratings have been locked
(hash sent to a teammate) and the private method key has been handed over.

Pass 1 (primary scores) uses the R1 rows/order of blank_ratings.csv.
Pass 2 (optional retest) uses the R2 rows/order and is used only for
intra-rater consistency, never for the headline table.

Example, from the web/ folder:
  python research/human-evaluation/analyse_ratings.py \
      --pass1 research/human-evaluation/ratings_pass1_R1.csv \
      --key   research/human-evaluation/PRIVATE_method_key_DO_NOT_SHARE.json \
      --pass2 research/human-evaluation/ratings_pass2_R2.csv   # optional
"""
import argparse
import csv
import json
import statistics
from pathlib import Path

DIMS = [('preference_1_5', 'Pref.'), ('feasibility_1_5', 'Feasib.'),
        ('workload_1_5', 'Progress'), ('clarity_1_5', 'Clarity'),
        ('overall_1_5', 'Overall')]
TASKS = {'base': 'Base', 'math': 'Mathematics minor', 'qf': 'QF minor'}


def display(method):
    m = method.lower()
    if m == 'csp':
        return 'Pathway CSP'
    if 'coder' in m:
        return 'Qwen Coder'
    if 'qwen' in m:
        return 'Qwen 3.6'
    if 'astra' in m:
        return 'Astra'
    if 'sol' in m:
        return 'Sol'
    return method


def load_key(path):
    key = json.loads(Path(path).read_text(encoding='utf-8'))
    plans = {p['anonymous_id']: {'method': p['method'], 'task': p['profile']} for p in key['plans']}
    methods = key.get('methods') or sorted({p['method'] for p in plans.values()})
    return plans, methods


def load_ratings(path, rater_id, plan_ids, label):
    rows, warnings = {}, []
    with open(path, newline='', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            if row.get('rater_id', '').strip() != rater_id:
                continue
            pid = row['plan_id'].strip()
            if pid not in plan_ids:
                warnings.append(f'{label}: unknown plan_id {pid}')
                continue
            if pid in rows:
                warnings.append(f'{label}: {pid} appears twice; keeping the first row')
                continue
            scores = {}
            for col, _ in DIMS:
                raw = (row.get(col) or '').strip()
                if raw == '':
                    scores[col] = None
                    if not (row.get('specific_concern') or '').strip():
                        warnings.append(f'{label}: {pid} {col} is blank without an explanation in specific_concern')
                    continue
                try:
                    v = int(raw)
                except ValueError:
                    v = None
                if v is None or not 1 <= v <= 5:
                    warnings.append(f'{label}: {pid} {col}={raw!r} is not an integer 1-5; treated as missing')
                    v = None
                scores[col] = v
            rows[pid] = {'order': row.get('order', ''), 'scores': scores,
                         'uncertainty': (row.get('uncertainty_low_medium_high') or '').strip().lower(),
                         'concern': (row.get('specific_concern') or '').strip(),
                         'recognised': (row.get('recognised_plan_yes_no') or '').strip().lower()}
    for pid in sorted(plan_ids - rows.keys()):
        warnings.append(f'{label}: no row for {pid} (rater {rater_id})')
    return rows, warnings


def fmt_num(x):
    return str(int(x)) if float(x).is_integer() else f'{x:.1f}'


def cell(values):
    v = [x for x in values if x is not None]
    if not v:
        return '--'
    return f'{fmt_num(statistics.median(v))} [{min(v)}, {max(v)}]'


def weighted_kappa(a, b, k=5):
    n = len(a)
    if n == 0:
        return None
    obs = [[0] * k for _ in range(k)]
    for x, y in zip(a, b):
        obs[x - 1][y - 1] += 1
    ra = [sum(r) for r in obs]
    cb = [sum(obs[i][j] for i in range(k)) for j in range(k)]
    w = [[(i - j) ** 2 / (k - 1) ** 2 for j in range(k)] for i in range(k)]
    num = sum(w[i][j] * obs[i][j] for i in range(k) for j in range(k))
    den = sum(w[i][j] * ra[i] * cb[j] / n for i in range(k) for j in range(k))
    return None if den == 0 else 1 - num / den


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--pass1', required=True, help='completed ratings CSV for the primary pass')
    ap.add_argument('--pass1-id', default='R1', help='rater_id rows used for pass 1 (default R1)')
    ap.add_argument('--pass2', help='optional retest CSV (may be the same file as --pass1)')
    ap.add_argument('--pass2-id', default='R2', help='rater_id rows used for pass 2 (default R2)')
    ap.add_argument('--key', required=True, help='PRIVATE_method_key_DO_NOT_SHARE.json')
    ap.add_argument('--out', default=None, help='output folder (default: results/ next to --pass1)')
    args = ap.parse_args()

    plans, methods = load_key(args.key)
    ids = set(plans)
    out = Path(args.out) if args.out else Path(args.pass1).resolve().parent / 'results'
    out.mkdir(parents=True, exist_ok=True)

    p1, warn = load_ratings(args.pass1, args.pass1_id, ids, 'pass1')
    p2 = None
    if args.pass2:
        p2, w2 = load_ratings(args.pass2, args.pass2_id, ids, 'pass2')
        warn += w2

    # 1. Unblinded per-plan file
    with (out / 'merged_pass1.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['plan_id', 'method', 'task', 'order'] + [c for c, _ in DIMS] + ['uncertainty', 'recognised', 'specific_concern'])
        for pid in sorted(ids):
            r = p1.get(pid)
            w.writerow([pid, display(plans[pid]['method']), plans[pid]['task'], r['order'] if r else '']
                       + [(r['scores'][c] if r and r['scores'][c] is not None else '') for c, _ in DIMS]
                       + [r['uncertainty'] if r else '', r['recognised'] if r else '', r['concern'] if r else ''])

    def score(pid, col, source=p1):
        r = source.get(pid)
        return None if r is None else r['scores'][col]

    by = {(plans[p]['method'], plans[p]['task']): p for p in ids}
    tasks = [t for t in TASKS if any(k[1] == t for k in by)]
    md = ['# Qualitative evaluation results (single rater)', '']
    if warn:
        md += ['## Data warnings', ''] + [f'- {x}' for x in warn] + ['']

    # 2. Headline table: median [min, max] over tasks, pass 1 only
    md += ['## Table 4 values: median [min, max] over the three tasks (pass 1)', '',
           '| Method | n | ' + ' | '.join(l for _, l in DIMS) + ' |', '|' + '---|' * (len(DIMS) + 2)]
    tex_rows = []
    for m in methods:
        pids = [by[(m, t)] for t in tasks if (m, t) in by]
        complete = sum(all(score(p, c) is not None for c, _ in DIMS) for p in pids)
        cells = [cell([score(p, c) for p in pids]) for c, _ in DIMS]
        md.append(f'| {display(m)} | {complete}/{len(pids)} | ' + ' | '.join(cells) + ' |')
        tex_rows.append(f'{display(m)} & {complete}/{len(pids)} & ' + ' & '.join(cells) + ' \\\\')
    md.append('')

    # 3. Per-task raw scores
    md += ['## Per-task scores (pass 1; blank = rater left it blank)', '',
           '| Method | Task | ' + ' | '.join(l for _, l in DIMS) + ' | Uncertainty | Recognised |',
           '|' + '---|' * (len(DIMS) + 4)]
    for m in methods:
        for t in tasks:
            p = by.get((m, t))
            if p is None:
                continue
            r = p1.get(p, {})
            md.append(f'| {display(m)} | {TASKS[t]} | ' + ' | '.join('' if score(p, c) is None else str(score(p, c)) for c, _ in DIMS)
                      + f" | {r.get('uncertainty', '')} | {r.get('recognised', '')} |")
    md.append('')

    # 4. Within-task paired differences against CSP
    csp = next((m for m in methods if m.lower() == 'csp'), None)
    if csp:
        md += ['## Within-task differences vs Pathway CSP (method minus CSP; + favours the LLM)', '',
               'Each cell lists Base, Mathematics, QF differences, then wins/ties/losses for the LLM. `?` = a score is missing.', '',
               '| Method | ' + ' | '.join(l for _, l in DIMS) + ' |', '|' + '---|' * (len(DIMS) + 1)]
        for m in methods:
            if m == csp:
                continue
            cells = []
            for c, _ in DIMS:
                diffs = []
                for t in tasks:
                    a, b = by.get((m, t)), by.get((csp, t))
                    x = score(a, c) if a else None
                    y = score(b, c) if b else None
                    diffs.append(None if x is None or y is None else x - y)
                d = [x for x in diffs if x is not None]
                wtl = f'{sum(x > 0 for x in d)}/{sum(x == 0 for x in d)}/{sum(x < 0 for x in d)}'
                cells.append(', '.join('?' if x is None else f'{x:+d}' for x in diffs) + f' ({wtl})')
            md.append(f'| {display(m)} | ' + ' | '.join(cells) + ' |')
        md.append('')

    # 5. Recognition and uncertainty
    rec = [p for p in ids if p1.get(p, {}).get('recognised', '').startswith('y')]
    md += ['## Blinding check', '',
           f'- Plans marked as recognised: {len(rec)}/{len(ids)}'
           + (' (' + ', '.join(f'{p} = {display(plans[p]["method"])}/{plans[p]["task"]}' for p in sorted(rec)) + ')' if rec else ''),
           '- Uncertainty counts: ' + ', '.join(f'{k or "blank"} {sum(p1.get(p, {}).get("uncertainty", "") == k for p in ids)}'
                                              for k in ['low', 'medium', 'high', '']), '']

    # 6. Optional test-retest agreement
    if p2:
        md += ['## Intra-rater consistency (pass 1 vs pass 2)', '',
               '| Dimension | Pairs | Exact | Within 1 | Mean abs. diff | Quadratic weighted kappa |', '|---|---|---|---|---|---|']
        allx, ally = [], []
        for c, label in DIMS:
            pairs = [(score(p, c), score(p, c, p2)) for p in ids]
            pairs = [(x, y) for x, y in pairs if x is not None and y is not None]
            allx += [x for x, _ in pairs]
            ally += [y for _, y in pairs]
            if not pairs:
                md.append(f'| {label} | 0 | -- | -- | -- | -- |')
                continue
            k = weighted_kappa([x for x, _ in pairs], [y for _, y in pairs])
            md.append(f'| {label} | {len(pairs)} | {sum(x == y for x, y in pairs) / len(pairs):.0%} | '
                      f'{sum(abs(x - y) <= 1 for x, y in pairs) / len(pairs):.0%} | '
                      f'{statistics.mean(abs(x - y) for x, y in pairs):.2f} | {"undefined" if k is None else f"{k:.2f}"} |')
        if allx:
            k = weighted_kappa(allx, ally)
            md.append(f'| All dimensions | {len(allx)} | {sum(x == y for x, y in zip(allx, ally)) / len(allx):.0%} | '
                      f'{sum(abs(x - y) <= 1 for x, y in zip(allx, ally)) / len(allx):.0%} | '
                      f'{statistics.mean(abs(x - y) for x, y in zip(allx, ally)):.2f} | {"undefined" if k is None else f"{k:.2f}"} |')
        md += ['', 'Pass 2 is a retest by the same person after a short interval; memory of pass 1 inflates agreement.', '']

    (out / 'summary.md').write_text('\n'.join(md) + '\n', encoding='utf-8')

    # 7. Drop-in replacement for research/report/qualitative_results.tex
    n_tasks = len(tasks)
    tex = ['\\begin{table}[htbp]\\centering', '\\begin{tabular}{@{}lcccccc@{}}\\toprule',
           'Method & $n$ & Pref. & Feasib. & Progress & Clarity & Overall\\\\\\midrule', *tex_rows,
           '\\bottomrule\\end{tabular}',
           '\\caption{Single-rater qualitative scores on the anchored 1--5 scale (higher is better). '
           f'Each method has {n_tasks} task plans rated once by one developer under blinding; $n$ counts plans with all five scores. '
           'Cells give median [minimum, maximum] across tasks. Scores are internal judgements, not a student study.}\\label{tab:qualitative}',
           '\\end{table}']
    (out / 'qualitative_results.tex').write_text('\n'.join(tex) + '\n', encoding='utf-8')

    print((out / 'summary.md').read_text(encoding='utf-8'))
    print(f'Wrote {out / "merged_pass1.csv"}, {out / "summary.md"} and {out / "qualitative_results.tex"}')


if __name__ == '__main__':
    main()
