"""Build the restricted flat-buffer kernels; run inside shell-sequential.nix."""
import ctypes
import subprocess
import tempfile
from pathlib import Path

from frontend import generate_source

ROOT = Path(__file__).resolve().parents[2]


def witness_source(schema, sum_constructors=None):
    """Keep both operations reachable without the packed-file compiler path."""
    terminal = next((c for c in schema.constructors
                     if all(f.kind == 'int' for f in c.fields)), None)
    if terminal is None:
        raise TypeError('schema needs a constructor without recursive fields')
    recursive = next((c for c in schema.constructors
                      if any(f.kind == 'recursive' for f in c.fields)), None)
    def constructor(c, recurse):
        args = ['depth' if f.kind == 'int' else recurse for f in c.fields]
        return c.name + ''.join(' (' + a + ')' for a in args)
    leaf = constructor(terminal, '')
    body = leaf if recursive is None else (
        'if depth <= 0 then ' + leaf + ' else ' +
        constructor(recursive, 'mk_root (depth - 1)'))
    return (generate_source(schema, sum_constructors=sum_constructors) + '\nmk_root :: Int -> ' + schema.name +
            '\nmk_root depth = ' + body +
            '\ngibbon_main = sum_ints (add_ints (mk_root sizeParam) 1)\n')


BRIDGE = '''
/* Private ABI: valid flat buffers, no aliasing, no overflow.
   Generated with --biginf --no-rcopies; caller owns both buffers. */
#define main generated_main
#include "module.c"
#undef main
int64_t kernel_sum(const uint8_t *data, size_t length) {
    GibCursor root = (GibCursor)data;
    return sum_ints(root + length, root).field2;
}
ssize_t kernel_add(const uint8_t *data, size_t length, int64_t amount,
                   uint8_t *output, size_t capacity) {
    if (!data || !output || !length || capacity < length) return -1;
    GibCursor root = (GibCursor)data, dest = (GibCursor)output;
    return add_ints(root + length, dest + capacity, dest, root, amount).field4 - dest;
}
'''


def run(command, directory):
    result = subprocess.run(command, cwd=directory, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            timeout=120)
    with (directory / 'build.log').open('a') as log:
        log.write(repr(command) + '\n' + result.stdout + '\n')
    if result.returncode:
        raise RuntimeError(f'build failed; see {directory / "build.log"}\n{result.stdout}')


def build(schema, sum_constructors=None):
    source = witness_source(schema, sum_constructors=sum_constructors)  # validate before touching the filesystem
    parent = ROOT / 'python-kernels' / 'integration' / 'build'
    parent.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix=schema.name + '-', dir=parent))
    (directory / 'module.hs').write_text(source)
    compiler = ROOT / 'python-kernels' / 'spikes' / 'native' / 'gibbon'
    run([str(compiler), '--hs', '--packed', '--biginf', '--no-rcopies',
         '--toC', 'module.hs'], directory)
    generated = (directory / 'module.c').read_text()
    # This spike adapter is deliberately tied to the observed cursor tuple ABI.
    if ('GibCursorGibCursorGibIntProd sum_ints(' not in generated or
        'GibCursorGibCursorGibCursorGibCursorGibCursorProd add_ints(' not in generated):
        raise RuntimeError('generated kernel ABI changed; inspect ' + str(directory))
    (directory / 'bridge.c').write_text(BRIDGE)
    runtime = ROOT / 'gibbon-rts'
    library = directory / 'kernels.so'
    run(['gcc', '-fPIC', '-shared', '-O2', '-Wl,-Bsymbolic',
         '-D_GIBBON_GENGC=0', '-D_GIBBON_SIMPLE_WRITE_BARRIER=0',
         '-D_GIBBON_EAGER_PROMOTION=1', '-I', str(runtime / 'rts-c'),
         '-I', str(ROOT / 'deps' / 'uthash'), 'bridge.c',
         str(runtime / 'rts-c' / 'gibbon_rts.c'), '-L', str(runtime / 'build'),
         '-lgibbon_rts_ng', '-lm', '-Wl,-rpath,' + str(runtime / 'build'),
         '-o', str(library)], directory)
    lib = ctypes.CDLL(str(library))
    byte_ptr = ctypes.POINTER(ctypes.c_ubyte)
    lib.kernel_sum.argtypes = [byte_ptr, ctypes.c_size_t]
    lib.kernel_sum.restype = ctypes.c_int64
    lib.kernel_add.argtypes = [byte_ptr, ctypes.c_size_t, ctypes.c_int64,
                              byte_ptr, ctypes.c_size_t]
    lib.kernel_add.restype = ctypes.c_ssize_t
    return lib, directory
