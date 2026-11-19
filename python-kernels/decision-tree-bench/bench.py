"""Benchmark scikit-learn decision-tree inference against hand-written Gibbon.

Trains DecisionTreeClassifier models of several sizes, exports them, compiles
DecisionTree.hs.in with Gibbon (packed and pointer backends) plus a C
array-of-structs baseline, checks every prediction against scikit-learn, and
times inference. Training, export, compilation and input parsing are reported
separately and are never inside the inference timings.

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
from sklearn.datasets import make_classification
from sklearn.tree import DecisionTreeClassifier

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
WORK = HERE / 'work'
RESULTS = HERE / 'results'

NUM_FEATURES = 32
NUM_TRAIN = 200_000
NUM_TEST = 100_000
DEPTHS = [4, 8, 12, 16, None]
BATCHES = {1: 5000, 100: 2000, 10_000: 50, 100_000: 10}
QUICK_DEPTHS = [4, 12]
QUICK_BATCHES = {1: 500, 100: 200, 10_000: 5}


def dataset():
    X, y = make_classification(n_samples=NUM_TRAIN + NUM_TEST, n_features=NUM_FEATURES,
                               n_informative=20, n_redundant=4, n_classes=4,
                               n_clusters_per_class=2, flip_y=0.02, random_state=0)
    # scikit-learn trees cast inputs to float32 internally; do it up front so
    # every implementation sees bit-identical features.
    X = X.astype(np.float32)
    return X[:NUM_TRAIN], y[:NUM_TRAIN], X[NUM_TRAIN:]


def threshold_down(t64):
    """Largest float32 <= t64: for float32 x, x <= t64 iff x <= threshold_down(t64)."""
    t32 = t64.astype(np.float32)
    up = t32.astype(np.float64) > t64
    t32[up] = np.nextafter(t32[up], np.float32(-np.inf))
    return t32


def threshold_nearest(t64):
    return t64.astype(np.float32)


def traverse(tree, X, thresholds, leaf_class):
    """Vectorised reference traversal with a chosen threshold array."""
    node = np.zeros(len(X), dtype=np.int64)
    rows = np.arange(len(X))
    while True:
        active = tree.feature[node] >= 0
        if not active.any():
            return leaf_class[node]
        n = node[active]
        go_left = X[rows[active], tree.feature[n]] <= thresholds[n]
        node[active] = np.where(go_left, tree.children_left[n], tree.children_right[n])


def boundary_probes(tree, X_test):
    """Rows whose split feature sits exactly at or next to each threshold."""
    internal = np.flatnonzero(tree.feature >= 0)
    t64 = tree.threshold[internal]
    candidates = [threshold_nearest(t64), threshold_down(t64)]
    candidates.append(np.nextafter(candidates[1], np.float32(np.inf)))
    rows = []
    for k, values in enumerate(candidates):
        base = X_test[(np.arange(len(internal)) * 7 + k) % len(X_test)].copy()
        base[np.arange(len(internal)), tree.feature[internal]] = values
        rows.append(base)
    return np.concatenate(rows)


def write_floats(path, X):
    np.savetxt(path, X.reshape(-1, 1), fmt='%.9g')


def export(clf, path):
    tree = clf.tree_
    thresholds = threshold_down(tree.threshold)
    leaf_class = np.argmax(tree.value[:, 0, :], axis=1)
    with open(path, 'w') as f:
        for i in range(tree.node_count):
            if tree.feature[i] >= 0:
                f.write(f'{tree.feature[i]} {thresholds[i]:.9g} {tree.children_left[i]} {tree.children_right[i]} 0\n')
            else:
                f.write(f'-1 0 -1 -1 {leaf_class[i]}\n')
    return thresholds, leaf_class


def run(cmd, cwd=None, env=None, timeout=1800):
    start = time.perf_counter()
    proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
    wall = time.perf_counter() - start
    if proc.returncode:
        raise RuntimeError(f'{cmd} failed ({proc.returncode}):\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}')
    return proc.stdout, wall


def parse(stdout):
    """Parse Gibbon/baseline output: optional build SELFTIMED, timed batch, predictions."""
    lines = stdout.splitlines()
    i = next(k for k, line in enumerate(lines) if line.startswith('ITERS:'))
    build = [float(l.split()[1]) for l in lines[:i] if l.startswith('SELFTIMED:')]
    fields = {}
    for line in lines[i:i + 4]:
        key, value = line.split(':')
        fields[key] = float(value)
    preds = [int(l) for l in lines[i + 4:] if l.strip().lstrip('-').isdigit()]
    return dict(build_s=build[0] if build else None, iters=int(fields['ITERS']),
                median_s=fields['SELFTIMED'], mean_s=fields['BATCHTIME'] / fields['ITERS'],
                preds=np.array(preds))


class Gibbon:
    def __init__(self, compiler, mode, model_dir, num_nodes):
        self.mode, self.dir = mode, model_dir
        src = (HERE / 'DecisionTree.hs.in').read_text()
        src = (src.replace('@NODES_FILE@', 'nodes.txt').replace('@NUM_NODES@', str(num_nodes))
                  .replace('@NUM_FEATURES@', str(NUM_FEATURES)))
        hs = model_dir / f'tree_{mode}.hs'
        hs.write_text(src)
        self.env = dict(os.environ, GIBBONDIR=str(ROOT))
        _, self.compile_s = run([str(compiler), '--hs', f'--{mode}', '--cc=gcc', '--to-exe', hs.name],
                                cwd=model_dir, env=self.env)
        self.exe = hs.with_suffix('.exe')

    def __call__(self, features, rows, iters):
        out, wall = run([str(self.exe), '--array-input', str(features),
                         '--array-input-length', str(rows * NUM_FEATURES),
                         '--size-param', str(rows), '--iterate', str(iters)], cwd=self.dir, env=self.env)
        return dict(parse(out), process_s=wall)


class Baseline:
    mode = 'c-aos'

    def __init__(self, model_dir, num_nodes):
        self.dir, self.num_nodes = model_dir, num_nodes
        self.exe = WORK / 'baseline'
        self.compile_s = None

    def __call__(self, features, rows, iters):
        out, wall = run([str(self.exe), 'nodes.txt', str(self.num_nodes), str(features), str(rows),
                         str(NUM_FEATURES), str(iters)], cwd=self.dir)
        return dict(parse(out), process_s=wall)


def time_sklearn(clf, X, iters):
    times = []
    for _ in range(iters):
        start = time.perf_counter()
        preds = clf.predict(X)
        times.append(time.perf_counter() - start)
    return dict(iters=iters, median_s=float(np.median(times)), mean_s=float(np.mean(times)), preds=preds)


def default_gibbon():
    out = subprocess.run(['cabal', 'list-bin', 'exe:gibbon'], cwd=ROOT / 'gibbon-compiler',
                         capture_output=True, text=True, check=True).stdout
    return Path(out.strip().splitlines()[-1])


def tree_stats(clf, X_test):
    tree = clf.tree_
    internal = int((tree.feature >= 0).sum())
    leaves = tree.node_count - internal
    path = clf.decision_path(X_test).sum(axis=1).mean()
    return dict(nodes=int(tree.node_count), leaves=int(leaves), depth=int(clf.get_depth()),
                mean_path_nodes=float(path),
                # Gibbon packed: tag(1) + right-child pointer(8) + Int(8) + Float(4); leaf: tag(1) + Int(8)
                packed_bytes=internal * 21 + leaves * 9,
                c_aos_bytes=tree.node_count * 16,
                # sklearn Node struct (64 bytes incl. training stats) + per-node class value array
                sklearn_bytes=tree.node_count * (64 + 8 * tree.value.shape[2]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--quick', action='store_true', help='two models, small batches')
    parser.add_argument('--gibbon', type=Path, help='gibbon executable (default: cabal list-bin)')
    args = parser.parse_args()
    depths = QUICK_DEPTHS if args.quick else DEPTHS
    batches = QUICK_BATCHES if args.quick else BATCHES
    compiler = (args.gibbon or default_gibbon()).resolve()

    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True)
    RESULTS.mkdir(exist_ok=True)
    run(['gcc', '-std=gnu11', '-O3', '-o', str(WORK / 'baseline'), str(HERE / 'baseline.c')])

    X_train, y_train, X_test = dataset()
    # Gibbon's readArrayFile ignores --array-input-length and writes every line
    # of the file into a vector of that length, so each batch needs its own file.
    batch_files = {}
    for rows in batches:
        batch_files[rows] = WORK / f'x_test_{rows}.txt'
        write_floats(batch_files[rows], X_test[:rows])

    records = []
    for depth in depths:
        name = f'depth{depth or "Full"}'
        model_dir = WORK / name
        model_dir.mkdir()
        start = time.perf_counter()
        clf = DecisionTreeClassifier(max_depth=depth, random_state=0).fit(X_train, y_train)
        train_s = time.perf_counter() - start
        start = time.perf_counter()
        thresholds, leaf_class = export(clf, model_dir / 'nodes.txt')
        export_s = time.perf_counter() - start
        stats = tree_stats(clf, X_test)
        print(f'{name}: {stats["nodes"]} nodes, depth {stats["depth"]}, trained in {train_s:.2f}s', flush=True)

        # Precision: scikit-learn compares float32 inputs against float64
        # thresholds. Rounding thresholds down to float32 is exact; rounding to
        # nearest is not. Check both on held-out rows and boundary probes.
        probes = boundary_probes(clf.tree_, X_test)
        verify = np.concatenate([X_test, probes])
        verify_file = model_dir / 'x_verify.txt'
        write_floats(verify_file, verify)
        expected = clf.predict(verify)
        precision = {}
        for label, rounding in (('float32_round_down', threshold_down), ('float32_round_nearest', threshold_nearest)):
            got = traverse(clf.tree_, verify, rounding(clf.tree_.threshold), leaf_class)
            precision[label] = dict(test_mismatches=int((got[:NUM_TEST] != expected[:NUM_TEST]).sum()),
                                    probe_mismatches=int((got[NUM_TEST:] != expected[NUM_TEST:]).sum()))
        t64 = clf.tree_.threshold[clf.tree_.feature >= 0]
        precision['thresholds_not_float32_exact'] = int((t64.astype(np.float32).astype(np.float64) != t64).sum())
        precision['probe_rows'] = int(len(probes))

        engines = [Baseline(model_dir, stats['nodes'])]
        for mode in ('packed', 'pointer'):
            engines.append(Gibbon(compiler, mode, model_dir, stats['nodes']))

        record = dict(model=name, max_depth=depth, train_s=train_s, export_s=export_s, **stats,
                      precision=precision, compile_s={}, build_tree_s={}, verify={}, timings=[])
        for engine in engines:
            result = engine(verify_file, len(verify), 1)
            mismatches = int((result['preds'] != expected).sum()) if len(result['preds']) == len(expected) else None
            record['verify'][engine.mode] = dict(rows=int(len(expected)), mismatches=mismatches)
            assert mismatches == 0, (name, engine.mode, mismatches)
            record['compile_s'][engine.mode] = engine.compile_s
            record['build_tree_s'][engine.mode] = result['build_s']
        print(f'  verified {len(expected)} rows ({len(probes)} boundary probes) on all engines', flush=True)

        for rows, iters in batches.items():
            sk = time_sklearn(clf, X_test[:rows], iters)
            assert (sk.pop('preds') == clf.predict(X_test[:rows])).all()
            entry = dict(batch=rows, sklearn=sk)
            for engine in engines:
                result = engine(batch_files[rows], rows, iters)
                assert (result.pop('preds') == expected[:rows]).all(), (name, engine.mode, rows)
                result.pop('build_s')
                entry[engine.mode] = result
            record['timings'].append(entry)
            cells = '  '.join(f'{k}={entry[k]["median_s"] / rows * 1e9:,.1f}ns/row' for k in ('sklearn', 'c-aos', 'packed', 'pointer'))
            print(f'  batch {rows}: {cells}', flush=True)
        records.append(record)

    env = dict(python=platform.python_version(), sklearn=sklearn.__version__, numpy=np.__version__,
               cpu=platform.processor() or platform.machine(),
               gcc=subprocess.run(['gcc', '--version'], capture_output=True, text=True).stdout.splitlines()[0],
               gibbon_commit=subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=ROOT,
                                            capture_output=True, text=True).stdout.strip())
    out = RESULTS / ('results-quick.json' if args.quick else 'results.json')
    out.write_text(json.dumps(dict(environment=env, models=records), indent=2) + '\n')
    print(f'wrote {out}')


if __name__ == '__main__':
    main()
