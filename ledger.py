#!/usr/bin/env python3
"""Validate ledger.csv and query paired comparisons (see LEDGER.md).

    python ledger.py                       # validate ledger.csv
    python ledger.py --best "tau Cet" ml_excess [--period all]

Standard library only.
"""
import argparse
import csv
import math
import re
import sys
from pathlib import Path

COLUMNS = ['run_id', 'date', 'study', 'commit', 'extraction', 'chain', 'config', 'star', 'period',
           'exposure_set', 'n_exp', 'n_nights', 'metric', 'value', 'ci_lo', 'ci_hi', 'baseline_run',
           'diff', 'diff_lo', 'diff_hi', 'source', 'notes']
FLOATS = ['value', 'ci_lo', 'ci_hi', 'diff', 'diff_lo', 'diff_hi']
INTS = ['n_exp', 'n_nights']
REQUIRED_NONEMPTY = ['run_id', 'date', 'metric', 'source']
DEFAULT = Path(__file__).with_name('ledger.csv')


def load(path):
    with open(path, newline='') as fh:
        reader = csv.DictReader(fh)
        return reader.fieldnames or [], list(reader)


def validate(path):
    """Return (errors, warnings) for the ledger at path."""
    header, rows = load(path)
    errors, warnings = [], []
    missing = [c for c in COLUMNS if c not in header]
    if missing:
        return ['missing columns: ' + ', '.join(missing)], warnings
    extra = [c for c in header if c not in COLUMNS]
    if extra:
        warnings.append('extra columns: ' + ', '.join(extra))
    run_ids = {r['run_id'] for r in rows}
    seen = {}
    runcfg = {}
    for i, r in enumerate(rows, start=2):  # line 1 is the header
        where = 'line %d (%s)' % (i, r.get('run_id', ''))
        for c in REQUIRED_NONEMPTY:
            if not r[c]:
                errors.append('%s: empty %s' % (where, c))
        if r['date'] and not re.fullmatch(r'\d{4}-\d{2}-\d{2}', r['date']):
            errors.append('%s: date %r is not YYYY-MM-DD' % (where, r['date']))
        for c in FLOATS:
            if r[c]:
                try:
                    if not math.isfinite(float(r[c])):
                        errors.append('%s: %s %r is not finite' % (where, c, r[c]))
                except ValueError:
                    errors.append('%s: %s %r is not a number' % (where, c, r[c]))
        for c in INTS:
            if r[c] and not re.fullmatch(r'\d+', r[c]):
                errors.append('%s: %s %r is not a count' % (where, c, r[c]))
        b = r['baseline_run']
        if b:
            if b not in run_ids:
                errors.append('%s: baseline_run %r is not a run_id in the ledger' % (where, b))
            if b == r['run_id']:
                errors.append('%s: row is paired against itself' % where)
            if not r['exposure_set']:
                errors.append('%s: paired row without exposure_set' % where)
        elif r['diff'] or r['diff_lo'] or r['diff_hi']:
            errors.append('%s: diff given without baseline_run' % where)
        if (r['diff_lo'] == '') != (r['diff_hi'] == ''):
            errors.append('%s: only one end of the diff interval' % where)
        if (r['ci_lo'] == '') != (r['ci_hi'] == ''):
            errors.append('%s: only one end of the value interval' % where)
        if '/' in r['source'] and not r['source'].startswith('FINDINGS:'):
            errors.append('%s: source %r looks like a path; use the basename' % (where, r['source']))
        key = (r['run_id'], r['star'], r['period'], r['exposure_set'], r['metric'], b)
        if key in seen:
            errors.append('%s: duplicate of line %d (same run, star, period, exposure_set, metric, baseline)' % (where, seen[key]))
        else:
            seen[key] = i
        cfg = (r['extraction'], r['chain'], r['config'])
        runcfg.setdefault(r['run_id'], set()).add(cfg)
    for rid, cfgs in sorted(runcfg.items()):
        if len(cfgs) > 1:
            warnings.append('run_id %s has %d different (extraction, chain, config) descriptions' % (rid, len(cfgs)))
    return errors, warnings


def best(path, star, metric, period=None):
    _, rows = load(path)
    sel = [r for r in rows if r['baseline_run'] and r['diff'] != '' and r['star'] == star and r['metric'] == metric
           and (period is None or r['period'] == period)]
    sel.sort(key=lambda r: (float(r['diff']), r['run_id']))
    if not sel:
        print('no paired rows for star=%r metric=%r%s' % (star, metric, '' if period is None else ' period=%r' % period))
        return
    print('%-28s %-26s %-18s %-30s %8s %18s  %s' % ('run_id', 'baseline_run', 'period', 'exposure_set', 'diff', '95% CI', 'source'))
    for r in sel:
        ci = '[%s, %s]' % (r['diff_lo'], r['diff_hi']) if r['diff_lo'] else ''
        print('%-28s %-26s %-18s %-30s %8s %18s  %s' % (r['run_id'], r['baseline_run'], r['period'], r['exposure_set'],
                                                       r['diff'], ci, r['source']))
    print('%d paired rows; negative diff = run lower than its baseline. Compare rows only within one exposure_set.' % len(sel))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--ledger', default=str(DEFAULT), help='ledger CSV (default: ledger.csv next to this script)')
    ap.add_argument('--best', nargs=2, metavar=('STAR', 'METRIC'), help='print paired comparisons sorted by diff')
    ap.add_argument('--period', help='with --best: only this period')
    a = ap.parse_args(argv)
    if a.best:
        best(a.ledger, a.best[0], a.best[1], a.period)
        return 0
    errors, warnings = validate(a.ledger)
    for w in warnings:
        print('warning:', w)
    for e in errors:
        print('error:', e)
    _, rows = load(a.ledger)
    print('%s: %d rows, %d run_ids, %d paired rows, %d errors' % (
        a.ledger, len(rows), len({r['run_id'] for r in rows}), sum(1 for r in rows if r['baseline_run']), len(errors)))
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
