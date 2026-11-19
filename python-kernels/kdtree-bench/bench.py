"""Benchmark exact 1-nearest-neighbour search: hand-written Gibbon k-d tree vs
scikit-learn's KDTree vs a plain C k-d tree.

For each dimension, draws uniform float32 points and queries, compiles
KDTree.hs.in with Gibbon (packed and pointer backends) and baseline.c, checks
every engine's answers against scikit-learn, then times tree build and a batch
of queries. Input parsing and compilation are never inside the timings.

    python3 bench.py [--quick] [--gibbon PATH]
"""
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import time

import numpy as np
import sklearn
from sklearn.neighbors import KDTree

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
WORK = HERE / 'work'
RESULTS = HERE / 'results'

DIMS = [2, 3, 8, 16]
NUM_POINTS = 100_000
NUM_QUERIES = 10_000
REPEATS = 5        # processes per engine; build is timed once per process
QUERY_ITERS = 5    # timed query batches per process
SKLEARN_LEAF_SIZES = [40, 1]   # 40 is the default; 1 is one point per leaf like the hand-written trees
QUICK = dict(dims=[2, 8], points=20_000, queries=2_000, repeats=2, iters=2)


def write_floats(path, X):
    np.savetxt(path, X.reshape(-1, 1), fmt='%.9g')


def run(cmd, cwd=None, env=None, timeout=3600):
    start = time.perf_counter()
    proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
    wall = time.perf_counter() - start
    if proc.returncode:
        raise RuntimeError(f'{cmd} failed ({proc.returncode}):\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}')
    return proc.stdout, wall


def parse(stdout):
    """Build SELFTIMED line, then the iterate block, then one neighbour index per line."""
    lines = stdout.splitlines()
    i = next(k for k, line in enumerate(lines) if line.startswith('ITERS:'))
    build = [float(l.split()[1]) for l in lines[:i] if l.startswith('SELFTIMED:')]
    fields = dict(line.split(':') for line in lines[i:i + 4])
    idx = [int(l) for l in lines[i + 4:] if l.strip().lstrip('-').isdigit()]
    return dict(build_s=build[0], query_median_s=float(fields['SELFTIMED']),
                query_mean_s=float(fields['BATCHTIME']) / float(fields['ITERS']), idx=np.array(idx))


class Gibbon:
    def __init__(self, compiler, mode, data_dir, num_points, dims):
        self.mode, self.dir = mode, data_dir
        src = (HERE / 'KDTree.hs.in').read_text()
        src = (src.replace('@POINTS_FILE@', 'points.txt').replace('@NUM_COORDS@', str(num_points * dims))
                  .replace('@DIMS@', str(dims)))
        hs = data_dir / f'kdtree_{mode}.hs'
        hs.write_text(src)
        self.env = dict(os.environ, GIBBONDIR=str(ROOT))
        _, self.compile_s = run([str(compiler), '--hs', f'--{mode}', '--cc=gcc', '--to-exe', hs.name],
                                cwd=data_dir, env=self.env)
        self.exe = hs.with_suffix('.exe')
        self.dims = dims

    def __call__(self, queries, num_queries, iters):
        out, wall = run([str(self.exe), '--array-input', str(queries),
                         '--array-input-length', str(num_queries * self.dims),
                         '--size-param', str(num_queries), '--iterate', str(iters)], cwd=self.dir, env=self.env)
        return dict(parse(out), process_s=wall)


class Baseline:
    mode = 'c'
    compile_s = None

    def __init__(self, data_dir, num_points, dims):
        self.dir, self.num_points, self.dims = data_dir, num_points, dims

    def __call__(self, queries, num_queries, iters):
        out, wall = run([str(WORK / 'baseline'), 'points.txt', str(self.num_points), str(queries),
                         str(num_queries), str(self.dims), str(iters)], cwd=self.dir)
        return dict(parse(out), process_s=wall)


def time_sklearn(X, Q, leaf_size, repeats, iters):
    builds, queries = [], []
    for _ in range(repeats):
        start = time.perf_counter()
        tree = KDTree(X, leaf_size=leaf_size)
        builds.append(time.perf_counter() - start)
        for _ in range(iters):
            start = time.perf_counter()
            dist, idx = tree.query(Q, k=1)
            queries.append(time.perf_counter() - start)
    return dict(build_median_s=float(np.median(builds)), query_median_s=float(np.median(queries)),
                builds_s=builds, queries_s=queries), dist[:, 0], idx[:, 0]


def default_gibbon():
    out = subprocess.run(['cabal', 'list-bin', 'exe:gibbon'], cwd=ROOT / 'gibbon-compiler',
                         capture_output=True, text=True, check=True).stdout
    return Path(out.strip().splitlines()[-1])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--quick', action='store_true', help='two dimensions, small inputs')
    parser.add_argument('--gibbon', type=Path, help='gibbon executable (default: cabal list-bin)')
    parser.add_argument('--dims', type=int, nargs='+', help='override the dimensions')
    parser.add_argument('--queries', type=int, help='override the number of queries')
    parser.add_argument('--out', help='results file name (default: results.json / results-quick.json)')
    args = parser.parse_args()
    if args.quick:
        dims_list, num_points, num_queries = QUICK['dims'], QUICK['points'], QUICK['queries']
        repeats, iters = QUICK['repeats'], QUICK['iters']
    else:
        dims_list, num_points, num_queries, repeats, iters = DIMS, NUM_POINTS, NUM_QUERIES, REPEATS, QUERY_ITERS
    dims_list = args.dims or dims_list
    num_queries = args.queries or num_queries
    compiler = (args.gibbon or default_gibbon()).resolve()

    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True)
    RESULTS.mkdir(exist_ok=True)
    run(['gcc', '-std=gnu11', '-O3', '-o', str(WORK / 'baseline'), str(HERE / 'baseline.c')])

    rng = np.random.default_rng(0)
    records = []
    for dims in dims_list:
        name = f'd{dims}'
        data_dir = WORK / name
        data_dir.mkdir()
        X = rng.random((num_points, dims), dtype=np.float32)
        Q = rng.random((num_queries, dims), dtype=np.float32)
        write_floats(data_dir / 'points.txt', X)
        write_floats(data_dir / 'queries.txt', Q)
        X64, Q64 = X.astype(np.float64), Q.astype(np.float64)

        record = dict(dims=dims, points=num_points, queries=num_queries, repeats=repeats,
                      query_iters=iters, engines={})
        ref_dist = None
        for leaf in SKLEARN_LEAF_SIZES:
            timing, dist, idx = time_sklearn(X64, Q64, leaf, repeats, iters)
            ref_dist = dist if ref_dist is None else ref_dist
            record['engines'][f'sklearn-leaf{leaf}'] = timing
        ref_idx = KDTree(X64).query(Q64, k=1)[1][:, 0]

        engines = [Baseline(data_dir, num_points, dims)]
        for mode in ('packed', 'pointer'):
            engines.append(Gibbon(compiler, mode, data_dir, num_points, dims))
        answers = {}
        for engine in engines:
            runs = [engine(data_dir / 'queries.txt', num_queries, iters) for _ in range(repeats)]
            idx = runs[0]['idx']
            if len(idx) != num_queries or any((r['idx'] != idx).any() for r in runs):
                raise RuntimeError(f'{name} {engine.mode}: missing or unstable answers')
            answers[engine.mode] = idx
            got = np.sqrt(((X64[idx] - Q64) ** 2).sum(axis=1))
            excess = (got - ref_dist) / np.maximum(ref_dist, 1e-30)
            record['engines'][engine.mode] = dict(
                compile_s=engine.compile_s,
                build_median_s=float(np.median([r['build_s'] for r in runs])),
                query_median_s=float(np.median([r['query_median_s'] for r in runs])),
                builds_s=[r['build_s'] for r in runs], queries_s=[r['query_median_s'] for r in runs],
                process_s=[r['process_s'] for r in runs],
                index_mismatches_vs_sklearn=int((idx != ref_idx).sum()),
                worse_than_sklearn=int((excess > 1e-6).sum()),
                max_rel_excess=float(excess.max()))
        record['gibbon_matches_c'] = {m: bool((answers[m] == answers['c']).all()) for m in ('packed', 'pointer')}
        records.append(record)

        e = record['engines']
        print(f'{name}: {num_points} points, {num_queries} queries', flush=True)
        for key in e:
            worse = e[key].get('worse_than_sklearn')
            print(f'  {key:15s} build {e[key]["build_median_s"] * 1e3:9.2f} ms   '
                  f'query {e[key]["query_median_s"] / num_queries * 1e9:10.1f} ns/query'
                  + ('' if worse is None else f'   index mismatches {e[key]["index_mismatches_vs_sklearn"]}, worse {worse}'),
                  flush=True)
        if not all(record['gibbon_matches_c'].values()) or any(e[m]['worse_than_sklearn'] for m in answers):
            raise RuntimeError(f'{name}: wrong neighbours {record["gibbon_matches_c"]}')

    env = dict(python=platform.python_version(), sklearn=sklearn.__version__, numpy=np.__version__,
               cpu=next((l.split(':', 1)[1].strip() for l in open('/proc/cpuinfo') if l.startswith('model name')),
                        platform.machine()),
               nproc=os.cpu_count(),
               gcc=subprocess.run(['gcc', '--version'], capture_output=True, text=True).stdout.splitlines()[0],
               gibbon_commit=subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=ROOT,
                                            capture_output=True, text=True).stdout.strip())
    out = RESULTS / (args.out or ('results-quick.json' if args.quick else 'results.json'))
    out.write_text(json.dumps(dict(environment=env, datasets=records), indent=2) + '\n')
    print(f'wrote {out}')


if __name__ == '__main__':
    main()
