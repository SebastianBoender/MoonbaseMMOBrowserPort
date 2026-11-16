# Driving mechanics comparison

Audit: 16 November 2026, browser revision `4b7d2d4`.

The browser cart is a stability fallback, not a reproduction of the original Havok vehicle. The largest differences are suspension, terrain contact and collisions. Original input formulas survive, but they feed a different simulation.

## Evidence and limits

Compared the recovered original `public/game/moonbase.dir` against the generated `moonbase-browser.dir`, including the bytecode of the vehicle handlers, the decompiled handlers from the existing physics diagnostics, and the adapter in `browser-test/compatibility.py`. The original EXE was not run during this audit. Descriptions of downloadable-client physics below refer to the authored setup and intended Havok path; exact native acceleration times, stopping distances and turning radii still require measurement in that client.

| Handler | Original / browser bytes | Result |
| --- | ---: | --- |
| DrivePlayer | 869 / 869 | Identical bytecode |
| CheckCarFlipped | 580 / 580 | Identical bytecode |
| SetupPhysics | 1014 / 1067 | Adapted: suspension disabled |
| prepareFrame | 345 / 6770 | Adapted: cart and ball integration, contact workaround and UI snapshots |
| FramerateTest | 49 / 49 | Adapted: maximum FrameMod 99 becomes 9 |

Original DrivePlayer SHA-256: `f66908edd0128f855667edac2374e617b13faecbd2bd8b5c71175fa3a8c0c3b9`.
Original CheckCarFlipped SHA-256: `612c7e39779fa607ceb20ae9740d8e6d31c042892aa38a229c7ee129d02ae2b5`.

## What matches

These are authored game units, not measured real-world speeds:

- Forward target speed 700; acceleration impulse proportional to `(700 - forwardSpeed) * FrameMod * 0.04 * mass`.
- Reverse target speed −200; reverse acceleration uses `FrameMod * 0.1`.
- Space handbrake removes 5% of longitudinal velocity per grounded handler call, before other physics effects. It also disables the scripted lateral-grip impulse while held.
- Scripted lateral grip removes 10% of sideways velocity per grounded handler call.
- Steering impulses require speed above 100 or below −100; steering direction reverses when reversing.
- Angular-speed limit decreases toward top speed: `min(abs(speed), (1 - min(abs(speed)/700, 1)) * FrameMod * 3)`.
- Steering-wheel visual rotation, driving animation, exit key and original flip/fall recovery handler remain.

Identical bytecode does not establish identical acceleration, braking or steering feel: contact state, angular inertia, damping and the physics integrator determine the response to those impulses.

## What differs

| Mechanic | Authored downloadable-client path | Browser fallback | Consequence |
| --- | --- | --- | --- |
| Suspension | Separate Car and Spring bodies, linear dashpot strength 0.5/damping 0.03, angular dashpot strength 7/damping 0.5 | Both strengths zero; Spring position forced to Car + (0,10,0), with identical rotation | No spring compression, body bounce or suspension lag |
| Terrain posture | Full rigid-body rotation and mesh contacts | Rotation overwritten as a world-Y yaw; fixed height sample + 50 | Cart stays upright; cannot pitch/roll with slopes or reproduce normal flips |
| Collisions | Cart participates in the Havok world containing GroundShape, rocks, Ramp, Earth and other bodies | Car and Spring marked inactive for shared Havok stepping | Cart does not receive normal obstacle contacts or collision impulses |
| Translation | Havok integrates and resolves body contacts | One explicit gravity/velocity/position update per movie frame | Different settling, terrain transitions and potentially different grip/coasting |
| Grounded state | Original collision callback registered for Car | Heightfield floor workaround sets OnGround | Terrain-only traction; no genuine ramp or rock support |
| Rotation | Havok integrates angular motion and contacts | Separate browserCartYaw accumulator, converted to a Y-axis rotation | Only yaw survives; angular response depends on emulated impulse/inertia handling |
| Parking | Native physics body remains subject to the scene | Unattended cart velocities cleared and assembly parked | No unattended rolling or suspension movement |
| Long frames | Original FrameMod capped at 99 | Cap reduced to 9 for browser stall protection | Long stalls intentionally simulate less elapsed time |

The yaw expression multiplies by 573 and divides by 10: approximately radians-to-degrees (57.3). This is not an extra tenfold steering reduction and should not be "fixed" by removing that division.

## Additional concrete defect

`browserCartYaw` is initialized at world startup, but the original `CheckCarFlipped` reset rotates the cart to zero without resetting this separate accumulator. The next browser driving integration can restore the old heading after a flip/fall reset. Any replacement controller must synchronize its heading with authored recovery and entry/exit transitions.

## Recommended correction order

1. Record a native baseline on level ground at the same gravity: forward/reverse acceleration, coasting, Space braking, left/right circles at low/medium/high speed, handbrake turns, ramp landing, rock impacts and fall recovery. Record elapsed time, FPS, speed, yaw and travel distance where available. Repeat browser runs with identical input durations.
2. Replace the flat point-contact cart fallback with Y-up contact handling. Prefer fixing the native emulator's Y-up contacts and re-enabling its chassis/suspension. If that is impractical, use a vehicle controller with multiple support/contact samples, terrain orientation, suspension, obstacle collision and explicit airborne states. Native parity cannot come from changing speed constants alone.
3. Keep original drive/handbrake/grip rules as the reference, and calibrate impulse/inertia response against the native measurements. Grip and handbrake are partly per-handler-call, so benchmark multiple browser frame rates before changing their time normalization.
4. Synchronize heading after recovery; verify all original flip/fall resets, vehicle entry/exit and parked behavior.
5. Validate both Original and Modern clients, keyboard/touch inputs, different gravity settings, frame stalls and multiplayer updates. Both clients currently share this vehicle workaround; higher render resolution does not restore original physics.

No driving behavior was changed by this audit. The existing stable fallback remains until a replacement can be compared and tested.

## Native baseline captured in Wine

The follow-up implementation work now runs the original projector in Wine, using `browser-test/tests/native_driving_probe.py`. It preserves the original world and Havok setup, substitutes constant button states in `DrivePlayer`, sets `FrameMod = 1`, and steps native Havok by 0.022 with one substep. No terms are accepted. All transport is inside an isolated loopback namespace, and the original distribution remains read-only. These are deterministic test inputs, not a recording of an unmodified interactive session.

Native measurements are retained in `browser-test/tests/fixtures/native-driving/`. With forward held, native Car Z moves from −700 to −133.9516 after 90 steps (566.0484 units), ending at forward velocity 588.1211. The browser fallback under the same fixed-step/button fixture reaches Z 282.0648 (982.0648 units), with forward velocity 616.2081. The original seat/body moves independently; the browser fallback rigidly attaches it.

Re-enabling original vehicle handlers without changing the browser runtime is insufficient: a 90-step emulator trial ends at Car Z −699.5482 despite reported forward velocity 666.3902. The generic Z-up correction is incompatible with this Y-up scene. Experimental emulator changes remain isolated until native-baseline comparisons pass.

The confirmed heading-recovery defect is corrected: original flip/fall rotation reset paths now also clear `browserCartYaw`. A live diagnostic forced a nonzero accumulator and an off-map fall, then verified recovery cleared the accumulator to zero. This small fix does not establish full vehicle parity.

To reproduce a native trace, use the bubblewrap command in CHAT-COMPATIBILITY.md, substituting `native_driving_probe.py` and adding `--frames 90 --input forward`. Supported inputs include idle, forward, reverse, brake and forward-left/right/brake. The fixture writes `driving-results.json`, with tick, Car position/linear velocity/angular velocity/rotation, then the same four fields for Spring. Wine initialization can take longer than a warm run; rerun with the same disposable output prefix after a first-start timeout. Never run the fixture with a public network route.

`python3 browser-test/tests/build_driving_fixture.py /tmp/moonbase-driving-browser` builds the matching browser fixture. Launch `python3 /tmp/moonbase-driving-browser/serve.py --port 8081`, use Trace world startup and click Play. RoomNumber reaches 90, then physics freezes for inspection. `--native` disables the vehicle workaround in that private fixture so emulator faults can be measured independently. It never changes production assets or connects to the public game server.

Native suspension micro-tests now also retain centres of mass, a half timestep, and a one-unit initial separation change. The first three samples establish a zero-anchor COM special case, nonzero model-local anchors, one inverse-mass application, and post-integration dashpot impulses. This explains the native initial response without tuning drive speed constants. The emulator experiment remains disabled pending compiled-runtime and contact verification. The browser fixture supports `--frames` and `--input`; with `--native` it now uses the same DrivePlayer/step sequence as the projector fixture. Earlier whole-prepareFrame trial results above are exploratory comparisons.
