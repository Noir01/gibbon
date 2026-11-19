"""Markdown tables of query and build time from a bench.py results file.

    python3 summarize.py [results/results.json] > results/SUMMARY.md
"""
import json
import sys

ORDER = ['sklearn-leaf40', 'sklearn-leaf1', 'scipy-ckdtree', 'nanoflann-leaf10', 'nanoflann-leaf1',
         'c', 'packed', 'pointer', 'brute']


def table(datasets, key, unit, scale, per_query, skip=()):
    engines = [e for e in ORDER if e not in skip and any(e in d['engines'] for d in datasets)]
    rows = [f'| d | n | queries | ' + ' | '.join(engines) + ' |', '|' + '---|' * (3 + len(engines))]
    for d in datasets:
        cells = []
        for e in engines:
            r = d['engines'].get(e)
            if r is None or key not in r:
                cells.append('')
                continue
            v = r[key] * scale / (r.get('queries', d['queries']) if per_query else 1)
            cells.append(f'{v:,.0f}' if v >= 100 else f'{v:.2f}')
        q = str(d['queries'])
        brute = d['engines'].get('brute', {}).get('queries')
        if brute and brute != d['queries']:
            q += f' (brute {brute})'
        rows.append(f"| {d['dims']} | {d['points']:,} | {q} | " + ' | '.join(cells) + ' |')
    return f'### {unit}\n\n' + '\n'.join(rows) + '\n'


def ratios(datasets):
    def per_query(d, e):
        r = d['engines'][e]
        return r['query_median_s'] / r.get('queries', d['queries'])
    rows = ['### Query time ratios\n', '| d | n | sklearn-leaf40 / packed | packed / c | packed / nanoflann-leaf10 | pointer / packed |',
            '|---|---|---|---|---|---|']
    for d in datasets:
        if 'packed' not in d['engines']:
            continue
        p = per_query(d, 'packed')
        rows.append(f"| {d['dims']} | {d['points']:,} | {per_query(d, 'sklearn-leaf40') / p:.2f} | {p / per_query(d, 'c'):.2f} | "
                    f"{p / per_query(d, 'nanoflann-leaf10'):.2f} | {per_query(d, 'pointer') / p:.2f} |")
    return '\n'.join(rows) + '\n'


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else 'results/results.json'
    data = json.load(open(path))
    ds = sorted(data['datasets'], key=lambda d: (d['dims'], d['points']))
    env = data['environment']
    print(f"Machine: {env['cpu']} ({env['host']}), {env['gcc']}; Python {env['python']}, "
          f"scikit-learn {env['sklearn']}, SciPy {env['scipy']}, nanoflann {env['nanoflann']}, "
          f"Gibbon {env['gibbon_commit']}. Medians of {ds[0]['repeats']} runs x {ds[0]['query_iters']} batches.\n")
    print(table(ds, 'query_median_s', 'Query, ns per query', 1e9, True))
    print(table(ds, 'build_median_s', 'Build, ms', 1e3, False, skip=('brute',)))
    print(ratios(ds))


if __name__ == '__main__':
    main()
