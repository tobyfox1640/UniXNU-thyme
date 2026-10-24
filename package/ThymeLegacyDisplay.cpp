//
// thyme bring-up: no-op legacy display instrument.
//
// The base kernel patch set (patches/xnu/offline-component-load-probes.patch)
// references native_legacy_display_probe() from bsd_init.c under
// DEVELOPMENT || DEBUG, and offline-legacy-start.patch references
// native_legacy_display_late_probe() when XNU_NATIVE_LEGACY_DISPLAY is on.
// The real instrument belongs to the qualified display stack, which thyme
// does not have yet, so this archive satisfies the link with empty bodies.
// The probes stay inert: the kernel only calls them when the matching
// offline-* boot argument is present, and they do nothing.
//
// Replaced by the genuine Legacy framebuffer/IOSurface backend once that
// stack is ported. SPDX-License-Identifier: BSD-2-Clause-Patent
//

extern "C" void
native_legacy_display_probe (void)
{
}

extern "C" void
native_legacy_display_late_probe (void)
{
}
