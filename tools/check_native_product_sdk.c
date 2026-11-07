/** @file
 * @brief Check the installed native radio SDK and runtime without opening
 * hardware.
 */
#include <dlfcn.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <usbradioplus_product.h>

_Static_assert(URP_NATIVE_CONFIG_ABI_VERSION == 4,
               "native radio configuration ABI 4 required");
_Static_assert(URP_AST_DIRECT_CALLBACKS_ABI_VERSION == 6,
               "native direct callback ABI 6 required");
_Static_assert(offsetof(UrpNativeStationConfig, processing_configuration) <
                   offsetof(UrpNativeStationConfig,
                            receive_deemphasis_corner_hz),
               "native processing configuration fields required");

/** Verify the complete SDK32 descriptor before reading configuration, control,
 * observation, remote operations and asynchronous activation readiness. No
 * station is created. */
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
  const size_t required =
      offsetof(UrpAstDescriptor, channel_activation_status) +
      sizeof(api->channel_activation_status);
  const int valid =
      api && api->struct_size >= required && api->abi_version == 1 &&
      api->capability_name &&
      strcmp(api->capability_name, "usbradioplus.product1") == 0 &&
      api->native_create && api->native_start && api->native_stop &&
      api->native_destroy && api->link_destroy &&
      api->native_processing_validate && api->native_link_prepare &&
      api->link_process_f32 && api->native_configuration_resolve &&
      api->native_configuration_visit && api->native_configuration_destroy &&
      api->native_get_status && api->native_command &&
      api->native_set_transmit && api->native_clear_manual &&
      api->native_prepare_update && api->native_begin_update &&
      api->native_accept_update && api->native_finish_update &&
      api->native_destroy_update && api->native_status_text &&
      api->native_processing_status_text && api->link_observer_create &&
      api->link_observer_read && api->link_observer_destroy &&
      api->native_service && api->native_remote_submit &&
      api->channel_remote_submit && api->remote_source && api->remote_take &&
      api->remote_destroy && api->native_quiesce && api->channel_quiesce &&
      api->native_configuration_remote_options &&
      api->native_activation_status && api->channel_activation_status;
  if (!valid)
    fputs("native radio runtime lacks the required SDK32 operations\n", stderr);
  dlclose(library);
  return valid ? 0 : 1;
}
