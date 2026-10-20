---
title: 'Atari ESP32 IRAM snapshot after Story 1.1'
type: 'measurement-record'
created: '2026-10-20'
status: 'recorded'
baseline_commit: 'd0dc8079'
comparison_commit: '47d362fe'
---

# Atari ESP32 IRAM Snapshot — Post Story 1.1

This is a point-in-time memory-layout record made after Story 1.1's fixture
contract was complete. It is not a protocol requirement, acceptance criterion,
or request to reopen Story 1.1. It records the pre-Story-1.2 firmware baseline
and the subsequently measured Story 1.2 comparison for the classic ESP32 Atari
FujiNet v1 16 MB target.

## Measurement Conditions

- Target: `atari-nio-fujibus-sio-gpio-fujinet-v1-16mb`, classic ESP32.
- Toolchain: PlatformIO `espressif32@6.10.0`, ESP-IDF 5.4.0, Xtensa GCC 14.2.0.
- Build procedure: `source "$NIO_WORKSPACE/scripts/env.sh && ./build.sh -cb`.
- The clean procedure regenerates `sdkconfig.defaults`, selecting
  `spiram-quad40.defaults`; it is required for comparable results.
- Linker output: `.pio/build/atari-nio-fujibus-sio-gpio-fujinet-v1-16mb/fujinet-nio.map`.

## Region and Build Results

`iram0_0_seg` begins at `0x40080000` and is `0x20000` bytes (131,072 bytes).
The output `.iram0.text` begins at `0x40080404`.

| Build | `.iram0.text` | Used from region origin | Free | Result |
| --- | ---: | ---: | ---: | --- |
| Pre-Story 1.2 `d0dc8079`, Debug | 122,603 | 123,631 | 7,441 | links |
| Story 1.2 `47d362fe`, Debug | 123,255 | 124,283 | 6,789 | links |
| Story 1.2, Release size diagnostic | 123,215 | 124,243 | 6,829 | links |

Story 1.2 changes the Debug IRAM total by +652 bytes. The previously reported
4,840-byte overflow was not reproducible under the regenerated Atari target
configuration: it corresponded to a stale/mismatched generated sdkconfig, not
to the Story 1.2 source delta.

## Complete Placement Accounting

The 123,255 bytes comprise 121,976 bytes from 205 object files and 1,279 bytes
of linker alignment fill. A partial map parser can falsely label approximately
66 KB as “other” because ESP-IDF emits both section-plus-object and source-only
map records. There is no opaque 66 KB component.

| Component group | Bytes |
| --- | ---: |
| FreeRTOS | 18,285 |
| PSRAM cache-workaround libc | 14,760 |
| Wi-Fi binary | 14,539 |
| SPI flash | 9,083 |
| PHY binary | 8,970 |
| ESP PSRAM | 8,621 |
| HAL | 8,151 |
| Hardware support | 7,880 |
| Heap | 7,492 |
| Remaining ESP-IDF, firmware, and fill | 18,195 |

## Largest Twenty Object Files

All entries are in output section `.iram0.text`.

| Bytes | Object | Placement rationale |
| ---: | --- | --- |
| 10,385 | FreeRTOS `tasks.c.o` | scheduler/cache-safe execution |
| 8,202 | `esp_psram_impl_quad.c.o` | PSRAM/cache-workaround support |
| 5,359 | heap `tlsf.c.o` | allocator safety |
| 4,671 | FreeRTOS `ringbuf.c.o` | RTOS primitive |
| 4,027 | PHY `phy_chip_v7_cal.o` | Wi-Fi/radio path |
| 3,997 | Wi-Fi `pm.o` | Wi-Fi power-management path |
| 3,894 | Wi-Fi `wdev.o` | Wi-Fi device/RX path |
| 3,174 | PSRAM libc `libc_a-strftime.o` | cache-workaround libc |
| 3,083 | SPI `spi_master.c.o` | flash/PSRAM transaction safety |
| 3,075 | flash `esp_flash_api.c.o` | flash-operation safety |
| 3,044 | FreeRTOS `queue.c.o` | RTOS primitive |
| 2,861 | flash `spi_flash_chip_generic.c.o` | flash-operation safety |
| 2,761 | PHY `phy_chip_v7_ana.o` | Wi-Fi/radio path |
| 2,447 | hardware support `rtc_clk.c.o` | clock/cache transition support |
| 2,219 | HAL `spi_hal_iram.c.o` | SPI flash/PSRAM safety |
| 2,182 | PHY `phy_chip_v7.o` | Wi-Fi/radio path |
| 2,138 | HAL `spi_flash_hal_iram.c.o` | flash-operation safety |
| 2,092 | Wi-Fi `pp.o` | packet-processing path |
| 1,581 | FreeRTOS `stream_buffer.c.o` | RTOS primitive |
| 1,537 | HAL `wdt_hal_iram.c.o` | watchdog/interrupt safety |

## Optional-Placement Audit

The principal placement is cache-disabled, PSRAM, flash, FreeRTOS, and
interrupt-safety code—not optional performance code. The effective config has
`CONFIG_ESP_WIFI_IRAM_OPT=n`, `CONFIG_ESP_WIFI_EXTRA_IRAM_OPT=n`,
`CONFIG_LWIP_IRAM_OPTIMIZATION=n`, `CONFIG_LWIP_EXTRA_IRAM_OPTIMIZATION=n`,
`CONFIG_GPIO_CTRL_FUNC_IN_IRAM=n`, and `CONFIG_UART_ISR_IN_IRAM=n`.

`CONFIG_ESP_WIFI_RX_IRAM_OPT=y` remains enabled. Wi-Fi and PHY contribute about
24 KB combined, but the map alone cannot separate vendor-required cache-safe
radio code from the removable RX optimisation subset. Establishing that subset
requires a controlled sdkconfig A/B build; no configuration change was made for
this snapshot.
