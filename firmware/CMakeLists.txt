idf_component_register(SRCS "probe_main.c" "ratchet.c" "sha256.c"
                       INCLUDE_DIRS "."
                       REQUIRES nvs_flash esp_partition)
