"""Execute the emitted floor guard at the real terrain edges and Earth position."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from compatibility import decode, encode, terrain_contact_guard

NAMES = ['position', 'sourceMap', 'x', 'z', 'width', 'height', 'contact']
def named(op, name):
    return encode(op, 2, NAMES.index(name))

def touches_floor(x, z, width=64, height=64):
    contact = encode(0x41, 1, 1) + named(0x4f, 'contact')
    code = terrain_contact_guard(named(0x49, 'position'), named, contact)
    globals_ = {'position': {'x': x, 'z': z}, 'sourceMap': {'width': width, 'height': height}, 'contact': False}
    ops = {op['pos']: op for op in decode(code)}
    stack, pc = [], 0
    while pc < len(code):
        op = ops[pc]; kind, value = op['op'], op['value']; next_pc = pc + len(op['raw'])
        if kind == 0x41: stack.append(value)
        elif kind == 0x49: stack.append(globals_[NAMES[value]])
        elif kind == 0x61: stack.append(stack.pop()[NAMES[value]])
        elif kind == 0x4f: globals_[NAMES[value]] = stack.pop()
        elif kind == 0x09: stack.append(-stack.pop())
        elif kind == 0x55:
            if not stack.pop(): next_pc = pc + value
        else:
            b, a = stack.pop(), stack.pop()
            stack.append({0x04: lambda: a*b, 0x05: lambda: a+b, 0x06: lambda: a-b,
                          0x11: lambda: a>=b, 0x0d: lambda: a<=b, 0x12: lambda: bool(a and b)}[kind]())
        pc = next_pc
    assert not stack
    return globals_['contact']

class TerrainBoundsTests(unittest.TestCase):
    def test_spawn_and_all_mesh_edges_keep_contact(self):
        for x, z in [(1000,1000),(0,0),(-19500,-19500),(18300,18300),(-19500,18300),(18300,-19500)]:
            with self.subTest(x=x,z=z): self.assertTrue(touches_floor(x,z))

    def test_no_invisible_floor_beyond_any_edge_or_at_earth(self):
        for x, z in [(-19500.01,0),(18300.01,0),(0,-19500.01),(0,18300.01),(16342.9,-32853.2),(-1e6,1e6)]:
            with self.subTest(x=x,z=z): self.assertFalse(touches_floor(x,z))

    def test_bounds_follow_each_heightmap_dimension(self):
        self.assertTrue(touches_floor(-15300,-12900,width=8,height=12))
        self.assertFalse(touches_floor(-15299,-12900,width=8,height=12))
        self.assertFalse(touches_floor(-15300,-12899,width=8,height=12))
