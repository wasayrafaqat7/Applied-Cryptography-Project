/*
 * Forward-secure hash ratchet used by the probe.
 *
 *   k_0     = SHA-256("fsk-probe/seed/v1|" || seed)
 *   k_{i+1} = SHA-256("fsk-probe/next/v1|" || k_i)
 *
 * After each step the device must forget k_i. Because SHA-256 is one-way,
 * someone who steals k_{i+1} cannot compute k_i. The whole point of the
 * experiment is to check whether k_i really disappears from flash.
 *
 * The seed is fixed and known to the analysis script, so the script can
 * recompute every k_i and search a flash dump for it. A real device would use
 * a random k_0; a known seed only makes the measurement possible.
 */
#pragma once

#include <stddef.h>
#include <stdint.h>

#define RATCHET_KEY_LEN 32

void ratchet_seed(const char *seed, uint8_t out[RATCHET_KEY_LEN]);
void ratchet_next(const uint8_t in[RATCHET_KEY_LEN], uint8_t out[RATCHET_KEY_LEN]);

/* memset that the compiler is not allowed to remove */
void secure_zero(void *p, size_t n);
