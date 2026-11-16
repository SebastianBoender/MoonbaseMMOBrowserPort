"""Branch relocation checks for inserting compatibility instructions."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from compatibility import decode, encode, insert_bytecode


class BranchRelocationTests(unittest.TestCase):
    def test_forward_branch_widens_when_insertion_exceeds_byte_operand(self):
        code = encode(0x53, 1, 255) + b'\x01' * 254
        result = insert_bytecode(code, {100: b'\x01' * 10})
        jump = decode(result)[0]
        self.assertEqual(jump['width'], 2)
        self.assertEqual(jump['value'], len(result) - 1)
        self.assertEqual(result[jump['value']], 1)

    def test_backward_branch_reaches_inserted_loop_entry(self):
        code = b'\x01' * 10 + encode(0x54, 1, 10)
        result = insert_bytecode(code, {0: b'\x03' * 3})
        jump = decode(result)[-1]
        self.assertEqual(jump['pos'] - jump['value'], 0)
        self.assertEqual(result[:3], b'\x03' * 3)

    def test_rejects_insertion_inside_an_operand(self):
        with self.assertRaises(AssertionError):
            insert_bytecode(encode(0x41, 2, 1000), {1: b'\x01'})


if __name__ == '__main__':
    unittest.main()
