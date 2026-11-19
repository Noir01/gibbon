"""Benchmark exact 1-nearest-neighbour search: hand-written Gibbon k-d tree vs
scikit-learn's KDTree, SciPy's cKDTree, nanoflann, a plain C k-d tree with the
same algorithm as the Gibbon one, and C brute force.

For each dimension and point count, draws uniform float32 points and queries,
compiles KDTree.hs.in with Gibbon (packed and pointer backends) and the C/C++
programs, checks every engine's answers against scikit-learn, then times tree
build and batches of queries. Input parsing and compilation are never inside
the timings.

    python3 bench.py [--quick] [--dims D ...] [--points N ...] [--gibbon PATH]
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
import scipy
from scipy.spatial import cKDTree
import sklearn
from sklearn.neighbors import KDTree

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
WORK = HERE / 'work'
RESULTS = HERE / 'results'

DIMS = [2, 3, 4, 8, 16]
POINTS = [10_000, 100_000, 1_000_000]
MAX_QUERIES = 10_000
MIN_QUERIES = 200
TARGET_BATCH_S = 1.0   # query count is cut so one scikit-learn batch takes about this long
BRUTE_BATCH_S = 1.0    # brute force runs on the first queries only, sized to about this long
REPEATS = 5            # processes per engine; build is timed once per process
QUERY_ITERS = 5        # timed query batches per process
SKLEARN_LEAF_SIZES = [40, 1]    # 40 is the default; 1 is one point per leaf like the hand-written trees
NANOFLANN_LEAF_SIZES = [10, 1]  # 10 is the default
NANOFLANN_TAG = 'v1.8.0'
CALL_OVERHEAD_CALLS = 2_000
QUICK = dict(dims=[2, 8], points=[20_000], max_queries=2_000, repeats=2, iters=2)


def write_floats(path, X):
    np.savetxt(path, X.reshape(-1, 1), fmt='%.9g')


def run(cmd, cwd=None, env=None, timeout=7200):
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
    visits = [int(l.split()[1]) for l in lines[i + 4:] if l.startswith('VISITS:')]
    return dict(build_s=build[0], query_median_s=float(fields['SELFTIMED']),
                query_mean_s=float(fields['BATCHTIME']) / float(fields['ITERS']), idx=np.array(idx),
                visits=visits[0] if visits else None)


class Gibbon:
    def __init__(self, compiler, mode, data_dir, num_points, dims):
        self.name, self.dir, self.dims = mode, data_dir, dims
        src = (HERE / 'KDTree.hs.in').read_text()
        src = (src.replace('@POINTS_FILE@', 'points.txt').replace('@NUM_COORDS@', str(num_points * dims))
                  .replace('@DIMS@', str(dims)))
        hs = data_dir / f'kdtree_{mode}.hs'
        hs.write_text(src)
        self.env = dict(os.environ, GIBBONDIR=str(ROOT))
        _, self.compile_s = run([str(compiler), '--hs', f'--{mode}', '--cc=gcc', '--to-exe', hs.name],
                                cwd=data_dir, env=self.env)
        self.exe = hs.with_suffix('.exe')

    def cmd(self, queries, num_queries, iters):
        return [str(self.exe), '--array-input', str(queries), '--array-input-length', str(num_queries * self.dims),
                '--size-param', str(num_queries), '--iterate', str(iters)]

    def __call__(self, queries, num_queries, iters):
        out, wall = run(self.cmd(queries, num_queries, iters), cwd=self.dir, env=self.env)
        return dict(parse(out), process_s=wall)


class Native:
    """A C/C++ program taking POINTS NUM_POINTS QUERIES NUM_QUERIES DIMS ITERS [extra...]."""
    compile_s = None

    def __init__(self, name, exe, data_dir, num_points, dims, extra=()):
        self.name, self.exe, self.dir = name, exe, data_dir
        self.num_points, self.dims, self.extra = num_points, dims, [str(x) for x in extra]

    def cmd(self, queries, num_queries, iters):
        return [str(self.exe), 'points.txt', str(self.num_points), str(queries), str(num_queries),
                str(self.dims), str(iters)] + self.extra

    def __call__(self, queries, num_queries, iters):
        out, wall = run(self.cmd(queries, num_queries, iters), cwd=self.dir)
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
                builds_s=builds, queries_s=queries), dist[:, 0], idx[:, 0], tree


def time_scipy(X, Q, repeats, iters):
    builds, queries = [], []
    for _ in range(repeats):
        start = time.perf_counter()
        tree = cKDTree(X)
        builds.append(time.perf_counter() - start)
        for _ in range(iters):
            start = time.perf_counter()
            dist, idx = tree.query(Q, k=1, workers=1)
            queries.append(time.perf_counter() - start)
    return dict(build_median_s=float(np.median(builds)), query_median_s=float(np.median(queries)),
                builds_s=builds, queries_s=queries), idx


def call_overhead(tree, Q):
    """Median time of tree.query on one query, and on one query repeated in a
    single call of the batch's size divided per query: the difference is the
    fixed cost of a call from Python."""
    q1 = Q[:1]
    times = []
    for _ in range(CALL_OVERHEAD_CALLS):
        start = time.perf_counter()
        tree.query(q1, k=1)
        times.append(time.perf_counter() - start)
    reps = np.repeat(q1, min(len(Q), 2_000), axis=0)
    batch = []
    for _ in range(5):
        start = time.perf_counter()
        tree.query(reps, k=1)
        batch.append((time.perf_counter() - start) / len(reps))
    one, per = float(np.median(times)), float(np.median(batch))
    return dict(one_query_call_s=one, same_query_in_batch_s=per, fixed_call_cost_s=one - per)


def choose_queries(tree, Q, max_queries, min_queries):
    probe = Q[:min(len(Q), 200)]
    start = time.perf_counter()
    tree.query(probe, k=1)
    per_query = (time.perf_counter() - start) / len(probe)
    n = int(TARGET_BATCH_S / per_query) if per_query > 0 else max_queries
    return max(min(n, max_queries), min(min_queries, max_queries))


def default_gibbon():
    out = subprocess.run(['cabal', 'list-bin', 'exe:gibbon'], cwd=ROOT / 'gibbon-compiler',
                         capture_output=True, text=True, check=True).stdout
    return Path(out.strip().splitlines()[-1])


def build_natives(nanoflann_dir):
    if nanoflann_dir is None:
        nanoflann_dir = WORK / 'nanoflann'
        run(['git', 'clone', '-q', '--depth', '1', '-b', NANOFLANN_TAG,
             'https://github.com/jlblancoc/nanoflann.git', str(nanoflann_dir)])
    run(['gcc', '-std=gnu11', '-O3', '-o', str(WORK / 'baseline'), str(HERE / 'baseline.c')])
    run(['gcc', '-std=gnu11', '-O3', '-o', str(WORK / 'brute'), str(HERE / 'brute.c')])
    run(['g++', '-std=c++17', '-O3', '-I', str(Path(nanoflann_dir) / 'include'),
         '-o', str(WORK / 'nanoflann_bench'), str(HERE / 'nanoflann_bench.cpp')])
    version = run(['git', 'describe', '--tags'], cwd=nanoflann_dir)[0].strip()
    return version


def check(name, idx, X64, Q64, ref_idx, ref_dist):
    got = np.sqrt(((X64[idx] - Q64[:len(idx)]) ** 2).sum(axis=1))
    ref = ref_dist[:len(idx)]
    excess = (got - ref) / np.maximum(ref, 1e-30)
    worse = int((excess > 1e-6).sum())
    if worse:
        raise RuntimeError(f'{name}: {worse} answers farther than scikit-learn')
    return dict(index_mismatches_vs_sklearn=int((idx != ref_idx[:len(idx)]).sum()),
                worse_than_sklearn=worse, max_rel_excess=float(excess.max()))


def run_dataset(compiler, rng, dims, num_points, max_queries, repeats, iters, engines_wanted):
    name = f'd{dims}-n{num_points}'
    data_dir = WORK / name
    data_dir.mkdir()
    X = rng.random((num_points, dims), dtype=np.float32)
    Q = rng.random((max_queries, dims), dtype=np.float32)
    X64, Q64 = X.astype(np.float64), Q.astype(np.float64)

    ref_tree = KDTree(X64)
    num_queries = choose_queries(ref_tree, Q64, max_queries, MIN_QUERIES)
    Q, Q64 = Q[:num_queries], Q64[:num_queries]
    write_floats(data_dir / 'points.txt', X)
    write_floats(data_dir / 'queries.txt', Q)
    ref_dist, ref_idx = (a[:, 0] for a in ref_tree.query(Q64, k=1))

    record = dict(dims=dims, points=num_points, queries=num_queries, repeats=repeats, query_iters=iters, engines={})
    e = record['engines']
    for leaf in SKLEARN_LEAF_SIZES:
        timing, _, idx, tree = time_sklearn(X64, Q64, leaf, repeats, iters)
        e[f'sklearn-leaf{leaf}'] = dict(timing, **check(f'{name} sklearn-leaf{leaf}', idx, X64, Q64, ref_idx, ref_dist))
        if leaf == 40:
            e[f'sklearn-leaf{leaf}']['call_overhead'] = call_overhead(tree, Q64)
    timing, idx = time_scipy(X64, Q64, repeats, iters)
    e['scipy-ckdtree'] = dict(timing, **check(f'{name} scipy', idx, X64, Q64, ref_idx, ref_dist))

    engines = [Native('c', WORK / 'baseline', data_dir, num_points, dims)]
    engines += [Native(f'nanoflann-leaf{leaf}', WORK / 'nanoflann_bench', data_dir, num_points, dims, [leaf])
                for leaf in NANOFLANN_LEAF_SIZES]
    for mode in ('packed', 'pointer'):
        if mode in engines_wanted:
            engines.append(Gibbon(compiler, mode, data_dir, num_points, dims))

    answers = {}
    for engine in engines:
        runs = [engine(data_dir / 'queries.txt', num_queries, iters) for _ in range(repeats)]
        idx = runs[0]['idx']
        if len(idx) != num_queries or any((r['idx'] != idx).any() for r in runs):
            raise RuntimeError(f'{name} {engine.name}: missing or unstable answers')
        answers[engine.name] = idx
        e[engine.name] = dict(
            compile_s=engine.compile_s,
            build_median_s=float(np.median([r['build_s'] for r in runs])),
            query_median_s=float(np.median([r['query_median_s'] for r in runs])),
            builds_s=[r['build_s'] for r in runs], queries_s=[r['query_median_s'] for r in runs],
            process_s=[r['process_s'] for r in runs],
            **check(f'{name} {engine.name}', idx, X64, Q64, ref_idx, ref_dist))
        if runs[0]['visits'] is not None:
            e[engine.name]['nodes_visited_per_query'] = runs[0]['visits'] / num_queries

    # Brute force on the first queries only, sized from the C tree's cost model: n * d multiply-adds.
    brute_queries = int(BRUTE_BATCH_S / (num_points * dims * 0.6e-9))
    brute_queries = max(min(brute_queries, num_queries), min(20, num_queries))
    write_floats(data_dir / 'queries-brute.txt', Q[:brute_queries])
    brute = Native('brute', WORK / 'brute', data_dir, num_points, dims)
    brute_iters = max(1, min(iters, 3))
    runs = [brute(data_dir / 'queries-brute.txt', brute_queries, brute_iters) for _ in range(3)]
    e['brute'] = dict(queries=brute_queries, repeats=3, query_iters=brute_iters, build_median_s=0.0,
                      query_median_s=float(np.median([r['query_median_s'] for r in runs])),
                      queries_s=[r['query_median_s'] for r in runs], process_s=[r['process_s'] for r in runs],
                      **check(f'{name} brute', runs[0]['idx'], X64, Q64, ref_idx, ref_dist))

    record['gibbon_matches_c'] = {m: bool((answers[m] == answers['c']).all()) for m in answers if m in ('packed', 'pointer')}
    if not all(record['gibbon_matches_c'].values()):
        raise RuntimeError(f'{name}: Gibbon and C disagree {record["gibbon_matches_c"]}')

    print(f'{name}: {num_points} points, {num_queries} queries (brute force {brute_queries})', flush=True)
    for key, v in e.items():
        nq = v.get('queries', num_queries)
        print(f'  {key:18s} build {v["build_median_s"] * 1e3:9.2f} ms   '
              f'query {v["query_median_s"] / nq * 1e9:12.1f} ns/query', flush=True)
    shutil.rmtree(data_dir)
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--quick', action='store_true', help='two dimensions, small inputs')
    parser.add_argument('--gibbon', type=Path, help='gibbon executable (default: cabal list-bin)')
    parser.add_argument('--nanoflann', type=Path, help='nanoflann checkout (default: clone %s)' % NANOFLANN_TAG)
    parser.add_argument('--dims', type=int, nargs='+', help='override the dimensions')
    parser.add_argument('--points', type=int, nargs='+', help='override the point counts')
    parser.add_argument('--max-queries', type=int, help='override the largest number of queries')
    parser.add_argument('--repeats', type=int, help='override processes per engine')
    parser.add_argument('--iters', type=int, help='override timed batches per process')
    parser.add_argument('--no-gibbon', action='store_true', help='skip the Gibbon engines')
    parser.add_argument('--out', help='results file name (default: results.json / results-quick.json)')
    args = parser.parse_args()
    q = QUICK if args.quick else dict(dims=DIMS, points=POINTS, max_queries=MAX_QUERIES, repeats=REPEATS,
                                      iters=QUERY_ITERS)
    dims_list = args.dims or q['dims']
    points_list = args.points or q['points']
    max_queries = args.max_queries or q['max_queries']
    repeats = args.repeats or q['repeats']
    iters = args.iters or q['iters']
    engines_wanted = () if args.no_gibbon else ('packed', 'pointer')
    compiler = None if args.no_gibbon else (args.gibbon or default_gibbon()).resolve()

    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True)
    RESULTS.mkdir(exist_ok=True)
    nanoflann_version = build_natives(args.nanoflann)
    out = RESULTS / (args.out or ('results-quick.json' if args.quick else 'results.json'))

    env = dict(python=platform.python_version(), sklearn=sklearn.__version__, scipy=scipy.__version__,
               numpy=np.__version__, nanoflann=nanoflann_version,
               cpu=next((l.split(':', 1)[1].strip() for l in open('/proc/cpuinfo') if l.startswith('model name')),
                        platform.machine()),
               nproc=os.cpu_count(), host=platform.node(),
               gcc=subprocess.run(['gcc', '--version'], capture_output=True, text=True).stdout.splitlines()[0],
               gibbon_commit=subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=ROOT,
                                            capture_output=True, text=True).stdout.strip())
    rng = np.random.default_rng(0)
    records = []
    for dims in dims_list:
        for num_points in points_list:
            records.append(run_dataset(compiler, rng, dims, num_points, max_queries, repeats, iters, engines_wanted))
            out.write_text(json.dumps(dict(environment=env, datasets=records), indent=2) + '\n')
    print(f'wrote {out}')


if __name__ == '__main__':
    main()
