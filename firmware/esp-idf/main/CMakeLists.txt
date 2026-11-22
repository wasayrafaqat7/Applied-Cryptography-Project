idf_component_register(SRCS "probe_main.c"
                            "../../common/ratchet.c"
                            "../../common/sha256.c"
                       INCLUDE_DIRS "." "../../common"
                       REQUIRES nvs_flash esp_partition)
