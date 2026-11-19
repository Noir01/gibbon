"""Isolate vector lowering vs backend specialization; run on Vulcan."""
from pathlib import Path
import os
import subprocess
from translate import translate

root = Path('/home/noir/gibbon-python-mvp')
compiler = root / 'python-kernels/spikes/native/gibbon'
build = Path(__file__).resolve().parent / 'build/probes'
build.mkdir(parents=True, exist_ok=True)
source = 'def main() -> int:\n    values = [0] * 3\n    return len(values)\n'
base = translate(source).replace('let { vec :: Vector Int; vec = valloc count }', 'let vec = valloc count')
variants = {
    'base': base,
    'annotated_alloc': base.replace('valloc 0', '(valloc 0 :: Vector Int)').replace('valloc count', '(valloc count :: Vector Int)'),
    'declared_let': base.replace('let vec = valloc count', 'let { vec :: Vector Int; vec = valloc count }'),
    'typed_let': base.replace('let vec = valloc count', 'let (vec :: Vector Int) = valloc count'),
    'typed_params': base.replace('count seed vec =', 'count seed (vec :: Vector Int) =').replace('vec raw =', '(vec :: Vector Int) raw ='),
    'no_empty_branch': base.replace('(if count <= 0 then valloc 0 else (let vec = valloc count in p_fill 0 count seed vec))', '(let vec = valloc count in p_fill 0 count seed vec)'),
}
for name, text in variants.items():
    path = build / (name + '.hs')
    path.write_text(text)
    result = subprocess.run([str(compiler), '--hs', '--packed', '--toC', str(path)], env=dict(os.environ, GIBBONDIR=str(root)), capture_output=True, text=True, timeout=30)
    (build / (name + '.log')).write_text(result.stdout + result.stderr)
    print(name, result.returncode, result.stderr[:250], flush=True)
