# Vehicle physics experiment — not enabled

`vehicle-y-up-experiment.patch` is a research patch against the pinned DirPlayer source bundled in `runtime-modern/upstream-source.tar.gz`. It is not included by `patch_runtime.py`, `setup.py` or deployment. Both published client runtimes remain unchanged.

It disables the emulator's Z-up ground clamp for a Y-up Car/Spring scene, classifies those bodies as boxes instead of rolling spheres, keeps the constrained pair active, and tests discrete contact resolution instead of rolling back all bodies when any body collides. It preserves the authored drive handler and dashpot strengths in the separate browser test fixture.

The first compiled trial (before the discrete-contact/active changes) did not match the native trace. The native-projector fixture in `tests/native_driving_probe.py` and the isolated browser fixture in `tests/build_driving_fixture.py` are the acceptance references. Do not replace the production vehicle fallback on the basis of this patch compiling or looking plausible; native acceleration, reverse, braking, steering, contacts, suspension and recovery comparisons must pass first.

This does not establish that the emulator's remaining convex contact, inertia, damping or dashpot/world-scale behavior matches the original Havok Xtra.

The next trial uses the native linear-dashpot anchor convention (zero means COM; nonzero is model-local), applies inverse mass once, and applies dashpot impulses after position integration. At dt 0.022, mass 10/2, COM A Y=28.6306, initial body Y=-678/-668 and pointB Y=-1, this predicts native velocities -3.2574/16.2869, then -8.9928/28.4806 and -14.4072/39.0856. Native half-dt and +1 initial separation captures independently check the time/position dependence. These calculations explain the first three free-suspension samples; compiled-runtime and terrain-contact comparisons remain required.

## Measured browser trials

| Trial | Result at 90 forward steps | Accepted? |
| --- | --- | --- |
| 4: native linear dashpot/order | First 23 steps match within 0.001; first ground impact diverges | No |
| 5: COM rotation, angular units, impulse-only normal response | Suspension aligns, but chassis falls through ground | No |
| 6: hull vertices clipped to terrain faces, contact midpoint, coupled sticking friction | Car Z=-113.9034, Y=-699.3579; native Z=-133.9516, Y=-697.0219 | No: travel is 3.54% too far and contact response differs |

The corresponding measured browser traces live beside the native references in `tests/fixtures/native-driving`. `tests/compare_driving.py` checks complete, matching input/timestep traces and compares positions, velocities and axis-angle rotations. The comparison deliberately fails on the first contact at step 24; compilation and a plausible screenshot are not parity checks.

Native material probes show 0.5 friction on Car, Spring and GroundShape. The first impact has a tangential/normal impulse ratio of 0.5. Changing either the chassis or ground material to 0.25 changes that ratio to 0.25. The research patch now tests the lower-material rule, coupled sliding friction and zero-gravity scene recognition (trial 7).

Native first-contact position is `(2173.82,-713.0021,-583.0064)`; the trial-6 support-vertex solver chooses `(2197.9205,-713.0021,-544.8195)`. Both lie on the touching face, but their different moment arms change the response. Reproducing Havok's contact-feature selection remains necessary for deterministic trace parity. Do not hardcode a contact-point scale to fit this single impact.

To inspect a compiled experimental bundle without changing production assets:

```bash
python3 browser-test/tests/build_driving_fixture.py /tmp/moonbase-driving-browser \
  --native --input forward --frames 90 --runtime-bundle /absolute/path/to/dirplayer-polyfill.js
python3 /tmp/moonbase-driving-browser/serve.py --port 8081
```

Open the private fixture, use Player diagnostics → Trace world startup, click Play, then run `@export-driving` in its Lingo console. The movie captures each step before the next one; browser polling cannot drop samples. Exported `Driving row` messages have the same nine fields as the basic native trace. The fixture intentionally reuses the fallback-only `browserCartYaw` variable as its private trace list; no published runtime uses that representation.

## Trial 7 acceptance result

Trial 7 is **not accepted and remains excluded from deployment**. At 90 forward steps, its chassis reaches Z=-136.9788 versus native -133.9516 (0.535% less forward travel). Reverse, forward-left and forward-brake traces are also retained, and all still fail the strict comparison. Improved distance alone does not establish matching handling.

A longer 360-step forward test exposes substantial terrain instability: native Car ends at (1926.07,-228.0804,3496.43), while the experimental browser Car ends at (1886.56,-123.2359,3060.34), with approximately 69.55 degrees of pitch. The browser console retained only the last 180 rows, so that partial export is not committed as a complete reference trace. The complete native 360-step reference is retained.

Independent unit-angular-velocity probes confirm that the native and browser inertia tensors agree to native output precision: Car diagonal (86.8559,117.3904,35.2262), Spring (7.4789,9.4858,2.0797). Remaining work includes contact-feature selection and verifying model/physics centre-of-mass transform synchronization; no unverified change to either is enabled in production.
