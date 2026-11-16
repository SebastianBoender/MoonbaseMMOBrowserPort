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
    def named(opcode, name):
        return encode(opcode, 2, names.index(name))
    def scene_ref(kind, literal):
        return named(0x49, 'sp') + encode(0x44, 1, literal) + bytes.fromhex('4302') + named(0x67, kind)
    def literal_for(text):
        for literal_index in range(literal_count):
            kind, relative = struct.unpack_from('>II', script, literal_table + literal_index * 8)
            if kind != 1:
                continue
            length = struct.unpack_from('>I', script, literal_data + relative)[0]
            if script[literal_data + relative + 4:literal_data + relative + 3 + length] == text.encode('mac_roman'):
                return encode(0x44, 1 if literal_index < 256 else 2, literal_index)
        raise ValueError(f'Missing game literal: {text}')
    walk_body = named(0x49, 'havok') + literal_for('Walk') + bytes.fromhex('4302') + named(0x67, 'rigidBody')
    def body_ref(name):
        return named(0x49, 'havok') + literal_for(name) + bytes.fromhex('4302') + named(0x67, 'rigidBody')
    def vector_at_y(source, y):
        return source + named(0x61, 'x') + y + source + named(0x61, 'z') + bytes.fromhex('4303') + named(0x57, 'vector')
    def ground_contact(body, offset, flag):
        height = named(0x49, 'browserGroundHeight')
        position = body + named(0x61, 'position')
        velocity = body + named(0x61, 'linearVelocity')
        sample = position + b'\x03' + bytes.fromhex('4302') + named(0x57, 'checkheight') + encode(0x41, 1, offset) + b'\x05' + named(0x4f, 'browserGroundHeight')
        floor = (body + vector_at_y(position, height) + named(0x62, 'position') +
                 body + vector_at_y(velocity, b'\x03') + named(0x62, 'linearVelocity') +
                 bytes.fromhex('4101') + named(0x50, flag))
        grounded = position + named(0x61, 'y') + height + b'\x0d' + velocity + named(0x61, 'y') + b'\x03\x0d\x12'
        return sample + grounded + encode(0x55, 2, len(floor) + 3) + floor
    rocket = scene_ref('modelResource', 196) + named(0x61, 'emitter')
    # The existing "Particle" texture name also names the independent second
    # particle resource; textures and model resources have separate namespaces.
    rocket_right = scene_ref('modelResource', 211) + named(0x61, 'emitter')
    for index in range(count):
        record = table + index * 46
        name_id = struct.unpack_from('>H', script, record)[0]
        size, start = struct.unpack_from('>II', script, record + 4)
        code = bytes(script[start:start + size])
        # Exact byte signatures pin adaptations to this game's handlers.
        if name_id == names.index('beginSprite') and size == 1139:
            initialize = (bytes.fromhex('43001e') + encode(0x4f, 2, names.index('browserConsole')) +
                          bytes([0x03]) + encode(0x4f, 2, names.index('browserConsoleVersion')) +
                          bytes.fromhex('4b00') + encode(0x4f, 2, names.index('browserGameplay')) +
                          b'\x03' + named(0x4f, 'browserCartYaw'))
            adapted = insert_bytecode(code, {0: initialize})
            label = 'beginSprite: initialize bounded browser console mirror'
        elif name_id == names.index('prepareFrame'):
            assert code[220:224] == bytes.fromhex('49534ab2') and code[235:237] == bytes.fromhex('67b4')
            # Park both pieces when this client is not driving. The runtime's
            # Z-up contacts otherwise accelerate the unattended Y-up vehicle.
            parked = bytearray()
            zero = b'\x03\x03\x03' + bytes.fromhex('4303') + named(0x57, 'vector')
            for body_name in ['Car', 'Spring']:
                body = body_ref(body_name)
                for prop in ['linearVelocity', 'angularVelocity']:
                    parked.extend(body + zero + named(0x62, prop))
            driving = named(0x49, 'AvatarMode') + literal_for('Driving') + b'\x0f'
            park_if_idle = driving + encode(0x55, 2, 6) + encode(0x53, 2, len(parked) + 3) + parked
            contacts = ground_contact(body_ref('Car'), 50, 'OnGround')
            car = body_ref('Car')
            spring = body_ref('Spring')
            position = car + named(0x61, 'position')
            velocity = car + named(0x61, 'linearVelocity')
            # Keep the original DrivePlayer impulses and steering. Integrate
            # their result in Y-up coordinates without sending the cart through
            # the runtime's incompatible Z-up collision/suspension solver.
            # Reuse the authored floating-point 0.022 literal: integer 22/1000
            # truncates to zero when FrameMod is the integer stall cap.
            dt = named(0x4a, 'FrameMod') + bytes.fromhex('443404')
            accelerate = car + velocity + named(0x49, 'havok') + named(0x61, 'gravity') + dt + b'\x04\x05' + named(0x62, 'linearVelocity')
            advance = car + position + velocity + dt + b'\x04\x05' + named(0x62, 'position')
            yaw = named(0x49, 'browserCartYaw')
            angular = car + named(0x61, 'angularVelocity') + named(0x61, 'y')
            y_axis = b'\x03' + bytes.fromhex('4101') + b'\x03' + bytes.fromhex('4303') + named(0x57, 'vector')
            yaw_step = yaw + angular + dt + b'\x04' + bytes.fromhex('81023d04410a07') + b'\x05' + named(0x4f, 'browserCartYaw')
            rotation = yaw_step + car + y_axis + yaw + bytes.fromhex('43021e') + named(0x62, 'rotation')
            drive_step = accelerate + advance + contacts + rotation
            vehicle_step = driving + encode(0x55, 2, len(drive_step) + 3) + drive_step
            # Spring carries the seat/body mesh. Follow the chassis as one
            # stable assembly until native Y-up articulated physics is available.
            offset = b'\x03' + bytes.fromhex('410a') + b'\x03' + bytes.fromhex('4303') + named(0x57, 'vector')
            vehicle_step += spring + position + offset + b'\x05' + named(0x62, 'position')
            vehicle_step += spring + car + named(0x61, 'rotation') + named(0x62, 'rotation')
            for body in [car, spring]:
                vehicle_step += body + b'\x03' + named(0x62, 'active')
            # The native ball still uses Z-up collision contacts. Keep original
            # kick impulses, then integrate against the original Y-up terrain.
            # Eight small steps bound travel per floor query even after a stall.
            ball = named(0x49, 'browserBall')
            bp = ball + named(0x61, 'position')
            bv = ball + named(0x61, 'linearVelocity')
            bh = named(0x49, 'browserBallHeight')
            bounce = named(0x49, 'browserBallBounce')
            drag = named(0x49, 'browserBallDrag')
            speed = named(0x49, 'browserBallSpeed')
            sub_dt = dt + bytes.fromhex('410807')
            def distance_from_zero(value):
                return value + zero + bytes.fromhex('4302') + named(0x67, 'distanceTo')
            measure = distance_from_zero(bv) + named(0x4f, 'browserBallSpeed')
            limit = ball + bv + encode(0x41, 2, 700) + speed + b'\x07\x04' + named(0x62, 'linearVelocity')
            cap_speed = measure + speed + encode(0x41, 2, 700) + b'\x10' + encode(0x55, 2, len(limit) + 3) + limit
            gravity = named(0x49, 'havok') + named(0x61, 'gravity')
            integrate = (ball + bv + gravity + sub_dt + b'\x04\x05' + named(0x62, 'linearVelocity') + cap_speed +
                         ball + bp + bv + sub_dt + b'\x04\x05' + named(0x62, 'position'))
            height = bp + b'\x03' + bytes.fromhex('4302') + named(0x57, 'checkheight') + bytes.fromhex('415005') + named(0x4f, 'browserBallHeight')
            # Correct penetration in either direction, but only bounce a real
            # downward impact. Small impacts settle rather than gaining energy.
            up_speed = b'\x03' + bv + named(0x61, 'y') + bytes.fromhex('4302') + named(0x57, 'max') + named(0x4f, 'browserBallBounce')
            rebound = bv + named(0x61, 'y') + b'\x09' + ball + named(0x61, 'restitution') + b'\x04' + named(0x4f, 'browserBallBounce')
            bounce_if_falling = bv + named(0x61, 'y') + bytes.fromhex('410a090c') + encode(0x55, 2, len(rebound) + 3) + rebound
            horizontal_speed = bytes.fromhex('4101') + distance_from_zero(vector_at_y(bv, b'\x03')) + bytes.fromhex('4302') + named(0x57, 'max')
            # Coulomb friction: remove at most mu * |g| * dt from ground speed.
            resistance = (b'\x03' + bytes.fromhex('4101') + ball + named(0x61, 'friction') + distance_from_zero(gravity) + b'\x04' + sub_dt + b'\x04' + horizontal_speed + b'\x07\x06' + bytes.fromhex('4302') + named(0x57, 'max') + named(0x4f, 'browserBallDrag'))
            stopped_velocity = (ball + bv + named(0x61, 'x') + drag + b'\x04' + bounce + bv + named(0x61, 'z') + drag + b'\x04' + bytes.fromhex('4303') + named(0x57, 'vector') + named(0x62, 'linearVelocity'))
            floor = (ball + vector_at_y(bp, bh) + named(0x62, 'position') + up_speed + bounce_if_falling + resistance + stopped_velocity)
            contact = bp + named(0x61, 'y') + bh + b'\x0d' + encode(0x55, 2, len(floor) + 3) + floor
            ball_step = (integrate + height + contact) * 8 + ball + b'\x03' + named(0x62, 'active')
            # Snapshot existing players and their head anchors. Reading
            # globals avoids executing debug expressions on every UI poll.
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
            # The runtime uses a model's local transform as an emitter origin
            # and keeps one particle system per resource. Supply world regions
            # for both nozzles and mirror the original thrust switch.
            for emitter, nozzle in [(rocket, 213), (rocket_right, 214)]:
                snapshot.extend(emitter + scene_ref('model', nozzle) + named(0x61, 'worldPosition') + named(0x62, 'region'))
            snapshot.extend(rocket_right + rocket + named(0x61, 'loop') + named(0x62, 'loop'))
            start_particles = b''.join(emitter + bytes.fromhex('4114') + named(0x62, 'numParticles') for emitter in (rocket, rocket_right))
            snapshot.extend(rocket + named(0x61, 'loop') + encode(0x55, 2, len(start_particles) + 3) + start_particles)
            assert code[-1:] == b'\x01'
            adapted = insert_bytecode(code, {0: park_if_idle + contacts, 220: vehicle_step + ball_step, len(code) - 1: bytes(snapshot)})
            label = 'prepareFrame: Y-up cart and soccer ball, nameplates and original twin jetpack emitters'
        elif name_id == names.index('MakeRocketPack'):
            assert size == 359 and code[44:48] == bytes.fromhex('492244c4')
            assert code[287:291] == bytes.fromhex('492244d5')
            # Duplicate the original resource setup verbatim, changing only its
            # resource-name literal. Preserve the original particle texture,
            # colors, speeds, size, opacity, lifetime and nozzle transforms.
            second = b''.join(encode(0x44, op['width'], 211) if op['op'] == 0x44 and op['value'] == 196 else op['raw']
                              for op in decode(code[44:287]))
            assign_right = scene_ref('model', 214) + scene_ref('modelResource', 211) + named(0x62, 'resource')
            quiet_start = b''.join(emitter + b'\x03' + named(0x62, 'numParticles') for emitter in (rocket, rocket_right))
            adapted = insert_bytecode(code, {44: second, 358: assign_right + quiet_start})
            label = 'MakeRocketPack: use independent original particle resources for left and right nozzles'
        elif name_id == names.index('SetupPhysics'):
            # Native mesh resting contacts are Z-up; Moonbase's terrain and
            # gravity are Y-up. WalkPlayer supplies the original heightfield
            # floor instead of letting this mismatched contact slide the body.
            disable = named(0x49, 'havok') + literal_for('Walk') + literal_for('GroundShape') + bytes.fromhex('4203') + named(0x67, 'disableCollision')
            # Native dashpots mutate even inactive bodies. Disable these two
            # actions when the seat follows the chassis in the Y-up fallback.
            for kind, constraint in [('linearDashpot', 'mydashpot'), ('angularDashpot', 'myandashpot')]:
                disable += named(0x49, 'havok') + literal_for(constraint) + bytes.fromhex('4302') + named(0x67, kind) + b'\x03' + named(0x62, 'strength')
            disable += body_ref('TheBall') + named(0x4f, 'browserBall')
            assert code[-1:] == b'\x01'
            adapted = insert_bytecode(code, {len(code) - 1: disable})
            label = 'SetupPhysics: Y-up walking contact and disable native vehicle dashpots for the cart fallback'
        elif name_id == names.index('WalkPlayer'):
            adapted = insert_bytecode(code, {0: ground_contact(walk_body, 50, 'ongroundwalk')})
            label = 'WalkPlayer: restore Y-up ground contact and original idle braking; preserve airborne momentum'
        elif name_id == names.index('FramerateTest'):
            # Avoid a background-tab stall producing a multi-second Havok step
            # and one enormous steering/rocket impulse on return.
            limits = [op for op in decode(code) if op['op'] == 0x41 and op['value'] == 99]
            assert len(limits) == 2
            adapted = b''.join(encode(op['op'], op['width'], 9) if op in limits else op['raw'] for op in decode(code))
            label = 'FramerateTest: cap frame-resume simulation increments to 60ms instead of 660ms'
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
            reset_viewport = b''.join(bytes.fromhex('41014301575003') + named(0x62, prop) for prop in ['rotation', 'skew'])
            puppet = (bytes.fromhex('4104430157504101') +
                      encode(0x62, 2, names.index('puppet')))
            panel = b''.join(
                encode(0x41, 1, channel) + bytes.fromhex('43015750') +
                encode(0x49, 2, names.index('AvatarMode')) +
                encode(0x44, 1, 51) + bytes([0x0f]) +
                encode(0x62, 1, names.index('visible'))
                for channel in range(2, 18))
            adapted = insert_bytecode(code, {24: reset_viewport + puppet + code[146:179] + panel})
            label = 'CheckWindowRescale: reset viewport skew/rotation, keep gravity knob on track and setup panel visibility'
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
    assert len(changes) == 9
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
        # Keep the original TextColor with each line, after its default is set.
        append = buffer + bytes.fromhex('4b004b0143021e4202') + encode(0x57, 1, names.index('add'))
        delete = buffer + bytes.fromhex('41014202') + encode(0x67, 2, names.index('deleteAt'))
        trim = (buffer + encode(0x61, 1, names.index('count')) + bytes.fromhex('416410') +
                encode(0x55, 1, len(delete) + 2) + delete)
        mirror = append + trim + version_get + bytes.fromhex('410105') + version_set
        adapted = insert_bytecode(code, {39: mirror})
        struct.pack_into('>II', script, record + 4, len(adapted), len(script))
        script.extend(adapted)
        return {'handler': 'PrintToConsole', 'capacity': 100,
                'change': 'Mirror game console text and original colors in browserConsole with a monotonic sequence',
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
    names.extend(['browserConsole', 'browserConsoleVersion', 'browserLabels', 'browserGameplay', 'browserGroundHeight', 'browserCartYaw', 'browserBall', 'browserBallHeight', 'browserBallBounce', 'browserBallDrag', 'browserBallSpeed'])
    for name in ['getAt', 'region']:
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
