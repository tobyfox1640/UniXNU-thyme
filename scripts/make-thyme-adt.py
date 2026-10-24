#!/usr/bin/env python3
"""Generate thyme's Apple-format ADT sidecar, without device I/O.

Implements the UniXNU payload ADT CLI. Hardware addresses come from the
qualified thyme profile; the optional sheng iPad profile changes userspace
compatibility properties while retaining the physical board and its seed.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import hashlib
import json
from pathlib import Path

from thyme_adt import build_tree, decode, hardware_path, load_hardware, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dram-size", type=lambda v: int(v, 0), required=True)
    parser.add_argument("--owned-memory-size", type=lambda v: int(v, 0))
    parser.add_argument("--root-match-volume-uuid")
    parser.add_argument("--unique-chip-id", type=lambda v: int(v, 16))
    parser.add_argument("--chip-id", type=lambda v: int(v, 16))
    parser.add_argument("--cpu-regs", default="0")
    parser.add_argument("--psci-method", choices=("smc", "hvc"), default="smc")
    data = parser.add_mutually_exclusive_group()
    data.add_argument("--data-ramdisk", action="store_true")
    data.add_argument("--packed-data-ramdisk", action="store_true")
    parser.add_argument("--trust-cache", action="store_true")
    parser.add_argument("--ipad-identity", action="store_true",
                        help="sheng's iPad7,1 / 21H461 userspace compatibility profile")
    args = parser.parse_args()
    try:
        hardware = load_hardware()
        tree = build_tree(
            hardware, dram_size=args.dram_size,
            cpu_regs=tuple(int(v, 0) for v in args.cpu_regs.split(",")),
            psci_method=args.psci_method, owned_memory_size=args.owned_memory_size,
            root_match_volume_uuid=args.root_match_volume_uuid,
            unique_chip_id=args.unique_chip_id, chip_id=args.chip_id,
            data_ramdisk=args.data_ramdisk, packed_data_ramdisk=args.packed_data_ramdisk,
            trust_cache=args.trust_cache, ipad_identity=args.ipad_identity)
        blob = tree.encode()
        decoded = decode(blob)
        if decoded.encode() != blob:
            raise ValueError("ADT round-trip differs")
    except (ValueError, KeyError) as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(blob)
    # Private binary includes fresh entropy and an optional software identity.
    args.output.chmod(0o600)
    report = {
        "format": "Apple device tree (not FDT)", "device": "thyme",
        "adt_sha256": hashlib.sha256(blob).hexdigest(), "bytes": len(blob),
        "hardware_profile_sha256": hashlib.sha256(hardware_path().read_bytes()).hexdigest(),
        "hardware_sources": hardware["sources"], **summary(decoded),
        "roundtrip_verified": True, "hardware_tested": False,
        "memory_window_requires_firmware_validation": True,
        "limitations": [
            "umi attempt 19 qualified a 512 MiB conventional window and a 256 MiB DarwinBoot allocation; this ADT alone does not verify that firmware.",
            "dram-size is the observed bank total, not a contiguous free-memory declaration.",
            "Framebuffer is handed over from GOP in boot_args, not initialized by this ADT.",
            "No GPU/touch hardware driver nodes; optional iPad profile is a userspace compatibility input.",
        ],
    }
    args.output.with_name(args.output.name + ".json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"umi ADT: {len(blob)} bytes; {len(tree.at('/cpus').children)} CPU(s); "
          f"GIC {report['gic_distributor']}/{report['gic_redistributor']}; host-validated only")


if __name__ == "__main__":
    main()
