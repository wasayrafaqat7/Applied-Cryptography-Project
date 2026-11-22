/*
 * stale-key-probe: does a forward-secure key really disappear from flash?
 *
 * The probe runs a SHA-256 hash ratchet (see ratchet.h) and stores its state
 * in ESP-IDF NVS (Non-Volatile Storage) after every step, exactly as a
 * forward-secure application would. Afterwards you dump the NVS partition and
 * run tools/stale_keys.py, which counts how many *old* keys are still in flash.
 *
 * State blob "st" (namespace "fsk"), 36 bytes:
 *     epoch (uint32, little-endian) || key (32 bytes)
 * Key and epoch sit in ONE blob so an update is a single NVS write. Two
 * separate items could be torn apart by a power cut, which matters once the
 * continuous mode is used for power-cut tests.
 *
 * Every machine-readable line starts with "PROBE " so a logger or the
 * power-cut rig can parse the serial output.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <inttypes.h>

#include "sdkconfig.h"
#include "esp_err.h"
#include "esp_log.h"
#include "esp_idf_version.h"
#include "esp_partition.h"
#include "nvs.h"
#include "nvs_flash.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "ratchet.h"

#if CONFIG_PROBE_NVS_PURGE || CONFIG_PROBE_PURGE_ALL_AT_END
/*
 * Purge mode (NVS_READWRITE_PURGE, nvs_purge_all) is documented from the
 * ESP-IDF release-v6.0 branch, but we have only tested it on v6.1. Refuse to
 * build below v6.1.0 so a result is never silently produced on an untested
 * version; lower this deliberately after testing a v6.0.x release.
 */
#if ESP_IDF_VERSION < ESP_IDF_VERSION_VAL(6, 1, 0)
#error "NVS purge mode is documented from ESP-IDF v6.0 but tested only on v6.1: build with v6.1 or newer."
#endif
#endif

#define NS_NAME   "fsk"
#define STATE_KEY "st"
#define STATE_LEN (4 + RATCHET_KEY_LEN)

static const char *TAG = "probe";

static nvs_open_mode_t probe_open_mode(void)
{
#if CONFIG_PROBE_NVS_PURGE
    return NVS_READWRITE_PURGE;
#else
    return NVS_READWRITE;
#endif
}

static const char *probe_mode_name(void)
{
#if CONFIG_PROBE_NVS_PURGE && CONFIG_PROBE_PURGE_ALL_AT_END
    return "purge+purgeall";
#elif CONFIG_PROBE_NVS_PURGE
    return "purge";
#elif CONFIG_PROBE_PURGE_ALL_AT_END
    return "purgeall";
#else
    return "default";
#endif
}

/*
 * Stop without touching flash. In continuous mode (power-cut tests) a failed
 * init or a corrupt state blob IS the measurement: the rig must see the error
 * on serial and then dump the flash as it is. Erasing and reseeding here
 * would hide the boot failure and destroy the stale keys we want to count.
 */
static void probe_fail(const char *stage, esp_err_t err)
{
    printf("PROBE FAIL stage=%s err=%s\n", stage, esp_err_to_name(err));
    fflush(stdout);
#if CONFIG_IDF_TARGET_LINUX
    exit(1);
#else
    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
#endif
}

#define PROBE_CHECK(stage, expr)              \
    do {                                      \
        esp_err_t err_rc_ = (expr);           \
        if (err_rc_ != ESP_OK) {              \
            probe_fail((stage), err_rc_);     \
        }                                     \
    } while (0)

static void pack_state(uint8_t out[STATE_LEN], uint32_t epoch, const uint8_t key[RATCHET_KEY_LEN])
{
    out[0] = (uint8_t)(epoch);
    out[1] = (uint8_t)(epoch >> 8);
    out[2] = (uint8_t)(epoch >> 16);
    out[3] = (uint8_t)(epoch >> 24);
    memcpy(out + 4, key, RATCHET_KEY_LEN);
}

static void print_key_prefix(const char *what, uint32_t epoch, const uint8_t key[RATCHET_KEY_LEN])
{
    /* Only the first 4 bytes: enough to cross-check with the parser. */
    printf("PROBE %s epoch=%" PRIu32 " key_prefix=%02x%02x%02x%02x\n",
           what, epoch, key[0], key[1], key[2], key[3]);
}

static esp_err_t store_state(nvs_handle_t h, uint32_t epoch, const uint8_t key[RATCHET_KEY_LEN])
{
    uint8_t buf[STATE_LEN];
    pack_state(buf, epoch, key);
    esp_err_t err = nvs_set_blob(h, STATE_KEY, buf, sizeof(buf));
    if (err == ESP_OK) {
        err = nvs_commit(h);
    }
    secure_zero(buf, sizeof(buf));
    return err;
}

/* Returns ESP_OK and fills epoch/key, or ESP_ERR_NVS_NOT_FOUND on a fresh device. */
static esp_err_t load_state(nvs_handle_t h, uint32_t *epoch, uint8_t key[RATCHET_KEY_LEN])
{
    uint8_t buf[STATE_LEN];
    size_t len = sizeof(buf);
    esp_err_t err = nvs_get_blob(h, STATE_KEY, buf, &len);
    if (err == ESP_OK && len != STATE_LEN) {
        err = ESP_ERR_INVALID_SIZE;
    }
    if (err == ESP_OK) {
        *epoch = (uint32_t)buf[0] | ((uint32_t)buf[1] << 8) |
                 ((uint32_t)buf[2] << 16) | ((uint32_t)buf[3] << 24);
        memcpy(key, buf + 4, RATCHET_KEY_LEN);
    }
    secure_zero(buf, sizeof(buf));
    return err;
}

static void init_nvs(void)
{
#if CONFIG_PROBE_MODE_BATCH
#if CONFIG_PROBE_ERASE_AT_START
    ESP_LOGI(TAG, "Erasing the NVS partition for a clean run");
    PROBE_CHECK("erase", nvs_flash_erase());
#endif
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        /* Batch runs start from a clean partition anyway, so reformatting is harmless. */
        printf("PROBE REFORMAT err=%s\n", esp_err_to_name(err));
        PROBE_CHECK("erase", nvs_flash_erase());
        err = nvs_flash_init();
    }
    PROBE_CHECK("init", err);
#else
    /*
     * Continuous mode: never reformat. ESP_ERR_NVS_NO_FREE_PAGES after a power
     * cut is one of the outcomes C2 counts. To start a fresh continuous run,
     * erase the partition by hand (see docs/reproduce.md).
     */
    PROBE_CHECK("init", nvs_flash_init());
#endif
}

static void print_partition_and_stats(void)
{
    const esp_partition_t *p = esp_partition_find_first(ESP_PARTITION_TYPE_DATA,
                                                        ESP_PARTITION_SUBTYPE_DATA_NVS, NULL);
    if (p) {
        printf("PROBE PARTITION label=%s offset=0x%" PRIx32 " size=0x%" PRIx32 "\n",
               p->label, (uint32_t)p->address, (uint32_t)p->size);
    }
    nvs_stats_t st;
    if (nvs_get_stats(NULL, &st) == ESP_OK) {
        printf("PROBE NVS_STATS used=%u free=%u total=%u namespaces=%u\n",
               (unsigned)st.used_entries, (unsigned)st.free_entries,
               (unsigned)st.total_entries, (unsigned)st.namespace_count);
    }
}

#if CONFIG_IDF_TARGET_LINUX
/* Host (Linux) build only: write the emulated NVS partition to a file. */
static void dump_partition_to_file(const char *path)
{
    const esp_partition_t *p = esp_partition_find_first(ESP_PARTITION_TYPE_DATA,
                                                        ESP_PARTITION_SUBTYPE_DATA_NVS, NULL);
    if (!p) {
        ESP_LOGE(TAG, "No NVS partition found");
        return;
    }
    uint8_t *buf = malloc(p->size);
    if (!buf) {
        return;
    }
    if (esp_partition_read_raw(p, 0, buf, p->size) == ESP_OK) {
        FILE *f = fopen(path, "wb");
        if (f) {
            fwrite(buf, 1, p->size, f);
            fclose(f);
            printf("PROBE DUMP path=%s bytes=%" PRIu32 "\n", path, (uint32_t)p->size);
        }
    }
    free(buf);
}
#endif

void app_main(void)
{
    printf("PROBE START idf=%s mode=%s seed=\"%s\"",
           esp_get_idf_version(), probe_mode_name(), CONFIG_PROBE_SEED);
#if CONFIG_PROBE_MODE_BATCH
    printf(" run=batch updates=%d\n", CONFIG_PROBE_NUM_UPDATES);
#else
    printf(" run=continuous\n");
#endif

    init_nvs();

    nvs_handle_t h;
    PROBE_CHECK("open", nvs_open(NS_NAME, probe_open_mode(), &h));

    uint32_t epoch = 0;
    uint8_t key[RATCHET_KEY_LEN];
    uint8_t next[RATCHET_KEY_LEN];

    esp_err_t err = load_state(h, &epoch, key);
    if (err == ESP_ERR_NVS_NOT_FOUND) {
        epoch = 0;
        ratchet_seed(CONFIG_PROBE_SEED, key);
        PROBE_CHECK("store_init", store_state(h, epoch, key));
        print_key_prefix("INIT", epoch, key);
    } else {
        PROBE_CHECK("load", err);
        print_key_prefix("RESUME", epoch, key);
    }

#if CONFIG_PROBE_MODE_BATCH
    uint32_t num_updates = CONFIG_PROBE_NUM_UPDATES;
#if CONFIG_IDF_TARGET_LINUX
    /* host builds only: PROBE_UPDATES=500 ./stale_key_probe.elf, for quick sweeps */
    const char *env = getenv("PROBE_UPDATES");
    if (env && atoi(env) > 0) {
        num_updates = (uint32_t)atoi(env);
        printf("PROBE OVERRIDE updates=%" PRIu32 "\n", num_updates);
    }
#endif
    const uint32_t target = epoch + num_updates;
    while (epoch < target) {
#else
    for (;;) {
#endif
        ratchet_next(key, next);
        epoch++;
        err = store_state(h, epoch, next);
        if (err != ESP_OK) {
            printf("PROBE ERROR epoch=%" PRIu32 " err=%s\n", epoch, esp_err_to_name(err));
            break;
        }
        /* forget the old key in RAM; whether flash forgets it is what we measure */
        memcpy(key, next, RATCHET_KEY_LEN);
        secure_zero(next, sizeof(next));
        print_key_prefix("UPD", epoch, key);

        if (CONFIG_PROBE_UPDATE_DELAY_MS > 0) {
            vTaskDelay(pdMS_TO_TICKS(CONFIG_PROBE_UPDATE_DELAY_MS));
        } else if ((epoch % 16) == 0) {
            vTaskDelay(1); /* let the idle task run so the watchdog stays quiet */
        }
    }

#if CONFIG_PROBE_PURGE_ALL_AT_END
    ESP_LOGI(TAG, "Calling nvs_purge_all() on the namespace");
    PROBE_CHECK("purge_all", nvs_purge_all(h));
    printf("PROBE PURGE_ALL done\n");
#endif

    secure_zero(key, sizeof(key));
    nvs_close(h);

    print_partition_and_stats();
    printf("PROBE DONE epoch=%" PRIu32 "\n", epoch);

#if CONFIG_IDF_TARGET_LINUX
    dump_partition_to_file(CONFIG_PROBE_LINUX_DUMP_PATH);
    fflush(stdout);
    exit(0);
#else
    printf("PROBE NEXT dump the NVS partition, e.g. "
           "parttool.py --port PORT read_partition --partition-name=nvs --output nvs.bin\n");
#endif
}
