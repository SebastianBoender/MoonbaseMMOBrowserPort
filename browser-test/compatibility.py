"""Reversible Director movie adapter for DirPlayer 0.8.1 compatibility.

getPixel(image, x, y, #integer) calls in the terrain script are rewritten
to getPixel(image, point(x, y), #integer). Both express the same Director read;
the point variant is the one whose integer flag DirPlayer currently honors.
The adapter also bridges callback/timing differences, synchronizes the walking
camera, and keeps the scripted gravity thumb independent of score tweening.
"""
import hashlib
import json
from pathlib import Path
import struct


def decode(code):
    ops = []
    pos = 0
    while pos < len(code):
        raw = code[pos]
        width = 4 if raw >= 0xC0 else 2 if raw >= 0x80 else 1 if raw >= 0x40 else 0
        if pos + 1 + width > len(code):
            raise ValueError("Truncated instruction")
        ops.append({"pos": pos, "op": 0x40 + raw % 0x40 if width else raw,
                    "width": width, "value": int.from_bytes(code[pos + 1:pos + 1 + width], 'big'),
                    "raw": code[pos:pos + 1 + width]})
        pos += 1 + width
    return ops


def encode(op, width, value):
    raw = op if width == 0 else op + {1: 0, 2: 0x40, 4: 0x80}[width]
    return bytes([raw]) + value.to_bytes(width, 'big')


def rewrite(code, point_id, pixel_id, integer_id):
    ops = decode(code)
    points = set()
    argc_positions = set()
    for index in range(len(ops) - 2):
        flag, args, call = ops[index:index + 3]
        if ((flag['op'], flag['value']) == (0x45, integer_id)
            and (args['op'], args['value']) == (0x43, 4)
            and (call['op'], call['value']) == (0x57, pixel_id)):
            points.add(flag['pos'])
            argc_positions.add(args['pos'])
    if not points:
        return code, []
    point_call = encode(0x43, 1, 2) + encode(0x57, 1 if point_id < 256 else 2, point_id)
    original_targets = {}
    for op in ops:
        if op['op'] in (0x53, 0x54, 0x55):
            target = op['pos'] + (-op['value'] if op['op'] == 0x54 else op['value'])
            if target not in {o['pos'] for o in ops} | {len(code)}:
                raise ValueError("Original jump is not on an instruction boundary")
            original_targets[op['pos']] = target
    # Widen jump operands if necessary; layout converges because widths only grow.
    for _ in range(8):
        cursor = 0
        mapping = {}
        for op in ops:
            mapping[op['pos']] = cursor
            cursor += len(point_call) if op['pos'] in points else 0
            op['new_pos'] = cursor
            cursor += 1 + op['width']
        mapping[len(code)] = cursor
        changed = False
        for op in ops:
            if op['pos'] not in original_targets:
                continue
            delta = mapping[original_targets[op['pos']]] - op['new_pos']
            value = -delta if op['op'] == 0x54 else delta
            if value < 0:
                raise ValueError("Unexpected jump direction")
            if value >= 1 << (8 * op['width']):
                op['width'] = 2 if op['width'] == 1 else 4
                changed = True
            op['new_value'] = value
        if not changed:
            break
    else:
        raise ValueError("Jump layout did not converge")
    output = bytearray()
    for op in ops:
        if op['pos'] in points:
            output.extend(point_call)
        value = 3 if op['pos'] in argc_positions else op.get('new_value', op['value'])
        # Unchanged instructions retain their exact encoding, including signed literals.
        output.extend(encode(op['op'], op['width'], value))
    rewritten = decode(output)
    boundaries = {op['pos'] for op in rewritten} | {len(output)}
    for op in rewritten:
        if op['op'] in (0x53, 0x54, 0x55):
            target = op['pos'] + (-op['value'] if op['op'] == 0x54 else op['value'])
            assert target in boundaries
    return bytes(output), sorted(points)


def insert_bytecode(code, insertions):
    """Insert complete instructions and relocate forward/backward branches."""
    ops = decode(code)
    boundaries = {o['pos'] for o in ops} | {len(code)}
    assert set(insertions) <= boundaries
    targets = {o['pos']: o['pos'] + (-o['value'] if o['op'] == 0x54 else o['value'])
               for o in ops if o['op'] in (0x53, 0x54, 0x55)}
    assert set(targets.values()) <= boundaries
    for _ in range(8):
        mapping, cursor = {}, 0
        for o in ops:
            mapping[o['pos']] = cursor
            cursor += len(insertions.get(o['pos'], b''))
            o['new_pos'] = cursor
            cursor += 1 + o['width']
        mapping[len(code)] = cursor
        widened = False
        for o in ops:
            if o['pos'] not in targets:
                continue
            delta = mapping[targets[o['pos']]] - o['new_pos']
            o['new_value'] = -delta if o['op'] == 0x54 else delta
            assert o['new_value'] >= 0
            if o['new_value'] >= 1 << (8 * o['width']):
                o['width'] = 2 if o['width'] == 1 else 4
                widened = True
        if not widened:
            break
    else:
        raise ValueError('Branch relocation did not converge')
    result = b''.join(insertions.get(o['pos'], b'') + encode(o['op'], o['width'], o.get('new_value', o['value'])) for o in ops)
    assert all(t in {o['pos'] for o in decode(result)} | {len(result)}
               for t in [o['pos'] + (-o['value'] if o['op'] == 0x54 else o['value'])
                         for o in decode(result) if o['op'] in (0x53, 0x54, 0x55)])
    return result


def adapt_gameplay(script, names):
    # Pin the literal used by the visibility comparison, just as the byte
    # signatures below pin the handlers. Avoid silently adapting another movie.
    literal_count, literal_table = struct.unpack_from('>HI', script, 78)
    literal_data = struct.unpack_from('>I', script, 88)[0]
    assert literal_count > 51
    literal_type, literal_offset = struct.unpack_from('>II', script, literal_table + 51 * 8)
    literal_size = struct.unpack_from('>I', script, literal_data + literal_offset)[0]
    assert literal_type == 1
    assert script[literal_data + literal_offset + 4:literal_data + literal_offset + 3 + literal_size] == b'CharacterSetup'
    count, table = struct.unpack_from('>HI', script, 72)
    changes = []
    for index in range(count):
        record = table + index * 46
        name_id = struct.unpack_from('>H', script, record)[0]
        size, start = struct.unpack_from('>II', script, record + 4)
        code = bytes(script[start:start + size])
        # Exact byte signatures pin adaptations to this game's handlers.
        if name_id == names.index('beginSprite') and size == 1139:
            initialize = (bytes.fromhex('43001e') + encode(0x4f, 2, names.index('browserConsole')) +
                          bytes([0x03]) + encode(0x4f, 2, names.index('browserConsoleVersion')) +
                          bytes.fromhex('4b00') + encode(0x4f, 2, names.index('browserGameplay')))
            adapted = insert_bytecode(code, {0: initialize})
            label = 'beginSprite: initialize bounded browser console mirror'
        elif name_id == names.index('prepareFrame'):
            # Snapshot existing players and their head anchors. Reading
            # globals avoids executing debug expressions on every UI poll.
            def named(opcode, name):
                return encode(opcode, 2, names.index(name))
            head = bytes.fromhex('41008100cd41004303') + named(0x57, 'vector')
            buffer = named(0x49, 'browserLabels')
            snapshot = bytearray(bytes.fromhex('43001e') + named(0x4f, 'browserLabels'))
            def append_label(name, position):
                entry = name + position + head + b'\x05' + bytes.fromhex('43021e')
                return buffer + entry + bytes.fromhex('4202') + named(0x57, 'add')
            snapshot.extend(append_label(named(0x49, 'PlayerName'), named(0x49, 'PlayerModel') + named(0x61, 'worldPosition')))
            for player_index in range(1, 26):
                def item(global_name):
                    return named(0x49, global_name) + encode(0x41, 1, player_index) + bytes.fromhex('4302') + named(0x57, 'getAt')
                position = named(0x49, 'sp') + item('usercode') + bytes.fromhex('4302') + named(0x67, 'model') + named(0x61, 'worldPosition')
                append = append_label(item('userpname'), position)
                snapshot.extend(named(0x49, 'usercode') + named(0x61, 'count') + encode(0x41, 1, player_index) + b'\x11' +
                                encode(0x55, 2, len(append) + 3) + append)
            assert code[-1:] == b'\x01'
            adapted = insert_bytecode(code, {len(code) - 1: bytes(snapshot)})
            label = 'prepareFrame: snapshot player names and world-space head anchors for browser text'
        elif code[292:296] == bytes.fromhex('67bd520c') and size == 641:
            # Reassigning the moved body's position invokes the runtime's W3D
            # synchronization path, which attemptMoveTo currently omits.
            sync = bytes.fromhex('4c054c0561616261')
            adapted = insert_bytecode(code, {294: sync})
            label = 'MoveCamera: collision-aware attemptMoveTo and W3D position synchronization'
        elif size == 800 and code[146:152] == bytes.fromhex('410443015750'):
            # Score position tweening overwrites script-controlled loc each
            # frame unless the channel is puppeted. Reapply the original
            # formula before the unchanged-size early return as well.
            puppet = (bytes.fromhex('4104430157504101') +
                      encode(0x62, 2, names.index('puppet')))
            panel = b''.join(
                encode(0x41, 1, channel) + bytes.fromhex('43015750') +
                encode(0x49, 2, names.index('AvatarMode')) +
                encode(0x44, 1, 51) + bytes([0x0f]) +
                encode(0x62, 1, names.index('visible'))
                for channel in range(2, 18))
            adapted = insert_bytecode(code, {24: puppet + code[146:179] + panel})
            label = 'CheckWindowRescale: keep gravity knob on track and show setup panel only in CharacterSetup'
        elif name_id == names.index('endSprite'):
            unpuppet = (bytes.fromhex('4104430157504100') +
                        encode(0x62, 2, names.index('puppet')))
            restore_panel = b''.join(encode(0x41, 1, channel) +
                bytes.fromhex('430157504101') + encode(0x62, 1, names.index('visible'))
                for channel in range(2, 18))
            adapted = insert_bytecode(code, {0: unpuppet + restore_panel})
            label = 'endSprite: release gravity knob score channel and restore menu channel visibility'
        else:
            continue
        struct.pack_into('>II', script, record + 4, len(adapted), len(script))
        script.extend(adapted)
        changes.append({'name_id': name_id, 'change': label,
                        'original_sha256': hashlib.sha256(code).hexdigest(),
                        'adapted_sha256': hashlib.sha256(adapted).hexdigest()})
    assert len(changes) == 5
    for position in (8, 12):
        struct.pack_into('>I', script, position, len(script))
    return changes


def adapt_console(script, names):
    """Mirror actual PrintToConsole output; retain the original network/terms logic."""
    count, table = struct.unpack_from('>HI', script, 72)
    for index in range(count):
        record = table + index * 46
        if struct.unpack_from('>H', script, record)[0] != names.index('PrintToConsole'):
            continue
        size, start = struct.unpack_from('>II', script, record + 4)
        code = bytes(script[start:start + size])
        assert size == 292 and code[14:16] == bytes.fromhex('4b01')
        buffer = encode(0x49, 2, names.index('browserConsole'))
        version_get = encode(0x49, 2, names.index('browserConsoleVersion'))
        version_set = encode(0x4f, 2, names.index('browserConsoleVersion'))
        append = buffer + bytes.fromhex('4b004202') + encode(0x57, 1, names.index('add'))
        delete = buffer + bytes.fromhex('41014202') + encode(0x67, 2, names.index('deleteAt'))
        trim = (buffer + encode(0x61, 1, names.index('count')) + bytes.fromhex('416410') +
                encode(0x55, 1, len(delete) + 2) + delete)
        mirror = append + trim + version_get + bytes.fromhex('410105') + version_set
        adapted = insert_bytecode(code, {39: mirror})
        struct.pack_into('>II', script, record + 4, len(adapted), len(script))
        script.extend(adapted)
        return {'handler': 'PrintToConsole', 'capacity': 100,
                'change': 'Mirror game console strings in browserConsole with a monotonic sequence',
                'original_sha256': hashlib.sha256(code).hexdigest(),
                'adapted_sha256': hashlib.sha256(adapted).hexdigest()}
    raise ValueError('PrintToConsole handler missing')


def adapt_multiuser(script, names):
    """Adapt Moonbase's automatic filtered callbacks to DirPlayer's queue API."""
    count, table = struct.unpack_from('>HI', script, 72)
    handlers = {}
    for index in range(count):
        record = table + index * 46
        name_id = struct.unpack_from('>H', script, record)[0]
        size, start = struct.unpack_from('>II', script, record + 4)
        handlers[names[name_id]] = (index, record, bytes(script[start:start + size]))
    def op(code, value):
        return encode(code, 1 if value < 256 else 2, value)
    _, setup_record, setup_code = handlers['makeAServerConnection']
    setup_ops = decode(setup_code)
    registrations = []
    replacement = bytearray(setup_code)
    for i, instruction in enumerate(setup_ops):
        if instruction['op'] != 0x67 or instruction['value'] != names.index('setNetMessageHandler'):
            continue
        group = setup_ops[i - 9:i + 1]
        # Receiver, handler symbol, script(...), subject, sender, mode, arglist, call.
        symbol = group[0] if group[0]['op'] == 0x45 else group[1]
        assert symbol['op'] == 0x45
        subject = setup_ops[i - 4]
        assert subject['op'] == 0x44
        handler = names[symbol['value']]
        registrations.append((handler, subject['value']))
        encoded = encode(0x45, symbol['width'], names.index('DefaultMessageHandler'))
        replacement[symbol['pos']:symbol['pos'] + len(symbol['raw'])] = encoded
    assert len(registrations) == 13
    assert len(replacement) == len(setup_code)
    struct.pack_into('>II', script, setup_record + 4, len(replacement), len(script))
    script.extend(replacement)
    _, record, original = handlers['DefaultMessageHandler']
    assert original[:2] == bytes.fromhex('4b01') and original[19:21] == bytes.fromhex('4b01')
    prefix = (op(0x49, names.index('gmultiuserinstance')) + op(0x43, 1)
              + op(0x67, names.index('getNetMessage')) + op(0x51, 1))
    router = bytearray()
    routes = []
    for handler, literal in registrations[1:]:
        if handler not in handlers:
            continue  # The packaged game has no DailyMessageHandler implementation.
        body = (op(0x4b, 0) + op(0x4b, 1) + op(0x42, 2)
                + op(0x56, handlers[handler][0]) + b'\x01')
        router.extend(op(0x4b, 1) + op(0x61, names.index('subject')) + op(0x44, literal)
                      + b'\x0f' + op(0x55, 2 + len(body)) + body)
        routes.append(handler)
    adapted = prefix + original[:19] + router + original[19:]
    struct.pack_into('>II', script, record + 4, len(adapted), len(script))
    script.extend(adapted)
    for code in (bytes(replacement), adapted):
        instructions = decode(code)
        boundaries = {item['pos'] for item in instructions} | {len(code)}
        for item in instructions:
            if item['op'] in (0x53, 0x54, 0x55):
                target = item['pos'] + (-item['value'] if item['op'] == 0x54 else item['value'])
                assert target in boundaries
    return {'callback': 'DefaultMessageHandler', 'registrations': len(registrations),
            'routes': routes, 'source': 'Actual Multiuser getNetMessage() queue',
            'original_handler_sha256': hashlib.sha256(original).hexdigest(),
            'adapted_handler_sha256': hashlib.sha256(adapted).hexdigest()}


def prepare(root):
    game = root / 'public' / 'game'
    original = (game / 'moonbase.dir').read_bytes()
    movie = bytearray(original)
    mmap = struct.unpack_from('<I', movie, 24)[0]
    header, stride, allocated, used = struct.unpack_from('<HHII', movie, mmap + 8)
    resources = {}
    for i in range(used):
        entry = mmap + 8 + header + i * stride
        resources[i] = (entry, *struct.unpack_from('<II', movie, entry + 4))
    # This exact package's internal Lnam and MakeTheTerrain Lscr resource IDs.
    _, length, offset = resources[1059]
    names_data = movie[offset + 8:offset + 8 + length]
    cursor, count = struct.unpack_from('>HH', names_data, 16)
    names = []
    casing_patches = []
    for _ in range(count):
        length = names_data[cursor]
        name = names_data[cursor + 1:cursor + 1 + length].decode('mac_roman')
        names.append(name)
        if name == 'RigidBody':
            # Director names are case-insensitive; this runtime's Havok
            # dispatcher accepts rigidBody/rigidbody but rejects RigidBody.
            movie[offset + 8 + cursor + 1:offset + 8 + cursor + 1 + length] = b'rigidBody'
            casing_patches.append({'from': name, 'to': 'rigidBody', 'name_id': len(names)-1})
        cursor += 1 + length
    names.append('getNetMessage')
    names.append('puppet')
    names.extend(['browserConsole', 'browserConsoleVersion', 'browserLabels', 'browserGameplay'])
    for name in ['getAt']:
        if name not in names:
            names.append(name)
    names[names.index('RigidBody')] = 'rigidBody'
    camera_method_id = names.index('interpolatingMoveTo')
    names[camera_method_id] = 'attemptMoveTo'
    name_entry, name_length, name_offset = resources[1059]
    adapted_names = bytearray(names_data[:20])
    for name in names:
        encoded = name.encode('mac_roman')
        adapted_names.extend(bytes([len(encoded)]) + encoded)
    adapted_names.extend(names_data[cursor:])
    struct.pack_into('>H', adapted_names, 18, len(names))
    for position in [8, 12]:
        declared = struct.unpack_from('>I', adapted_names, position)[0]
        struct.pack_into('>I', adapted_names, position, declared + len(adapted_names) - len(names_data))
    point_id, pixel_id, integer_id = (names.index(name) for name in ['point', 'getPixel', 'integer'])
    entry, length, offset = resources[1062]
    assert movie[offset:offset + 4] == b'rcsL'
    script = bytearray(movie[offset + 8:offset + 8 + length])
    count, handlers = struct.unpack_from('>HI', script, 72)
    patches = []
    for index in range(count):
        record = handlers + index * 46  # capital-X LctX handler records
        name_id = struct.unpack_from('>H', script, record)[0]
        code_length, code_offset = struct.unpack_from('>II', script, record + 4)
        code = bytes(script[code_offset:code_offset + code_length])
        replacement, positions = rewrite(code, point_id, pixel_id, integer_id)
        if positions:
            new_offset = len(script)
            script.extend(replacement)
            struct.pack_into('>II', script, record + 4, len(replacement), new_offset)
            patches.append({'handler': names[name_id], 'original_positions': positions,
                'original_code_sha256': hashlib.sha256(code).hexdigest(),
                'adapted_code_sha256': hashlib.sha256(replacement).hexdigest()})
    if {p['handler'] for p in patches} != {'makeTerrain', 'checkheight'}:
        raise ValueError(f"Unexpected patch sites: {patches}")
    if sorted(len(p['original_positions']) for p in patches) != [1, 4] or len(casing_patches) != 1:
        raise ValueError('Unexpected integer-read or Havok alias patch count')
    for position in [8, 12]:
        struct.pack_into('>I', script, position, len(script))
    if len(movie) % 2:
        movie.append(0)
    new_offset = len(movie)
    movie.extend(b'rcsL' + struct.pack('<I', len(script)) + script)
    struct.pack_into('<II', movie, entry + 4, len(script), new_offset)
    # The seconds-resolution clock can repeat when browser VM timer callbacks
    # catch up after expensive 3D startup. Use its elapsed millisecond clock.
    clock_entry, clock_length, clock_offset = resources[1078]
    clock_script = bytearray(movie[clock_offset + 8:clock_offset + 8 + clock_length])
    clock_count, clock_handlers = struct.unpack_from('>HI', clock_script, 72)
    clock_patches = []
    for index in range(clock_count):
        record = clock_handlers + index * 46
        name_id = struct.unpack_from('>H', clock_script, record)[0]
        if names[name_id] != 'CheckTime':
            continue
        size, start = struct.unpack_from('>II', clock_script, record + 4)
        old_code = bytes(clock_script[start:start + size])
        if old_code[:4] != bytes.fromhex('41085c00'):
            raise ValueError('Unexpected CheckTime clock read')
        # All branches are wholly after the replaced prefix, so their relative
        # distances stay the same. No code target points into that prefix.
        for op in decode(old_code):
            if op['op'] in (0x53, 0x54, 0x55):
                target = op['pos'] + (-op['value'] if op['op'] == 0x54 else op['value'])
                assert op['pos'] >= 4 and target >= 4
        new_code = encode(0x5f, 1, names.index('milliSeconds')) + old_code[4:]
        struct.pack_into('>II', clock_script, record + 4, len(new_code), len(clock_script))
        clock_script.extend(new_code)
        clock_patches.append({'handler': 'CheckTime', 'from': 'the abbr time',
            'to': 'the milliSeconds', 'original_code_sha256': hashlib.sha256(old_code).hexdigest(),
            'adapted_code_sha256': hashlib.sha256(new_code).hexdigest()})
    assert len(clock_patches) == 1
    network_patch = adapt_multiuser(clock_script, names)
    console_patch = adapt_console(clock_script, names)
    for position in [8, 12]:
        struct.pack_into('>I', clock_script, position, len(clock_script))
    if len(movie) % 2:
        movie.append(0)
    clock_new_offset = len(movie)
    movie.extend(b'rcsL' + struct.pack('<I', len(clock_script)) + clock_script)
    struct.pack_into('<II', movie, clock_entry + 4, len(clock_script), clock_new_offset)
    gameplay_entry, gameplay_length, gameplay_offset = resources[1077]
    gameplay_script = bytearray(movie[gameplay_offset + 8:gameplay_offset + 8 + gameplay_length])
    gameplay_patches = adapt_gameplay(gameplay_script, names)
    if len(movie) % 2:
        movie.append(0)
    gameplay_new_offset = len(movie)
    movie.extend(b'rcsL' + struct.pack('<I', len(gameplay_script)) + gameplay_script)
    struct.pack_into('<II', movie, gameplay_entry + 4, len(gameplay_script), gameplay_new_offset)
    if len(movie) % 2:
        movie.append(0)
    name_new_offset = len(movie)
    movie.extend(b'manL' + struct.pack('<I', len(adapted_names)) + adapted_names)
    struct.pack_into('<II', movie, name_entry + 4, len(adapted_names), name_new_offset)
    struct.pack_into('<I', movie, 4, len(movie) - 8)
    struct.pack_into('<I', movie, resources[0][0] + 4, len(movie) - 8)
    # All unrelated live chunks remain exactly byte-identical.
    for resource_id, (slot, size, old_offset) in resources.items():
        if resource_id in (0, 2, 1059, 1062, 1077, 1078) or original[slot:slot + 4] in (b'eerf', b'knuj', b'\0\0\0\0'):
            continue
        assert original[old_offset:old_offset + 8 + size] == movie[old_offset:old_offset + 8 + size]
    (game / 'moonbase-browser.dir').write_bytes(movie)
    manifest = {'baseline_sha256': hashlib.sha256(original).hexdigest(),
        'adapted_sha256': hashlib.sha256(movie).hexdigest(),
        'reason': 'DirPlayer 0.8.1 ignores #integer with getPixel(image,x,y,flag).',
        'equivalent_rewrite': 'getPixel(image,point(x,y),#integer)', 'patches': patches,
        'case_insensitive_havok_aliases': casing_patches, 'clock_patches': clock_patches, 'multiuser_dispatch': network_patch, 'gameplay_patches': gameplay_patches,
        'camera_method_alias': {'name_id': camera_method_id, 'from': 'interpolatingMoveTo', 'to': 'attemptMoveTo'},
        'console_mirror': console_patch,
        'original_preserved': 'moonbase.dir'}
    (game / 'compatibility.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('Prepared reversible integer-pixel compatibility copy:', ', '.join(p['handler'] for p in patches))
