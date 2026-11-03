/** @file
 * @brief Check the installed native radio SDK and runtime without opening
 * hardware.
 */
#include <dlfcn.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <usbradioplus_product.h>

_Static_assert(URP_NATIVE_CONFIG_ABI_VERSION == 3,
               "native radio configuration ABI 3 required");
_Static_assert(offsetof(UrpNativeStationConfig, processing_configuration) <
                   offsetof(UrpNativeStationConfig,
                            receive_deemphasis_corner_hz),
               "native processing configuration fields required");

/** Verify the native descriptor tail, then close the library without creating a
 * station. */
int main(void) {
  void *library = dlopen("libusbradioplus_product.so.1", RTLD_NOW | RTLD_LOCAL);
  if (!library) {
    fputs("native radio runtime could not be loaded\n", stderr);
    return 1;
  }
  typedef const UrpAstDescriptor *(*descriptor_fn)(void);
  descriptor_fn describe =
      (descriptor_fn)dlsym(library, "usbradioplus_product_descriptor_v1");
  const UrpAstDescriptor *api = describe ? describe() : NULL;
  const size_t required = offsetof(UrpAstDescriptor, link_process_f32) +
                          sizeof(api->link_process_f32);
  const int valid =
      api && api->struct_size >= required && api->abi_version == 1 &&
      api->capability_name &&
      strcmp(api->capability_name, "usbradioplus.product1") == 0 &&
      api->native_create && api->native_start && api->native_stop &&
      api->native_destroy && api->link_destroy &&
      api->native_processing_validate && api->native_link_prepare &&
      api->link_process_f32;
  if (!valid)
    fputs("native radio runtime lacks the required processing operations\n",
          stderr);
  dlclose(library);
  return valid ? 0 : 1;
}
