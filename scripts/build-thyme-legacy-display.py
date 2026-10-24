#!/usr/bin/env python3
"""Build thyme's legacy-display link stub with the source kernel's C++ recipe.

The kernel patch set requires native_legacy_display_probe() and
native_legacy_display_late_probe() whenever the legacy display instrument is
enabled. thyme has no qualified display stack yet, so this archive publishes
empty bodies with the exact compile recipe of the kernel build, and writes the
build report that build-xnu-4k-baseline.sh verifies before force-loading it.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import hashlib
import json
from pathlib import Path
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/native-legacy-display'
OUT.mkdir(parents=True, exist_ok=True)
recipe = ROOT / 'build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/iokit/DEVELOPMENT/IOPlatformExpert.cpo.json'
record = json.loads(recipe.read_text().strip().rstrip(','))
source = ROOT / 'kits/thyme/ThymeLegacyDisplay.cpp'
destination = OUT / 'ThymeLegacyDisplay.o'

command = []
arguments = record['arguments']
index = 0
while index < len(arguments):
    value = arguments[index]
    if value == record['file']:
        command.append(str(source))
    elif value == '-o':
        command.extend(['-o', str(destination)])
        index += 1
    elif value == '-Xclang' and arguments[index + 1].startswith('-W'):
        index += 1
    elif not value.startswith('-W'):
        command.append(value)
    index += 1
command.extend(['-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
                '-I', str(ROOT / '.cache/xnu-work/osfmk')])
(OUT / 'compile-command.json').write_text(json.dumps(command, indent=2) + '\n')
result = subprocess.run(command, cwd=record['directory'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
(OUT / 'compile.log').write_text(result.stdout)
if result.returncode:
    raise SystemExit(result.stdout[-3500:])

data = destination.read_bytes()
magic, cpu, subtype, kind, count, size = struct.unpack_from('<6I', data)
if (magic, cpu, subtype, kind) != (0xfeedfacf, 0x100000c, 0, 1):
    raise SystemExit('Unexpected platform object architecture')

archive = OUT / 'libNativeLegacyDisplay.late.a'
archive.unlink(missing_ok=True)
subprocess.run(['xcrun', 'ar', 'rcs', archive, destination], check=True)
report = {
    'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
    'source_sha256': {str(source.relative_to(ROOT)): hashlib.sha256(source.read_bytes()).hexdigest()},
}
(OUT / 'build-report.json').write_text(json.dumps(report, indent=2) + '\n')
print('thyme legacy display stub: archive + build report written')
