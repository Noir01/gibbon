import ctypes
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).parent

def lit(n): return b'\x00' + struct.pack('@q', n)
def add(a, b): return b'\x01' + a + b

def load():
    lib = ctypes.CDLL(str(ROOT / 'libexpr_bridge.so'))
    byte_ptr = ctypes.POINTER(ctypes.c_ubyte)
    lib.expr_sum.argtypes = [byte_ptr, ctypes.c_size_t]
    lib.expr_sum.restype = ctypes.c_int64
    lib.expr_add.argtypes = [byte_ptr, ctypes.c_size_t, ctypes.c_int64, byte_ptr, ctypes.c_size_t]
    lib.expr_add.restype = ctypes.c_ssize_t
    return lib

class NativeBridgeTest(unittest.TestCase):
    def test_python_encoded_literals_and_nested_add_sum(self):
        lib = load()
        tree = add(lit(-8), add(lit(20), lit(-3)))
        data = (ctypes.c_ubyte * len(tree)).from_buffer_copy(tree)
        self.assertEqual(lib.expr_sum(data, len(tree)), 9)

    def test_generated_increment_into_independent_output(self):
        lib = load()
        tree = add(lit(-8), add(lit(20), lit(-3)))
        data = (ctypes.c_ubyte * len(tree)).from_buffer_copy(tree)
        original = bytes(data)
        output = (ctypes.c_ubyte * (len(tree) + 128))()
        written = lib.expr_add(data, len(tree), 4, output, len(output))
        self.assertGreater(written, 0)
        self.assertEqual(lib.expr_sum(output, written), 21)
        self.assertEqual(bytes(data), original)
        second = (ctypes.c_ubyte * (len(tree) + 128))()
        written2 = lib.expr_add(data, len(tree), -2, second, len(second))
        self.assertGreater(written2, 0)
        self.assertEqual(lib.expr_sum(second, written2), 3)
        self.assertEqual(bytes(data), original)

    def test_small_capacity_rejected(self):
        lib = load()
        tree = lit(1)
        data = (ctypes.c_ubyte * len(tree)).from_buffer_copy(tree)
        output = (ctypes.c_ubyte * (len(tree) - 1))()
        self.assertLess(lib.expr_add(data, len(tree), 1, output, len(output)), 0)

if __name__ == '__main__': unittest.main()
