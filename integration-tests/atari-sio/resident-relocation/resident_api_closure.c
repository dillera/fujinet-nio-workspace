/* Link-closure measurement for Story 2.5.  It is never installed or run as a
 * CIO handler: every public call is here solely to make ld65 select the exact
 * current fn_open/read/write/info/close archive closure. */
#include <stdint.h>

#include "fujinet-nio.h"

static fn_handle_t handles[2];
static uint8_t caches[2][128];
static uint16_t transfer_count;
static uint16_t http_status;
static uint32_t content_length;
static uint8_t info_flags;
static uint8_t read_flags;
static volatile uint8_t result_sink;

int main(void)
{
    static const char uri[] = "fixture://resident-closure";
    uint8_t status;

    status = fn_init();
    status |= fn_open(&handles[0], FN_METHOD_GET, uri, 0);
    status |= fn_write(handles[0], 0, caches[0], sizeof(caches[0]),
                       &transfer_count);
    status |= fn_read(handles[0], 0, caches[1], sizeof(caches[1]),
                      &transfer_count, &read_flags);
    status |= fn_info(handles[0], &http_status, &content_length, &info_flags);
    status |= fn_close(handles[0]);
    result_sink = status;
    return status;
}
