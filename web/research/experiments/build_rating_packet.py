"""Regenerate the blind 15-plan rating packet (report section 4.3) from scratch.

Use this when the archived run (research/experiments/run-2026-11-09/) and
output/CS3263_rater_materials.zip are not available. It makes NEW model calls,
so the plans are a fresh draw, not the responses scored in Tables 2-3.

Stages, run from the web/ folder:
  python research/experiments/build_rating_packet.py prepare          # offline: freeze prompts + context
  python research/experiments/build_rating_packet.py models           # needs SoCLaaS access (+ Codex CLI for Astra/Sol)
  python research/experiments/build_rating_packet.py csp --profile base   # needs Java 11+ (repeat for math, qf)
  python research/experiments/build_rating_packet.py packet           # needs reportlab
  python research/experiments/build_rating_packet.py status

Blinding: nothing printed here reveals plan contents or which plan is which.
Do not open the run folder, output/pdf/ beyond the packet, or the method key
until your ratings are finished and hashed.
"""
import argparse
import asyncio
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import research.experiments.benchmark as bm  # noqa: E402  (loads web/.env)

RUN = ROOT / 'research/experiments/run-qual-regenerated'
HUMAN = ROOT / 'research/human-evaluation'
OUT = ROOT / 'output'
PROFILES = ['base', 'math', 'qf']
LEVEL = 'APR'
SOCLAAS_MODELS = ['qwen3.6:35b', 'qwen3-coder-next']   # Qwen Coder replaces Llama, as recorded on 9 Nov
CODEX_MODELS = ['gpt-6-astra', 'gpt-6.1-sol']
bm.RUN = RUN


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def parseable(path):
    try:
        bm.parse_output(json.loads(path.read_text(encoding='utf-8')))
        return True
    except Exception:
        return False


def attempts_used(name):
    return len(list((RUN / 'attempts').glob(f'{name}__attempt*.json')))


def archive_failed(name):
    raw = RUN / 'raw' / f'{name}.json'
    n = attempts_used(name) + 1
    dest = RUN / 'attempts' / f'{name}__attempt{n}.json'
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(raw), str(dest))
    return n


# ---------------------------------------------------------------- prepare
def prepare():
    if (RUN / 'manifest.json').exists():
        print('Already prepared:', RUN.relative_to(ROOT), '(delete the folder to start over)')
        return
    RUN.mkdir(parents=True, exist_ok=True)
    context = json.dumps(bm.compact_catalogue(), separators=(',', ':'))
    (RUN / 'context.json').write_text(context, encoding='utf-8')
    for p in PROFILES:
        dump(RUN / 'tasks' / f'{p}.json', bm.request_for(p).model_dump())
        (RUN / 'inputs').mkdir(exist_ok=True)
        (RUN / 'inputs' / f'{p}-{LEVEL}.txt').write_bytes(bm.prompt(p, LEVEL, context).encode('utf-8'))

    def git(*a):
        try:
            return subprocess.check_output(['git', *a], cwd=ROOT, text=True).strip()
        except Exception:
            return None
    dump(RUN / 'manifest.json', {
        'frozen_at': datetime.now(timezone.utc).isoformat(),
        'protocol': 'v1-regenerated-human-packet',
        'purpose': 'Fresh APR plans for the blind qualitative packet; archived 9 Nov responses were unavailable to the rater.',
        'models_soclaas': SOCLAAS_MODELS, 'models_codex': CODEX_MODELS,
        'substitution': 'llama3.1:8b is not requested; Qwen Coder (qwen3-coder-next) replaces it as recorded on 9 Nov.',
        'temperature_soclaas': 0, 'max_tokens_soclaas': 3500, 'timeout_seconds_soclaas': 180,
        'codex_harness': 'codex exec --ignore-user-config --ignore-rules --ephemeral, read-only empty directory, medium reasoning, 300 s timeout',
        'attempt_policy': 'Up to --max-attempts calls per cell; the first parseable response is used; failed attempts kept in attempts/.',
        'context_sha256': hashlib.sha256(context.encode()).hexdigest(),
        'prompt_sha256': {p: sha(RUN / 'inputs' / f'{p}-{LEVEL}.txt') for p in PROFILES},
        'git_head': git('rev-parse', 'HEAD'), 'working_tree_dirty': bool(git('status', '--porcelain')),
        'source_sha256': {str(p.relative_to(ROOT)): sha(p) for p in sorted((ROOT / 'backend').glob('*.py'))},
        'data_sha256': {str(p.relative_to(ROOT)): sha(p) for p in sorted((ROOT / 'assets/data').glob('*course_details.json'))},
    })
    print('Prepared', RUN.relative_to(ROOT), '- context bytes', len(context))


# ---------------------------------------------------------------- models
def codex_once(model, profile, exe):
    name = bm.stem(model, profile, LEVEL)
    target = RUN / 'raw' / f'{name}.json'
    directory = RUN / 'codex' / name
    empty = directory / 'empty'
    empty.mkdir(parents=True, exist_ok=True)
    out = directory / 'answer.txt'
    if out.exists():
        out.unlink()
    prompt_path = RUN / 'inputs' / f'{profile}-{LEVEL}.txt'
    command = [exe, 'exec', '--ignore-user-config', '--ignore-rules', '--ephemeral', '--skip-git-repo-check',
               '-s', 'read-only', '-C', str(empty), '-m', model, '-c', 'model_reasoning_effort=medium',
               '--json', '-o', str(out), '-']
    dump(RUN / 'requests' / f'{name}.json', {'command': [Path(command[0]).name] + command[1:],
                                              'stdin_file': str(prompt_path.relative_to(RUN))})
    r = {'model': model, 'profile': profile, 'level': LEVEL, 'provider': 'codex-cli',
         'started_at': datetime.now(timezone.utc).isoformat()}
    started = time.monotonic()
    try:
        proc = subprocess.run(command, input=prompt_path.read_bytes(), capture_output=True, timeout=300)
        (directory / 'events.jsonl').write_bytes(proc.stdout)
        events = []
        for line in proc.stdout.decode('utf-8', 'replace').splitlines():
            if line.startswith('{'):
                try:
                    events.append(json.loads(line))
                except ValueError:
                    pass
        items = [e.get('item', {}) for e in events if e.get('type') == 'item.completed']
        tools = [i for i in items if i.get('type') not in {'agent_message', 'reasoning'}]
        ok = proc.returncode == 0 and out.exists() and not tools
        r.update(status='received' if ok else 'harness_error', returncode=proc.returncode,
                 tool_item_types=[i.get('type') for i in tools],
                 content=out.read_text(encoding='utf-8') if out.exists() else '',
                 usage=next((e.get('usage') for e in events if e.get('type') == 'turn.completed'), None))
        if not ok:
            tail = proc.stderr.decode('utf-8', 'replace').strip()[-300:]
            print(f'  {name}: codex exit {proc.returncode}; stderr tail: {tail}', flush=True)
    except subprocess.TimeoutExpired:
        r.update(status='timeout')
    except FileNotFoundError:
        r.update(status='harness_error', error='codex executable not found')
    r['elapsed_seconds'] = round(time.monotonic() - started, 3)
    dump(target, r)
    print(name, r['status'], r['elapsed_seconds'], flush=True)


async def cell(model, profile, provider, max_attempts, soc_sem, cod_sem, exe):
    name = bm.stem(model, profile, LEVEL)
    raw = RUN / 'raw' / f'{name}.json'
    while True:
        if raw.exists():
            if parseable(raw):
                print(f'OK   {name} (attempt {attempts_used(name) + 1})', flush=True)
                return True
            n = archive_failed(name)
            print(f'FAIL {name} attempt {n}: not a parseable schedule', flush=True)
        if attempts_used(name) >= max_attempts:
            print(f'GAVE UP {name} after {max_attempts} attempts', flush=True)
            return False
        if provider == 'soclaas':
            await bm.soc_run(model, profile, LEVEL, soc_sem)
        else:
            async with cod_sem:
                await asyncio.to_thread(codex_once, model, profile, exe)


async def run_models(args):
    if not (RUN / 'manifest.json').exists():
        sys.exit('Run the prepare stage first.')
    exe = None
    if not args.skip_codex:
        exe = shutil.which('codex')
        if not exe:
            sys.exit('Codex CLI not found on PATH. Install/log in to it, or rerun with --skip-codex (Astra/Sol plans will be missing).')
    if not args.skip_soclaas and not os.environ.get('SOCLAAS_API_KEY'):
        sys.exit('SOCLAAS_API_KEY is not set (web/.env).')
    soc_sem, cod_sem = asyncio.Semaphore(3), asyncio.Semaphore(2)
    jobs = []
    for p in PROFILES:
        if not args.skip_soclaas:
            jobs += [cell(m, p, 'soclaas', args.max_attempts, soc_sem, cod_sem, exe) for m in SOCLAAS_MODELS]
        if not args.skip_codex:
            jobs += [cell(m, p, 'codex', args.max_attempts, soc_sem, cod_sem, exe) for m in CODEX_MODELS]
    done = await asyncio.gather(*jobs)
    print(f'{sum(done)}/{len(done)} model cells have a parseable plan.')


# ---------------------------------------------------------------- csp
def run_csp(profiles):
    from backend.solver import generate_plan
    for p in profiles:
        path = RUN / 'csp' / f'{p}.json'
        if path.exists() and json.loads(path.read_text(encoding='utf-8')).get('status') == 'feasible':
            print('CSP', p, 'already feasible')
            continue
        started = time.monotonic()
        result = generate_plan(bm.request_for(p))
        dump(path, result)
        print('CSP', p, result.get('status'), f'{time.monotonic() - started:.0f}s', flush=True)


# ---------------------------------------------------------------- packet
def light_results():
    results = []
    for path in sorted((RUN / 'raw').glob('*.json')):
        raw = json.loads(path.read_text(encoding='utf-8'))
        try:
            assignments, _, _ = bm.parse_output(raw)
            results.append({'model': raw['model'], 'profile': raw['profile'], 'level': raw['level'],
                            'evaluable': True, 'assignments': assignments})
        except Exception:
            results.append({'model': raw.get('model'), 'profile': raw.get('profile'), 'level': raw.get('level'), 'evaluable': False})
    return results


def build_packet():
    for p in PROFILES:
        path = RUN / 'csp' / f'{p}.json'
        if not path.exists() or json.loads(path.read_text(encoding='utf-8')).get('status') != 'feasible' \
                or not json.loads(path.read_text(encoding='utf-8')).get('semesters'):
            sys.exit(f'CSP control for {p} is missing or not feasible; run the csp stage first.')
    if not Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf').exists():
        # Windows/macOS: build_materials hard-codes a Linux DejaVu path; use reportlab's bundled Vera fonts instead.
        import reportlab
        import reportlab.pdfbase.ttfonts as tt
        fonts = Path(reportlab.__file__).parent / 'fonts'

        class VeraFallback(tt.TTFont):
            def __init__(self, name, filename, *a, **k):
                if 'DejaVu' in str(filename):
                    filename = str(fonts / ('VeraBd.ttf' if 'Bold' in str(filename) else 'Vera.ttf'))
                super().__init__(name, filename, *a, **k)
        tt.TTFont = VeraFallback
    import research.experiments.build_materials as bmat   # needs reportlab
    bmat.RUN = RUN
    selected, replacements = bmat.build_human(light_results())
    key_path = HUMAN / 'PRIVATE_method_key_DO_NOT_SHARE.json'
    key = json.loads(key_path.read_text(encoding='utf-8'))
    for r in key['replacements']:
        if r['original'] == 'llama3.1:8b':
            r['reason'] = 'Carried over from the 9 Nov availability rule (Llama returned no evaluable plans); Llama was not re-requested.'
    failed = {}
    for m in SOCLAAS_MODELS + CODEX_MODELS:
        for p in PROFILES:
            name = bm.stem(m, p, LEVEL)
            failed[name] = attempts_used(name)
    key['regenerated'] = {'run': str(RUN.relative_to(ROOT)), 'built_at': datetime.now(timezone.utc).isoformat(),
                          'failed_attempts_before_used_plan': failed}
    dump(key_path, key)
    packet = OUT / 'pdf' / 'human_evaluation_packet.pdf'
    rater_zip = OUT / 'CS3263_rater_materials.zip'
    files = [(packet, 'human_evaluation_packet.pdf')] + \
            [(HUMAN / n, n) for n in ['README_FOR_RATERS.md', 'blank_ratings.csv', 'course_reference.csv', 'task_supplement.json']] + \
            [(RUN / 'context.json', 'context.json')]
    with zipfile.ZipFile(rater_zip, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for src, arc in files:
            z.write(src, arc)
    seal = OUT / 'SEALED_hashes.txt'
    lines = [f'Sealed {datetime.now(timezone.utc).isoformat()}',
             f'plans_in_packet {len(selected)}',
             f'sha256 method_key {sha(key_path)}',
             f'sha256 packet_pdf {sha(packet)}',
             f'sha256 rater_zip  {sha(rater_zip)}']
    seal.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('\n'.join(lines))
    print(f'\nRater ZIP: {rater_zip.relative_to(ROOT)}')
    print(f'Method key (do not open until rated): {key_path.relative_to(ROOT)}')
    if len(selected) < 15:
        print(f'WARNING: only {len(selected)} of 15 plans available; missing cells are absent from the packet.')


def status():
    print('Run folder:', RUN.relative_to(ROOT), 'prepared' if (RUN / 'manifest.json').exists() else 'NOT prepared')
    for p in PROFILES:
        row = []
        for m in SOCLAAS_MODELS + CODEX_MODELS:
            name = bm.stem(m, p, LEVEL)
            raw = RUN / 'raw' / f'{name}.json'
            row.append(f'{m}={"ok" if raw.exists() and parseable(raw) else "missing"}({attempts_used(name)} failed)')
        c = RUN / 'csp' / f'{p}.json'
        row.append('CSP=' + (json.loads(c.read_text(encoding='utf-8')).get('status') if c.exists() else 'missing'))
        print(p, ' '.join(row))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('stage', choices=['prepare', 'models', 'csp', 'packet', 'status'])
    ap.add_argument('--profile', choices=PROFILES, help='csp stage: run one profile (default: all three)')
    ap.add_argument('--max-attempts', type=int, default=3, help='models stage: calls per cell before giving up')
    ap.add_argument('--skip-codex', action='store_true', help='models stage: do not run Astra/Sol')
    ap.add_argument('--skip-soclaas', action='store_true', help='models stage: do not run the Qwen models')
    a = ap.parse_args()
    if a.stage == 'prepare':
        prepare()
    elif a.stage == 'models':
        asyncio.run(run_models(a))
    elif a.stage == 'csp':
        run_csp([a.profile] if a.profile else PROFILES)
    elif a.stage == 'packet':
        build_packet()
    else:
        status()
