"""Build the disposable handwritten single-schema packed-tree kernel."""
import ctypes
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

def build():
    compiler = ROOT / 'python-kernels/spikes/native/gibbon'
    subprocess.run([str(compiler), '--hs', '--packed', '--biginf', '--no-rcopies', '--toC', 'module.hs'], cwd=HERE, check=True)
    text = (HERE / 'module.c').read_text()
    signature = 'GibCursorGibCursorGibCursorProd mk_tree(GibCursor end_r_308, GibCursor loc_307,'
    if signature not in text:
        raise RuntimeError('generated builder cursor tuple ABI changed')
    start = text.index('GibCursorGibCursorGibCursorProd mk_tree(', text.index('GibCursorGibCursorGibCursorProd mk_tree(') + 1)
    stop = text.index('\n}', start) + 2
    body = text[start:stop]
    if any(token in body for token in ('gib_alloc', 'gib_grow', 'gib_promote', 'gib_alloc_region')):
        raise RuntimeError('generated ordinary builder has runtime allocation/growth calls')
    runtime = ROOT / 'gibbon-rts'
    subprocess.run(['gcc', '-fPIC', '-shared', '-O2', '-Wl,-Bsymbolic', '-D_GIBBON_GENGC=0', '-D_GIBBON_SIMPLE_WRITE_BARRIER=0', '-D_GIBBON_EAGER_PROMOTION=1', '-I', str(runtime/'rts-c'), '-I', str(ROOT/'deps/uthash'), 'bridge.c', str(runtime/'rts-c/gibbon_rts.c'), '-L', str(runtime/'build'), '-lgibbon_rts_ng', '-lm', '-Wl,-rpath,'+str(runtime/'build'), '-o', 'tree_construction_native.so'], cwd=HERE, check=True)
    lib = ctypes.CDLL(str(HERE/'tree_construction_native.so'))
    byte_ptr = ctypes.POINTER(ctypes.c_ubyte)
    lib.kernel_build.argtypes = [byte_ptr, ctypes.c_size_t, ctypes.c_int64]
    lib.kernel_build.restype = ctypes.c_ssize_t
    lib.kernel_sum.argtypes = [byte_ptr, ctypes.c_size_t]
    lib.kernel_sum.restype = ctypes.c_int64
    return lib, body

if __name__ == '__main__':
    lib, body = build()
    print('builder ABI:', body.splitlines()[0].strip())
    print('generated constructor body has no allocation/growth calls')
