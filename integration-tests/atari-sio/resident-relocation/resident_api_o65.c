/* Story 2.5 relocation feasibility only: force the actual Atari public API
 * closure into a loadable o65 module.  This is not a CIO handler, an
 * installer, or a replacement service peer. */
#include <stdint.h>

#include "fujinet-nio.h"

struct resident_api_o65_result {
    uint8_t status;
    uint8_t read_flags;
    uint8_t read_data[4];
    uint16_t handle;
    uint16_t written;
    uint16_t read;
    uint16_t http_status;
    uint32_t content_length;
};

/* Representative state required by the eventual handler: two bounded cache
 * slots and two public-library handle slots. */
static fn_handle_t handles[2];
static uint8_t caches[2][128];
static uint16_t written;
static uint16_t read;
static uint16_t http_status;
static uint32_t content_length;
static uint8_t info_flags;

struct resident_api_o65_result resident_api_o65_result;

uint8_t resident_api_o65_exercise(void)
{
    static const char uri[] = "fixture://resident-o65";
    uint8_t status;

    status = fn_init();
    if (status == FN_OK) {
        status = fn_open(&handles[0], FN_METHOD_GET, uri, 0);
    }
    if (status == FN_OK) {
        status = fn_write(handles[0], 0, (const uint8_t *)"O65!", 4, &written);
    }
    if (status == FN_OK) {
        status = fn_read(handles[0], 0, caches[0], 4, &read, &info_flags);
    }
    if (status == FN_OK) {
        status = fn_info(handles[0], &http_status, &content_length, &info_flags);
    }
    if (status == FN_OK) {
        status = fn_close(handles[0]);
    }

    resident_api_o65_result.status = status;
    resident_api_o65_result.read_flags = info_flags;
    resident_api_o65_result.read_data[0] = caches[0][0];
    resident_api_o65_result.read_data[1] = caches[0][1];
    resident_api_o65_result.read_data[2] = caches[0][2];
    resident_api_o65_result.read_data[3] = caches[0][3];
    resident_api_o65_result.handle = handles[0];
    resident_api_o65_result.written = written;
    resident_api_o65_result.read = read;
    resident_api_o65_result.http_status = http_status;
    resident_api_o65_result.content_length = content_length;
    return status;
}
