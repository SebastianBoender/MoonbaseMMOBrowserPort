# Browser / downloadable chat interoperability

Verified locally on 2026-11-16 against the supplied `MB_2010-10-08.exe`, SHA-256 `6d7b81d5d1e76ca6ee7ca2f1fc4286ab19a62a344417f88d229f677280b43a3a`.

## Reproduced defect

The movie sends `MC` with `[userID, EncryptString(string([text, milliseconds]), string(userID))]`. `EncryptString` XORs text with the sender's ID, then writes each resulting nibble as a character whose low nibble is 15. Consequently even plain ASCII chat contains characters above 127.

The bundled Director 12 projector's Multiuser Xtra serializes those characters as UTF-8. DirPlayer's binary MUS writer instead casts each character to a byte, and its reader maps each incoming byte to a character. Native-to-browser and browser-to-native messages therefore decrypt incorrectly before the game's `value()` list check. Server `MC` success/echo and successful browser-to-browser delivery do not establish native interoperability.

## Native fixture and browser verification

The actual desktop runtime was launched under Wine against a local-only MUS fixture. The test changes a disposable executable copy's startup and callback handlers to use fixed synthetic inputs, call the original encryption/decryption handlers and exchange fixture packets. It never accepts game terms or logs into the public server. The original executable, DLLs and Xtras are unchanged.

For plaintext `MoonBase0429` and sender/key `123456`, both native and browser encryption generate these 24 character values:

```
207 127 223 95 207 95 175 95 127 127 127 95
47 79 127 95 63 15 15 15 127 15 255 15
```

The desktop serializes them into **29 UTF-8 bytes**; the browser serializes **24 raw bytes**. The exact native packet is preserved as the synthetic fixture in `browser-test/tests/test_chat_protocol.py`.

| Direction | Original bytes | Corrected bytes |
| --- | --- | --- |
| Browser → native Wine decoder | Incorrect text; returned UTF-8 hex `c38ec38d446377613232343b` | Exact `MoonBase0429` |
| Native → actual browser VM decoder | Incorrect text | Exact `MoonBase0429` |

The bridge now translates only the second content-list item of recognized encrypted `MC` packets. Sender, recipients, timestamps and all non-chat packets are unchanged. It accepts incoming UTF-8 and existing byte-based cipher values. Tests cover the captured native packet, every cipher nibble, odd/even padding, malformed/truncated inputs, split/coalesced frames, and real WebSocket-to-TCP translation in both directions.

## Reproduce the isolated native test

Requires Linux, Wine, bubblewrap, an existing local X11 display and the private original game package. The output directory contains a disposable patched executable and Wine prefix; do not distribute it. This command gives Wine a private network namespace, a private temporary directory, hides the user's home directory and mounts the original package read-only:

```bash
probe_output=$(mktemp -d /tmp/moonbase-chat-probe.XXXXXXXX)
bwrap --unshare-net --ro-bind / / --tmpfs /tmp \
  --ro-bind /tmp/.X11-unix /tmp/.X11-unix \
  --bind "$probe_output" /tmp/probe-output \
  --tmpfs "$HOME" --ro-bind "$PWD" /mnt \
  --dev /dev --proc /proc --chdir /mnt \
  python3 /mnt/browser-test/tests/native_chat_probe.py /mnt --output /tmp/probe-output
```

The test captures a native packet, feeds the native runtime the original browser representation and then the corrected one, asserts the failure/success distinction, and writes `results.json`. It kills its dedicated Wine server on exit.

## Practical limits

This proves the supplied native runtime and local browser encryption/decryption formats, plus the fixed bridge transport. It is not a completed live test between the deployed website and another person's desktop session. Their desktop build must match the supplied package; both users still need chat enabled and the same room. Deploy/restart the backend and reconnect browsers before that final check. The original game's cipher remains byte-limited; this change does not add unrestricted Unicode chat.
