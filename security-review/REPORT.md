# Moonbase package static security review

Review date: 2026-11-15 (Europe/Amsterdam).

## Verdict

No confirmed malware was identified in this static inspection. This is **not a clean antivirus result or a guarantee of safety**. Treat the Windows executables as unverified until scanned with current antivirus engines and, if necessary, observed in an isolated Windows VM.

## Scope and method

Reviewed the 63 original files: 50 Windows PE executables/libraries (including Director Xtras), 11 VBScript/WSF files, and two macOS .DS_Store files. Enumerated types and SHA-256 hashes; inspected PE sections, certificate-table presence, imports, ASCII/UTF-16 strings, appended content, all plaintext scripts, and the embedded NVIDIA helper application source. No package executables or scripts were executed. Original files were not modified.

This is a distributed Windows Director/Shockwave projector package. The .git directory is empty; there is no available commit history or remote configuration to establish provenance. There are no separate editable game project files, build configuration, or multiplayer server sources in this folder. Embedded strings identify an Adobe Projector 12.0r111 and a Moon Base Version 1.7d movie. That supports a standalone Shockwave wrapper rather than a demonstrated engine rewrite.

## Findings

### NVIDIA helper: privileged system changes, consistent with its stated purpose

FIX_NVIDIA.exe is a 73,989,500-byte executable containing a Node.js runtime and a pkg virtual filesystem with 89 entries. Its stored application source is preserved as FIX_NVIDIA.embedded-index.js.txt.

The recovered source enumerates InstalledDisplayDrivers values under HKLM\SYSTEM\CurrentControlSet\Control\Video, strips directory/extension information from driver entries, and invokes elevated reg.exe ADD commands to overwrite those REG_MULTI_SZ values. sudo-prompt provides elevation; regedit uses the external vbs directory. There is no application-source download, exfiltration destination, persistence setup, or antivirus disabling in that recovered entry point. A web URL in its error text is a troubleshooting reference, not a download call.

This changes machine-wide graphics-driver settings and should not be run casually on a primary Windows installation. The command interpolates registry-derived text into a shell command without robust shell escaping; a tampered input could alter the command. This is a potential robustness/security issue, not evidence of an active malicious payload.

The package also stores compiled V8 bytecode. This review recovered the accompanying source but did not prove bytecode/source equivalence or audit the entire native Node runtime and all dependencies.

### Main game: native projector containing runtime libraries and game data

MB_2010-10-08.exe contains an approximately 6.7 MB overlay after its outer PE sections. Five embedded PE files have Adobe/Microsoft runtime metadata. They were compared byte-for-byte against the loose Proj.dll, Dirapi.dll, Iml32.dll, msvcr100.dll, and msvcp100.dll; see embedded-runtime-comparison.txt for results. Thus the presence of appended executable material has a concrete packaging explanation and is not itself a malware finding.

Visible movie strings include multiplayer connection and room-management functions. Legacy Macromedia/Adobe HTTP update/Xtra URLs are present. These strings establish capabilities and references, not which connections actually occur. The compiled game scripts/assets were not fully decoded or decompiled, and actual server destinations/runtime behavior remain unverified.

### Script helpers: generic registry access

All 11 VBS/WSF files were read. They expose generic registry list/create/write/delete operations through WMI StdRegProv. util.vbs uses ExecuteGlobal to include local architecture-specific helper files; its callers select fixed local filenames. No obfuscated downloader, scheduled task, hardcoded autorun key, credential theft destination, or antivirus-disabling command was found in these scripts. Their generic registry modification capabilities still make them privileged tools when run with elevated rights.

### Signatures and provenance remain incomplete

47 of 50 PE files contain certificate-table data. The three without it are MB_2010-10-08.exe, FIX_NVIDIA.exe, and Xtras/Havok.x32. A sampled Dirapi.dll certificate container includes an Adobe Systems Incorporated signing certificate and timestamp certificates. Certificate-table presence or publisher metadata alone does not establish authenticity: image digests, certificate trust chains, revocation, and timestamp validity were not verified. Unsigned files are not automatically malware.

### Indicator searches

Searched extracted ASCII/UTF-16 strings for common persistence keys, scheduled-task commands, security-disabling commands, destructive administrative tools, credential-store names, common exfiltration endpoints, and mining indicators. No matches were found for those specific persistence, disabling, destructive-tool, credential-store, endpoint, or mining terms. Shell-related matches occur in the helper, projector/runtime and scripts. The helper's keylog matches refer to Node TLS key logging, not demonstrated keyboard capture. PowerShell strings occur in its privilege-elevation dependency. String searches are incomplete heuristics and cannot exclude hidden or compiled behavior; raw term hits are saved in indicator-hits.json.

## What was not done

- No antivirus engine scan: ClamAV/clamscan and a signature database were unavailable.
- No dynamic execution, sandbox detonation, or network-traffic observation.
- No complete native disassembly or Director/Lingo decompilation.
- No verified vendor hash baseline or cryptographic Authenticode validation.
- Public web searches for the two executable SHA-256 hashes and the helper project name returned no results. This is not a VirusTotal lookup or evidence of a clean reputation. No files were uploaded to external scanning services.

## Recommended next step

Scan the original 63 files with current Microsoft Defender or another updated antivirus engine. Check the hashes against existing multi-engine reports; if reports do not exist, decide whether to upload the binaries. For behavioral investigation, use a disposable Windows VM without personal accounts, host-folder sharing, or initially enabled network access. Inspect network attempts and registry/process changes before allowing connections. Keep the NVIDIA helper out of the future browser build; the browser implementation should not require Windows registry access or these native runtime libraries.

## Evidence files

- file-inventory.json: original file sizes, hashes, PE sections, certificate-table sizes, and overlay measurements.
- sha256sums.txt: all original file SHA-256 hashes.
- FIX_NVIDIA.embedded-index.js.txt and FIX_NVIDIA.embedded-package.json.txt: recovered source/metadata saved as inert text.
- embedded-runtime-comparison.txt: exact comparisons of embedded and loose runtime files.
- indicator-hits.json: raw string-term matches, requiring context rather than being malware verdicts.
