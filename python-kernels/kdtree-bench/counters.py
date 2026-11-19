"""Hardware counters per query and per visited node for the k-d tree engines,
and where scikit-learn spends a batch query.

Each native engine runs under `perf stat` with 1 and 1 + EXTRA timed query
batches (median of RUNS each); the difference divided by EXTRA * queries is the
cost of one query with input parsing and tree build cancelled out. The hand-written C tree
reports how many nodes the queries visit, which the Gibbon trees share (same
tree, same search). scikit-learn is sampled with `perf record` and its samples
grouped by shared object.

    python3 counters.py [--dims D ...] [--points N] [--queries Q] [--gibbon PATH]
"""
import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time

import numpy as np

import bench

EVENTS = ['cycles', 'instructions', 'branch-misses', 'L1-dcache-load-misses', 'cache-misses']
EXTRA = 20
RUNS = 3


def perf_stat(cmd, cwd, env=None):
    proc = subprocess.run(['perf', 'stat', '-x,', '-e', ','.join(EVENTS), '--'] + cmd, cwd=cwd, env=env,
                          capture_output=True, text=True)
    if proc.returncode:
        raise RuntimeError(f'{cmd}: {proc.stderr[-2000:]}')
    counts = {}
    for line in proc.stderr.splitlines():
        fields = line.split(',')
        if len(fields) > 2 and fields[2] in EVENTS:
            counts[fields[2]] = float(fields[0])
    return counts


def per_query(engine, queries, num_queries):
    env = getattr(engine, 'env', None)
    def median(batches):
        runs = [perf_stat(engine.cmd(queries, num_queries, batches), engine.dir, env) for _ in range(RUNS)]
        return {k: float(np.median([r[k] for r in runs])) for k in EVENTS}
    one, many = median(1), median(1 + EXTRA)
    return {k: (many[k] - one[k]) / (EXTRA * num_queries) for k in EVENTS}


SKLEARN_SCRIPT = '''
import sys, numpy as np
from sklearn.neighbors import KDTree
X = np.loadtxt(sys.argv[1], dtype=np.float64).reshape(-1, int(sys.argv[3]))
Q = np.loadtxt(sys.argv[2], dtype=np.float64).reshape(-1, int(sys.argv[3]))
tree = KDTree(X)
import os; os.kill(os.getpid(), 19)  # SIGSTOP: perf attaches from here
for _ in range(int(sys.argv[4])):
    tree.query(Q, k=1)
os.kill(os.getpid(), 19)  # and stops again before interpreter teardown
'''


def sklearn_profile(data_dir, dims, batches):
    """perf record the query batches only (attached after load and build), samples by shared object."""
    script = data_dir / 'sk.py'
    script.write_text(SKLEARN_SCRIPT)
    proc = subprocess.Popen([sys.executable, str(script), 'points.txt', 'queries.txt', str(dims), str(batches)],
                            cwd=data_dir)

    def wait_stopped():
        while open(f'/proc/{proc.pid}/stat').read().split()[2] != 'T':
            if proc.poll() is not None:
                raise RuntimeError('sklearn profile script exited early')
            time.sleep(0.01)

    wait_stopped()
    rec = subprocess.Popen(['perf', 'record', '-q', '-F', '2000', '-o', 'perf.data', '-p', str(proc.pid)],
                           cwd=data_dir, stderr=subprocess.DEVNULL)
    time.sleep(0.5)
    os.kill(proc.pid, signal.SIGCONT)
    time.sleep(0.1)
    wait_stopped()
    rec.send_signal(signal.SIGINT)
    rec.wait()
    os.kill(proc.pid, signal.SIGCONT)
    proc.wait()
    report = subprocess.run(['perf', 'report', '-i', 'perf.data', '--sort', 'dso', '--stdio', '-q'],
                            cwd=data_dir, capture_output=True, text=True, check=True).stdout
    shares = {}
    for line in report.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].endswith('%'):
            shares[parts[1]] = float(parts[0][:-1])
    report = subprocess.run(['perf', 'report', '-i', 'perf.data', '--sort', 'sym', '--stdio', '-q'],
                            cwd=data_dir, capture_output=True, text=True, check=True).stdout
    symbols = {}
    for line in report.splitlines()[:12]:
        parts = line.split(None, 2)
        if len(parts) == 3 and parts[0].endswith('%'):
            symbols[parts[2].strip()] = float(parts[0][:-1])
    return shares, symbols


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dims', type=int, nargs='+', default=[2, 3, 4, 8, 16])
    parser.add_argument('--points', type=int, default=100_000)
    parser.add_argument('--queries', type=int, nargs='+', default=None,
                        help='queries per dimension, or one count for all (default 10000, 500 for d >= 16)')
    parser.add_argument('--gibbon', type=os.path.abspath)
    parser.add_argument('--nanoflann', type=os.path.abspath)
    parser.add_argument('--out', default='counters.json')
    args = parser.parse_args()
    compiler = args.gibbon or str(bench.default_gibbon().resolve())
    work = bench.HERE / 'work-counters'
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    bench.WORK = work
    bench.build_natives(args.nanoflann)

    rng = np.random.default_rng(1)
    results = []
    for i, dims in enumerate(args.dims):
        nq = (args.queries[i] if len(args.queries) > 1 else args.queries[0]) if args.queries else (500 if dims >= 16 else 10_000)
        data_dir = work / f'd{dims}'
        data_dir.mkdir()
        X = rng.random((args.points, dims), dtype=np.float32)
        Q = rng.random((nq, dims), dtype=np.float32)
        bench.write_floats(data_dir / 'points.txt', X)
        bench.write_floats(data_dir / 'queries.txt', Q)
        engines = [bench.Native('c', work / 'baseline', data_dir, args.points, dims),
                   bench.Native('nanoflann-leaf10', work / 'nanoflann_bench', data_dir, args.points, dims, [10])]
        engines += [bench.Gibbon(compiler, m, data_dir, args.points, dims) for m in ('packed', 'pointer')]
        visits = engines[0](data_dir / 'queries.txt', nq, 1)['visits'] / nq
        record = dict(dims=dims, points=args.points, queries=nq, nodes_visited_per_query=visits, engines={})
        for engine in engines:
            record['engines'][engine.name] = per_query(engine, data_dir / 'queries.txt', nq)
        record['sklearn_dso_share_pct'], record['sklearn_top_symbols_pct'] = sklearn_profile(data_dir, dims, 5)
        results.append(record)
        print(f'd{dims}: {visits:.0f} nodes visited per query', flush=True)
        for name, c in record['engines'].items():
            # Only C and Gibbon build this tree, so only they visit `visits` nodes.
            per_node = (f'   cycles/node {c["cycles"] / visits:6.1f}  insn/node {c["instructions"] / visits:6.1f}'
                        if name in ('c', 'packed', 'pointer') else '')
            print(f'  {name:17s} ' + '  '.join(f'{k} {v:10.1f}' for k, v in c.items()) + per_node, flush=True)
        top = sorted(record['sklearn_dso_share_pct'].items(), key=lambda kv: -kv[1])[:5]
        print('  sklearn samples by object: ' + ', '.join(f'{k} {v:.1f}%' for k, v in top), flush=True)
        shutil.rmtree(data_dir)
        (bench.RESULTS / args.out).write_text(json.dumps(results, indent=2) + '\n')
    shutil.rmtree(work)


if __name__ == '__main__':
    main()
