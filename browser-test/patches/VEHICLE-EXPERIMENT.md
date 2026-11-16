# Vehicle physics experiment — not enabled

`vehicle-y-up-experiment.patch` is a research patch against the pinned DirPlayer source bundled in `runtime-modern/upstream-source.tar.gz`. It is not included by `patch_runtime.py`, `setup.py` or deployment. Both published client runtimes remain unchanged.

It disables the emulator's Z-up ground clamp for a Y-up Car/Spring scene, classifies those bodies as boxes instead of rolling spheres, keeps the constrained pair active, and tests discrete contact resolution instead of rolling back all bodies when any body collides. It preserves the authored drive handler and dashpot strengths in the separate browser test fixture.

The first compiled trial (before the discrete-contact/active changes) did not match the native trace. The native-projector fixture in `tests/native_driving_probe.py` and the isolated browser fixture in `tests/build_driving_fixture.py` are the acceptance references. Do not replace the production vehicle fallback on the basis of this patch compiling or looking plausible; native acceleration, reverse, braking, steering, contacts, suspension and recovery comparisons must pass first.

This does not establish that the emulator's remaining convex contact, inertia, damping or dashpot/world-scale behavior matches the original Havok Xtra.

The next trial uses the native linear-dashpot anchor convention (zero means COM; nonzero is model-local), applies inverse mass once, and applies dashpot impulses after position integration. At dt 0.022, mass 10/2, COM A Y=28.6306, initial body Y=-678/-668 and pointB Y=-1, this predicts native velocities -3.2574/16.2869, then -8.9928/28.4806 and -14.4072/39.0856. Native half-dt and +1 initial separation captures independently check the time/position dependence. These calculations explain the first three free-suspension samples; compiled-runtime and terrain-contact comparisons remain required.
