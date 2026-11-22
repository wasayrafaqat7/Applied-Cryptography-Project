/*
 * Minimal, dependency-free SHA-256 (FIPS 180-4).
 *
 * Kept self-contained on purpose: ESP-IDF v5.x ships Mbed TLS 3 and v6.x ships
 * Mbed TLS 4 / PSA, whose hash APIs differ. The probe only needs a hash that
 * the Python parser can reproduce with hashlib.sha256, so a small local copy
 * avoids version-specific code.
 */
#pragma once

#include <stddef.h>
#include <stdint.h>

#define SHA256_DIGEST_LEN 32

typedef struct {
    uint32_t state[8];
    uint64_t total_len;   /* bytes processed so far */
    uint8_t  block[64];
    size_t   block_len;
} sha256_ctx_t;

void sha256_init(sha256_ctx_t *ctx);
void sha256_update(sha256_ctx_t *ctx, const void *data, size_t len);
void sha256_final(sha256_ctx_t *ctx, uint8_t out[SHA256_DIGEST_LEN]);
