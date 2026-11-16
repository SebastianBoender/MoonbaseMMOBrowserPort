"""Compare measured projector/browser traces; exit nonzero on a mismatch."""
import argparse
import json
import math
from pathlib import Path
import re

NUMBER = re.compile(r'[-+]?(?:\d*\.\d+|\d+)(?:e[-+]?\d+)?', re.I)


def numbers(text):
    result = [float(x) for x in NUMBER.findall(text)]
    if not result or not all(math.isfinite(x) for x in result):
        raise ValueError('Missing or non-finite measurement')
    return result


def orientation(text):
    values = numbers(text)
    if len(values) != 4:
        raise ValueError('Expected an axis-angle measurement')
    axis, degrees = values[:3], values[3]
    length = math.sqrt(sum(x*x for x in axis))
    if not length:
        if degrees:
            raise ValueError('Nonzero rotation requires an axis')
        return [1, 0, 0, 0]
    angle = math.radians(degrees) / 2
    return [math.cos(angle)] + [x / length * math.sin(angle) for x in axis]


def distance(a, b, rotation=False):
    if rotation:
        qa, qb = orientation(a), orientation(b)
        dot = min(1, abs(sum(x*y for x, y in zip(qa, qb))))
        return math.degrees(2 * math.acos(dot))
    av, bv = numbers(a), numbers(b)
    if len(av) != 3 or len(bv) != 3:
        raise ValueError('Expected vector measurements')
    return math.dist(av, bv)


def canonical(trace):
    rows = trace['samples']
    if not rows:
        raise ValueError('Trace has no samples')
    for expected, row in enumerate(rows, 1):
        if row[0] != expected or len(row) != (11 if trace.get('details') else 9) + bool(trace.get('contacts')) + 3 * bool(trace.get('materials')):
            raise ValueError('Missing tick or malformed sample')
    return [[r[0], *r[1:5], *r[6:10]] for r in rows] if trace.get('details') else [r[:9] for r in rows]


def compare(reference, candidate, tolerance=0.001):
    if (reference['input'], reference['dt']) != (candidate['input'], candidate['dt']):
        raise ValueError('Input and timestep must match')
    if reference.get('spring_offset', 10) != candidate.get('spring_offset', 10):
        raise ValueError('Initial suspension separation must match')
    if reference.get('friction_override') != candidate.get('friction_override'):
        raise ValueError('Material overrides must match')
    original, browser = canonical(reference), canonical(candidate)
    if len(original) != len(browser):
        raise ValueError('Sample counts must match')
    fields = [f'{body}.{prop}' for body in ['Car', 'Spring']
              for prop in ['position', 'linearVelocity', 'angularVelocity', 'rotation']]
    result = {'samples': len(original), 'tolerance': tolerance, 'first_mismatch': None, 'fields': {}}
    for index, field in enumerate(fields, 1):
        errors = [distance(a[index], b[index], index in (4, 8)) for a, b in zip(original, browser)]
        first = next((i+1 for i, error in enumerate(errors) if error > tolerance), None)
        if first is not None:
            result['first_mismatch'] = min(result['first_mismatch'] or first, first)
        result['fields'][field] = {'maximum_error': max(errors),
                                  'rms_error': math.sqrt(sum(e*e for e in errors) / len(errors)),
                                  'first_mismatch': first}
    result['pass'] = result['first_mismatch'] is None
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference', type=Path)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('--tolerance', type=float, default=0.001,
                        help='Vector-unit / orientation-degree error tolerance')
    args = parser.parse_args()
    try:
        if not math.isfinite(args.tolerance) or args.tolerance <= 0:
            raise ValueError('Tolerance must be finite and positive')
        result = compare(json.loads(args.reference.read_text()), json.loads(args.candidate.read_text()), args.tolerance)
    except (ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['pass'] else 1)
