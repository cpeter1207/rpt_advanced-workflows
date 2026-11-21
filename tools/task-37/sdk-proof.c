#include <rptadvschedule/recurrence.h>
#include <string.h>
#include <usbradioplus_product.h>

int main(void)
{
    const UrpPreparationDescriptor *station = usbradioplus_preparation_descriptor();
    const UrpLinkPreparationDescriptor *link = usbradioplus_link_preparation_descriptor();
    return !(rptadv_recurrence_descriptor_valid(rptadv_recurrence_descriptor()) &&
             station && station->struct_size >= sizeof(*station) && station->abi_version == 1 &&
             station->capability_name && !strcmp(station->capability_name, "usbradioplus.preparation1") &&
             station->prepare && station->equal && station->create && station->prepare_update &&
             station->link_prepare && link && link->struct_size >= sizeof(*link) &&
             link->abi_version == 1 && link->capability_name &&
             !strcmp(link->capability_name, "usbradioplus.link-preparation1") &&
             link->prepare && link->equal && link->link_prepare && link->destroy);
}
