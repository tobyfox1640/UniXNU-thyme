#!/usr/bin/env python3
"""Qualify the original IOBlockStorageDevice ABI for thyme from the donor image.

The reference board qualified this interface with a prelink report, a live gdb
observation (`build/darwinboot-storage-native-metadata/gdb-stop.json`) and a
companion AES audit (`build/image4-ignition/aes-interface-audit.json`). None of
those exist for a new board and none can exist before the driver runs, so this
board derives the same numbers from the donor kernelcache alone: the reference
class is compiled from the public IOStorageFamily source exactly as the
reference audit does, and the bounds of the original class come from the
prelinked image's own __PRELINK_INFO segment instead of a prelink report.

Every measurement below is unchanged from scripts/audit-storage-interface.py; only
the candidate bounds and the two recorded-artifact gates are replaced. The output
is the pinned record build-native-virtio-bindings.py consumes.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
#!/usr/bin/env python3
"""Qualify original ordinary-ARM64 block-storage ABI using public Darwin 23 source."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'kits/NativePrelink'))
import native_prelink as np
source = ROOT / 'refer/IOStorageFamily'
revision = subprocess.check_output(['git', '-C', source, 'rev-parse', 'HEAD'], text=True).strip()
if revision != 'e45fbe30a7879e0b16e26dddb78538f1b00e0bff':
    raise SystemExit('Unexpected public Darwin 23 IOStorageFamily source')
out = ROOT / 'build/storage-abi'
headers = out / 'include/IOKit/storage'
headers.mkdir(parents=True, exist_ok=True)
for path in source.glob('*.h'):
    shutil.copyfile(path, headers / path.name)
# Only this platform-selection header is missing from the source-kernel SDK.
# The reference object is an annotation instrument and is never linked/executed.
sdk = Path(subprocess.check_output(['xcrun', '--sdk', 'macosx', '--show-sdk-path'], text=True).strip())
conditions = sdk / 'usr/include/TargetConditionals.h'
shutil.copyfile(conditions, out / 'include/TargetConditionals.h')
record = json.loads((ROOT / 'build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/iokit/DEVELOPMENT/IOPlatformExpert.cpo.json').read_text().strip().rstrip(','))
obj_path = out / 'IOBlockStorageDevice-reference.o'
arguments = record['arguments']
command, index = [], 0
while index < len(arguments):
    value = arguments[index]
    if value == record['file']:
        command.append(str(source / 'IOBlockStorageDevice.cpp'))
    elif value == '-o':
        command += ['-o', str(obj_path)]
        index += 1
    elif value in ('-MF', '-MJ'):
        index += 1
    elif value == '-Xclang' and arguments[index + 1].startswith('-W'):
        index += 1
    elif not value.startswith('-W') and value not in ('-MD', '-MP'):
        command.append(value)
    index += 1
command += ['-I', str(out / 'include'), '-I', str(ROOT / '.cache/xnu-work/osfmk'),
            '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', '-Wno-deprecated-declarations',
            '-Wno-c99-designator', '-Wno-reorder-init-list', '-Wno-unnecessary-virtual-specifier',
            '-Wno-deprecated-enum-enum-conversion']
(out / 'compile-command.json').write_text(json.dumps(command, indent=2) + '\n')
r = subprocess.run(command, cwd=record['directory'], capture_output=True, text=True)
(out / 'compile.log').write_text(r.stdout + r.stderr)
if r.returncode:
    raise SystemExit((r.stdout + r.stderr)[-3500:])


def require(value, message):
    if not value:
        raise SystemExit(message)


obj = obj_path.read_bytes()
om = np.macho(obj)
require(om['kind'] == 1, 'Expected an ordinary ARM64 reference object')
dwarf = subprocess.check_output(['xcrun', 'dwarfdump', '--name=IOBlockStorageDevice', '--show-children', obj_path], text=True)
class_size = re.search(r'DW_AT_name\s+\("IOBlockStorageDevice"\)[\s\S]{0,200}?DW_AT_byte_size\s+\((0x[0-9a-f]+)\)', dwarf)
require(class_size and int(class_size[1], 16) == 0x90, 'Actual compiled public class size changed')
version_command = next(at for command, at, size in om['commands'] if command == 0x32)
require(struct.unpack_from('<II', obj, version_command + 8) == (2, 0x110000), 'Expected iOS 17 reference deployment')
sycmd = next(at for command, at, size in om['commands'] if command == 2)
symoff, count, stroff, _ = struct.unpack_from('<4I', obj, sycmd + 8)
symbols = []
for i in range(count):
    ix, kind, _, _, value = struct.unpack_from('<IBBHQ', obj, symoff + i * 16)
    symbols.append(dict(name=obj[stroff + ix:obj.index(b'\0', stroff + ix)].decode(), value=value, kind=kind))
vtable = next(s['value'] for s in symbols if s['name'] == '__ZTV20IOBlockStorageDevice')
end = min(s['value'] for s in symbols if not s['kind'] & 0xe0 and s['kind'] & 0xe == 0xe and s['value'] > vtable)
relocations = {}
for segment in om['segments']:
    for section in segment['sections']:
        if section['va'] <= vtable < section['va'] + section['size']:
            ro, rc = struct.unpack_from('<II', obj, section['command_offset'] + 56)
            for i in range(rc):
                address, word = struct.unpack_from('<II', obj, ro + i * 8)
                if word >> 27 & 1 and word >> 28 == 0 and word >> 25 & 3 == 3:
                    relocations[section['va'] + address] = symbols[word & 0xffffff]['name']
methods = []
for at in range(vtable + 16, end, 8):
    if at not in relocations:
        break
    methods.append(relocations[at])
require(len(methods) == 190 and methods.count('___cxa_pure_virtual') == 14, 'Public iOS class dispatch shape changed')
kernel_path = ROOT / 'build/native-prelink/native-apfs-load-positive.macho'
if not kernel_path.is_file():
    raise SystemExit(f'the donor kernelcache is not at {kernel_path}; the pre-build step places it')
kernel = kernel_path.read_bytes()
native = np.macho(kernel)
exports = np.exports(kernel, native)
by_name = {name: va for va, names in exports.items() for name in names}

# The reference audit qualified its bounds from a prelink report plus a live gdb
# observation and a companion AES audit, none of which exist for a new board.
# The prelinked image carries the same information itself: __PRELINK_INFO lists
# every kext with the address its executable was loaded at, so the extents of
# the original storage kext can be read straight out of the donor kernelcache.
parent = native['segments']
info = next(s for s in parent if s['name'] == '__PRELINK_INFO')
at = np.backed_offset(parent, info['va'], info['filesize'], len(kernel))
metadata = np.unserialize_xml(kernel[at:at + info['filesize']])
entry = next(e for e in metadata['_PrelinkInfoDictionary']
             if e.get('CFBundleIdentifier') == 'com.apple.iokit.IOStorageFamily')
header = np.backed_offset(parent, entry['_PrelinkExecutableLoadAddr'], 32, len(kernel))
module = np.macho(kernel, header)
segments = {s['name']: s for s in module['segments'] if s['size']}
# The prelink moves every kext by the board's slide, so the extents recorded in
# the donor image are not where the merged image keeps the code. Read at the
# moved addresses; the pointers found inside are already relocated by the
# prelink and are used as they are.
import argparse as _argparse
_ap = _argparse.ArgumentParser(description='thyme storage interface audit')
_ap.add_argument('--slide', type=lambda v: int(v, 0), default=0)
_args = _ap.parse_args()
text = dict(segments['__TEXT_EXEC'], va=segments['__TEXT_EXEC']['va'] + _args.slide)
const = dict(segments['__DATA_CONST'], va=segments['__DATA_CONST']['va'] + _args.slide)


def read(va, length):
    at = np.backed_offset(native['segments'], va, length, len(kernel))
    return kernel[at:at + length]


blob = read(const['va'], const['size'])
found = []
for at in range(0, len(blob) - (len(methods) + 2) * 8 + 1, 8):
    if blob[at:at + 16] != bytes(16):
        continue
    pointers = struct.unpack_from('<' + 'Q' * len(methods), blob, at + 16)
    if all(pointers[i] == by_name[name] for i, name in enumerate(methods) if name in by_name):
        found.append((const['va'] + at, pointers))
require(len(found) == 1, 'Cannot uniquely identify the original block-storage class dispatch')
table, pointers = found[0]
matched = sum(name in by_name for name in methods)
require(matched == 176, 'Unexpected original/native kernel binding count')
for i, name in enumerate(methods):
    if name not in by_name:
        require(text['va'] <= pointers[i] < text['va'] + text['size'], 'Owned storage method outside original text')


def relative_branch(address, instruction):
    immediate = instruction & 0x3ffffff
    if immediate & 0x2000000:
        immediate -= 0x4000000
    return address + immediate * 4


def thunk_names(address):
    a, load, branch = struct.unpack('<3I', read(address, 12))
    require(a & 0x9f00001f == 0x90000010 and load & 0xffc003ff == 0xf9400210 and branch == 0xd61f0200,
            'Unqualified original native import thunk')
    immediate = ((a >> 5 & 0x7ffff) << 2) | (a >> 29 & 3)
    if immediate & 0x100000:
        immediate -= 0x200000
    slot = (address & ~4095) + immediate * 4096 + (load >> 10 & 4095) * 8
    target = struct.unpack('<Q', read(slot, 8))[0]
    return exports.get(target, [])


constructors = []
for address in range(text['va'], text['va'] + text['size'] - 32, 4):
    words = struct.unpack('<8I', read(address, 32))
    if (words[:2] != (0xa9bf7bfd, 0x910003fd) or words[2] & 0xfc000000 != 0x94000000 or
        words[3] & 0x9f00001f != 0x90000008 or words[4] & 0xffc003ff != 0x91000108 or
        words[5:] != (0xf9000008, 0xa8c17bfd, 0xd65f03c0)):
        continue
    immediate = ((words[3] >> 5 & 0x7ffff) << 2) | (words[3] >> 29 & 3)
    if immediate & 0x100000:
        immediate -= 0x200000
    stored = ((address + 12) & ~4095) + immediate * 4096 + (words[4] >> 10 & 4095)
    if stored == table + 16:
        constructors.append((address, relative_branch(address + 8, words[2])))
require(len(constructors) == 1 and '__ZN9IOServiceC2EPK11OSMetaClass' in thunk_names(constructors[0][1]),
        'Original protected block constructor does not forward to actual source IOService')
destructor = pointers[0] - 4
word = struct.unpack('<I', read(destructor, 4))[0]
require(word & 0xfc000000 == 0x14000000 and
        '__ZN9IOServiceD2Ev' in thunk_names(relative_branch(destructor, word)), 'Unqualified actual base destructor')
require(all(read(pointers[i], 4) == struct.pack('<I', 0xd4200020) for i in (0, 1)),
        'Unexpected original abstract complete-destructor behavior')
function = pointers[7]
a, add, ret = struct.unpack('<3I', read(function, 12))
require(a & 0x9f00001f == 0x90000000 and add & 0xffc003ff == 0x91000000 and ret == 0xd65f03c0,
        'Unqualified original storage metaclass getter')
immediate = ((a >> 5 & 0x7ffff) << 2) | (a >> 29 & 3)
if immediate & 0x100000:
    immediate -= 0x200000
meta = (function & ~4095) + immediate * 4096 + (add >> 10 & 4095)
service_meta = by_name['__ZN9IOService10gMetaClassE']
result = dict(
    candidate_sha256=hashlib.sha256(kernel).hexdigest(),
    method_slots=190, kernel_bindings=matched, pure_virtual_slots=14, inherited_kernel_methods=162,
    vtable=hex(table), original_metaclass=hex(meta), source_ioservice_metaclass=hex(service_meta),
    original_protected_constructor=hex(constructors[0][0]), original_base_destructor=hex(destructor),
    abstract_complete_destructors_trap=True,
    live_instance_sizes=dict(IOBlockStorageDevice=0x90, IOService=0x88), live_native_4k=True,
    compiled_public_class_size=int(class_size[1], 16),
    methods=[dict(slot=i, reference_name=name, candidate_target=hex(pointers[i]),
                  kernel_names=exports.get(pointers[i], [])) for i, name in enumerate(methods)],
    extents_from='donor __PRELINK_INFO', live_metadata_recorded=False,
    disk_read_tested=False, transport_implemented=False, hardware_tested=False)
(out / 'interface-audit.json').write_text(json.dumps(result, indent=2) + '\n')
print(f'interface audit: dispatch {table:#x}, {matched} kernel bindings, constructor {constructors[0][0]:#x}')
