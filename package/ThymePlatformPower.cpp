// SPDX-License-Identifier: MIT
// Adapted from UniXNU-umi package/UmiPlatformPower.cpp (SM8250), which in turn
// follows UniXNU-sheng a599a1a8a92093b5077543e071b72130769eb325. thyme uses the
// same donor kernelcache (iPad7,1 17.7.11), so the donor-derived class storage,
// nub entry points and ApplePMGR symbols are the ones this board needs.
//
// The base patch patches/xnu/sheng-platform-power.patch calls sheng_pmgr_run()
// from bsd_init() when CONFIG_XNU_SHENG_PMGR is on, so the exported name stays
// sheng_pmgr_run even though the implementation is thyme's.
// Umi original PMGR service integration; no SM8550 hardware resources.
// Board-side original PMGR ABI qualification. Default off. Modes: 1 releases
// unpublished objects, 2 publishes the original nub, 3 tests power refusal.
// No clocks, sleep, reset or secondary-CPU success is advertised.
#include "OriginalPMGRABI.h"
#include <IOKit/IOLib.h>
#include <IOKit/IOPlatformExpert.h>
#include <libkern/c++/OSSymbol.h>
#include <mach/kmod.h>
#include <pexpert/pexpert.h>

extern "C" {
extern kmod_info_t g_kernel_kmod_info;
kern_return_t OSKextLoadKextWithIdentifier(const char *);
void thyme_pmgr_static_init(void) __asm__("__GLOBAL__sub_I_ThymePlatformPower.cpp");
IOService *thyme_original_pmgr_nub_create(IORegistryEntry *, ApplePMGR *);
uint32_t thyme_original_pmgr_nub_read(IOService *);
void thyme_original_pmgr_nub_write(IOService *, uint64_t);
// stage,status,parent-size,own-size,provider,nub,bound-provider,read-before,
// read-after,own-before,own-after,nub-before,nub-after,attached,registered,mode.
volatile uint64_t thyme_pmgr_observation[16];
__attribute__((noinline)) void thyme_pmgr_checkpoint(void) {
  __asm__ volatile("" ::: "memory");
}
// Called at the root-volume lookup boundary, after ordinary platform matching.
// Read existing driver counters; never manufacture readiness or interrupts.
}

__attribute__((noreturn)) static void unavailable(unsigned slot)
{
  thyme_pmgr_observation[0] = 0x100 + slot;
  thyme_pmgr_observation[1] = static_cast<uint32_t>(kIOReturnUnsupported);
  thyme_pmgr_checkpoint();
  panic("ThymePlatformPower: unimplemented operation %u", slot);
}

class ThymePlatformPower : public ApplePMGR {
  OSDeclareDefaultStructors(ThymePlatformPower)
public:
  void enableCPUCore(unsigned, uint64_t) override { unavailable(168); }
  void enableCPUCore(unsigned) override { unavailable(169); }
  void disableCPUCore(unsigned) override { unavailable(170); }
  void enableCPUCluster(unsigned) override { unavailable(171); }
  void disableCPUCluster(unsigned) override { unavailable(172); }
  void initCPUIdle(ml_processor_info_t *) override { unavailable(173); }
  void enterCPUIdle(UInt64 *) override { unavailable(174); }
  void exitCPUIdle(UInt64 *) override { unavailable(175); }
  void updateCPUIdle(UInt64 *) override { unavailable(176); }
#include "GuardedPMGRSlots.inc"
};
OSDefineMetaClassWithInit(ThymePlatformPower, ApplePMGR, )
OSMetaClassConstructorInit(ThymePlatformPower, ApplePMGR, )
OSDefineBasicStructors(ThymePlatformPower, ApplePMGR)
// The original object's storage exceeds kalloc_type's 16 KiB size limit.
// Use XNU's existing zeroed, size-aware OSObject heap allocation pair.
void *ThymePlatformPower::operator new(size_t size) { return OSObject::operator new(size); }
void ThymePlatformPower::operator delete(void *memory, size_t size)
{
  OSObject::operator delete(memory, size);
}
static_assert(sizeof(ThymePlatformPower) == 0x4b8a8, "Exact original provider storage");

static const OSMetaClass *lookup(const char *text)
{
  const OSSymbol *name = OSSymbol::withCString(text);
  const OSMetaClass *meta = name ? OSMetaClass::getMetaClassWithName(name) : nullptr;
  OSSafeReleaseNULL(name);
  return meta;
}

extern "C" void sheng_pmgr_run(void)
{
  unsigned mode = 0;
  if (!PE_parse_boot_argn("thyme-pmgr", &mode, sizeof(mode)) || !mode) return;
  thyme_pmgr_observation[15] = mode;
  thyme_pmgr_observation[1] = static_cast<uint32_t>(kIOReturnError);
  if (mode > 3 || thyme_pmgr_observation[0]) { thyme_pmgr_checkpoint(); panic("ThymePlatformPower: invalid mode or duplicate initialization"); }
  thyme_pmgr_observation[0] = 1;
  kern_return_t result = OSKextLoadKextWithIdentifier("com.apple.driver.ApplePMGR");
  if (result) { thyme_pmgr_observation[1] = static_cast<uint32_t>(result); thyme_pmgr_checkpoint(); return; }
  const OSMetaClass *parent = lookup("ApplePMGR"), *nubMeta = lookup("ApplePMGRNub");
  if (!parent || parent != &ApplePMGR::gMetaClass || parent->getClassSize() != 0x4b8a8 ||
      !nubMeta || nubMeta->getClassSize() != 0x740) { thyme_pmgr_checkpoint(); return; }
  thyme_pmgr_observation[2] = parent->getClassSize();
  void *handle = OSMetaClass::preModLoad(g_kernel_kmod_info.name);
  if (!handle) { thyme_pmgr_checkpoint(); return; }
  thyme_pmgr_static_init();
  result = OSMetaClass::postModLoad(handle);
  if (result) { thyme_pmgr_observation[1] = static_cast<uint32_t>(result); thyme_pmgr_checkpoint(); return; }
  thyme_pmgr_observation[9] = ThymePlatformPower::gMetaClass.getInstanceCount();
  thyme_pmgr_observation[11] = nubMeta->getInstanceCount();
  ThymePlatformPower *provider = new ThymePlatformPower;
  IORegistryEntry *description = new IORegistryEntry;
  IOService *nub = nullptr;
  do {
    if (!provider || !description || !provider->init() || !description->init()) break;
    thyme_pmgr_observation[0] = 2;
    thyme_pmgr_observation[3] = provider->getMetaClass()->getClassSize();
    thyme_pmgr_observation[4] = reinterpret_cast<uintptr_t>(provider);
    // Empty resource description: no Apple register map or device capabilities.
    description->setName("thyme-platform-power");
    nub = thyme_original_pmgr_nub_create(description, provider);
    thyme_pmgr_observation[5] = reinterpret_cast<uintptr_t>(nub);
    if (!nub || nub->getMetaClass() != nubMeta || !provider->metaCast("ApplePMGR")) break;
    uintptr_t bound = 0;
    memcpy(&bound, reinterpret_cast<const char *>(nub) + 0x88, sizeof(bound));
    thyme_pmgr_observation[6] = bound;
    if (bound != reinterpret_cast<uintptr_t>(provider)) break;
    thyme_pmgr_observation[0] = 3;
    uint32_t value = thyme_original_pmgr_nub_read(nub);
    thyme_pmgr_observation[7] = value;
    thyme_original_pmgr_nub_write(nub, uint64_t(value | 4));
    thyme_pmgr_observation[8] = thyme_original_pmgr_nub_read(nub);
    thyme_pmgr_observation[13] = nub->getProvider() != nullptr || provider->getProvider() != nullptr;
    thyme_pmgr_observation[14] = (nub->getState() | provider->getState()) & kIOServiceRegisteredState;
    if (value != 0xffffffff || thyme_pmgr_observation[8] != 0xffffffff ||
        thyme_pmgr_observation[13] || thyme_pmgr_observation[14]) break;
    if (mode == 3) provider->disableCPUCore(1);
    if (mode == 2) {
      IOService *platform = IOService::getPlatform();
      if (!platform || !provider->attach(platform)) break;
      if (!provider->start(platform)) { provider->detach(platform); break; }
      if (!nub->attach(provider)) {
        provider->stop(platform); provider->detach(platform); break;
      }
      if (!nub->start(provider)) {
        nub->detach(provider); provider->stop(platform); provider->detach(platform); break;
      }
      provider->registerService(kIOServiceSynchronous);
      nub->registerService(kIOServiceSynchronous);
      thyme_pmgr_observation[0] = 5;
      thyme_pmgr_observation[13] = nub->getProvider() == provider && provider->getProvider() == platform;
      thyme_pmgr_observation[14] = (nub->getState() & provider->getState()) & kIOServiceRegisteredState;
      auto matching = IOService::serviceMatching("ApplePMGRNub");
      IOService *matched = matching ? IOService::waitForMatchingService(matching, 1000000) : nullptr;
      OSSafeReleaseNULL(matching);
      // Check actual service discovery and genuine type identity, then retain
      // both live objects. The registry and original nub refer to this provider.
      if (matched != nub || matched->getMetaClass() != nubMeta ||
          !thyme_pmgr_observation[13] || !thyme_pmgr_observation[14]) {
        thyme_pmgr_checkpoint();
        panic("ThymePlatformPower: original nub publication failed");
      }
      thyme_pmgr_observation[10] = ThymePlatformPower::gMetaClass.getInstanceCount();
      thyme_pmgr_observation[12] = nubMeta->getInstanceCount();
      thyme_pmgr_observation[1] = kIOReturnSuccess;
      OSSafeReleaseNULL(matched);
      OSSafeReleaseNULL(description);
      thyme_pmgr_checkpoint();
      return;
    }
    thyme_pmgr_observation[1] = kIOReturnSuccess;
  } while (false);
  OSSafeReleaseNULL(nub);
  OSSafeReleaseNULL(description);
  OSSafeReleaseNULL(provider);
  thyme_pmgr_observation[10] = ThymePlatformPower::gMetaClass.getInstanceCount();
  thyme_pmgr_observation[12] = nubMeta->getInstanceCount();
  if (thyme_pmgr_observation[9] != thyme_pmgr_observation[10] ||
      thyme_pmgr_observation[11] != thyme_pmgr_observation[12]) thyme_pmgr_observation[1] = static_cast<uint32_t>(kIOReturnError);
  thyme_pmgr_observation[0] = 4;
  thyme_pmgr_checkpoint();
}
