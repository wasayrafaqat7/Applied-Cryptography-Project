#include <string.h>
#include "ratchet.h"
#include "sha256.h"

static const char SEED_LABEL[] = "fsk-probe/seed/v1|";
static const char NEXT_LABEL[] = "fsk-probe/next/v1|";

void ratchet_seed(const char *seed, uint8_t out[RATCHET_KEY_LEN])
{
    sha256_ctx_t ctx;
    sha256_init(&ctx);
    sha256_update(&ctx, SEED_LABEL, sizeof(SEED_LABEL) - 1);
    sha256_update(&ctx, seed, strlen(seed));
    sha256_final(&ctx, out);
}

void ratchet_next(const uint8_t in[RATCHET_KEY_LEN], uint8_t out[RATCHET_KEY_LEN])
{
    sha256_ctx_t ctx;
    sha256_init(&ctx);
    sha256_update(&ctx, NEXT_LABEL, sizeof(NEXT_LABEL) - 1);
    sha256_update(&ctx, in, RATCHET_KEY_LEN);
    sha256_final(&ctx, out);
}

void secure_zero(void *p, size_t n)
{
    volatile uint8_t *v = (volatile uint8_t *)p;
    while (n--) {
        *v++ = 0;
    }
}
