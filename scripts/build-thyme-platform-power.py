#!/usr/bin/env python3
"""Build thyme's guarded original-PMGR integration instrument.

AppleMobileFileIntegrity panics with "AMFI: No PMGR" unless an ApplePMGR
service exists, so bsd_init() publishes the donor's original PMGR nub through
CONFIG_XNU_SHENG_PMGR. This builder generates the exact donor storage/slot ABI,
compiles the board source with the kernel's own C++ recipe, binds the three
ApplePMGR symbols and the three original nub entry points of the donor
kernelcache (the same iPad7,1 17.7.11 image the kernel is prelinked against),
and writes the archive the link script expects. No clock, sleep, reset or
secondary-CPU success is advertised.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import json
from pathlib import Path
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/sheng-platform-power'
OUT.mkdir(parents=True, exist_ok=True)

# Storage and vtable of the donor's ApplePMGR, read from the donor kernelcache.
header = '''// Generated exact storage/slot ABI; private fields stay opaque.
#pragma once
#include <IOKit/IOPMGR.h>
class ApplePMGR : public IOPMGR {
 OSDeclareAbstractStructors(ApplePMGR)
 unsigned char originalPrivate[0x4b8a8-sizeof(IOPMGR)];
public:
'''
guards = ''
for i in range(177, 340):
    # Slots 320/321 are AON register access. AMFI really calls readAon(), so
    # these two keep the donor's implementations: the class declares them
    # without a guard and the source dispatches through the donor's own ApplePMGR
    # vtable entries at runtime (same donor image and link layout as the
    # reference ports, which bind these two symbols statically instead).
    if i in (320, 321):
        header += (' virtual uint32_t readAon();\n' if i == 320
                   else ' virtual void writeAon(uint64_t);\n')
    else:
        header += f' virtual void opaque{i}() = 0;\n'
        guards += f' void opaque{i}() override {{ unavailable({i}); }}\n'
header += '};\nstatic_assert(sizeof(ApplePMGR)==0x4b8a8,"Original provider storage");\n'
(OUT / 'OriginalPMGRABI.h').write_text(header)
(OUT / 'GuardedPMGRSlots.inc').write_text(guards)

source = ROOT / 'kits/thyme/ThymePlatformPower.cpp'
obj = OUT / 'ThymePlatformPower.o'
record = json.loads((ROOT / 'build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/iokit/DEVELOPMENT/IOPlatformExpert.cpo.json').read_text().strip().rstrip(','))
command, index = [], 0
arguments = record['arguments']
while index < len(arguments):
    value = arguments[index]
    if value == record['file']:
        command.append(str(source))
    elif value == '-o':
        command.extend(['-o', str(obj)])
        index += 1
    elif value == '-Xclang' and arguments[index + 1].startswith('-W'):
        index += 1
    elif not value.startswith('-W'):
        command.append(value)
    index += 1
command += ['-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', '-Wno-c99-designator',
            '-Wno-reorder-init-list', '-Wno-deprecated-enum-enum-conversion',
            '-Wno-unnecessary-virtual-specifier',
            '-I', str(OUT), '-I', str(ROOT / '.cache/xnu-work/osfmk')]
(OUT / 'compile-command.json').write_text(json.dumps([str(v) for v in command], indent=2) + '\n')
result = subprocess.run([str(v) for v in command], cwd=record['directory'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
(OUT / 'compile.log').write_text(result.stdout)
if result.returncode:
    raise SystemExit(result.stdout[-3500:])

# Addresses inside the donor kernelcache that this kernel is prelinked against.
# Same donor as sheng and umi, so the same values; the kernel link resolves them.
bindings = {
    '__ZN9ApplePMGRC2EPK11OSMetaClass': 0xfffffff0049f003c,
    '__ZN9ApplePMGRD2Ev': 0xfffffff0049f019c,
    '__ZN9ApplePMGR10gMetaClassE': 0xfffffff006adf490,
    '_thyme_original_pmgr_nub_create': 0xfffffff004a22568,
    '_thyme_original_pmgr_nub_read': 0xfffffff004a24adc,
    '_thyme_original_pmgr_nub_write': 0xfffffff004a230ec,
}
asm = OUT / 'original-bindings.S'
asm.write_text(''.join(f'.globl {name}\n.set {name}, {va:#x}\n' for name, va in bindings.items()))
sdk = subprocess.check_output(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path'], text=True).strip()
subprocess.run(['xcrun', 'clang', '-target', 'arm64-apple-ios17.0', '-isysroot', sdk, '-c', str(asm), '-o', str(OUT / 'original-bindings.o')], check=True)

archive = OUT / 'libShengPlatformPower.a'
archive.unlink(missing_ok=True)
subprocess.run(['xcrun', 'ar', 'rcs', archive, obj, OUT / 'original-bindings.o'], check=True)
print(f'thyme platform power: {archive.relative_to(ROOT)} ({archive.stat().st_size} bytes)')
