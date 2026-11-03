/*
 * Bridge to NASA CryptoLib (CCSDS SDLS, shipped with NOS3) for
 * interoperability tests of SENTINEL-LINK's SDLS implementation.
 *
 *   bridge apply   <key_hex>   < data fields (hex, one per line)  > protected TM frames (hex)
 *   bridge process <key_hex>   < protected TM frames (hex)        > "<status> <data_hex>" per line
 *
 * One TM virtual channel (TFVN 0, SCID 44, VCID 0), SA SPI 5:
 * authentication only, HMAC-SHA-256 truncated to 16 bytes, 4-byte ARSN in the
 * security header, anti-replay window 64, authentication bit mask all ones.
 * Frame: primary header 6 | SPI 2 | ARSN 4 | data 256 | MAC 16 | FECF 2 = 286.
 * SA state (ARSN) persists for the whole run, so replays inside one run are
 * judged by CryptoLib's own anti-replay check.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "crypto.h"
#include "sa_interface.h"
#include "key_interface.h"

#define SPI 5
#define DATA_LEN 256
#define FRAME_LEN (6 + 2 + 4 + DATA_LEN + 16 + 2)

static int hex2bin(const char *h, uint8_t *out, int max)
{
    int n = 0;
    while (h[0] && h[1] && n < max) {
        if (h[0] == '\n' || h[0] == '\r') break;
        unsigned v;
        if (sscanf(h, "%2x", &v) != 1) return -1;
        out[n++] = (uint8_t)v;
        h += 2;
    }
    return n;
}

static void print_hex(const uint8_t *b, int n)
{
    for (int i = 0; i < n; i++) printf("%02x", b[i]);
}

static int setup(const char *key_hex)
{
    Crypto_Config_CryptoLib(KEY_TYPE_INTERNAL, MC_TYPE_INTERNAL, SA_TYPE_INMEMORY, CRYPTOGRAPHY_TYPE_LIBGCRYPT,
                            IV_INTERNAL, CRYPTO_TM_CREATE_FECF_TRUE, TC_PROCESS_SDLS_PDUS_TRUE, TC_HAS_PUS_HDR,
                            TC_IGNORE_SA_STATE_FALSE, TC_IGNORE_ANTI_REPLAY_FALSE, TC_UNIQUE_SA_PER_MAP_ID_FALSE,
                            TM_CHECK_FECF_TRUE, 0x3F, SA_INCREMENT_NONTRANSMITTED_IV_TRUE);
    GvcidManagedParameters_t mp = {0, 0x002c, 0, TM_HAS_FECF, AOS_FHEC_NA, AOS_IZ_NA, 0,
                                   TM_SEGMENT_HDRS_NA, FRAME_LEN, TM_NO_OCF, 1};
    Crypto_Config_Add_Gvcid_Managed_Parameters(mp);
    int32_t st = Crypto_Init();
    if (st != CRYPTO_LIB_SUCCESS) return st;

    SaInterface sa_if = get_sa_interface_inmemory();
    SecurityAssociation_t *sa = NULL;
    sa_if->sa_get_from_spi(1, &sa);
    sa->sa_state = SA_KEYED;               /* take the default SA off this channel */
    sa_if->sa_get_from_spi(SPI, &sa);
    sa->sa_state       = SA_OPERATIONAL;
    sa->gvcid_blk.tfvn = 0;
    sa->gvcid_blk.scid = 44;
    sa->gvcid_blk.vcid = 0;
    sa->ast = 1;
    sa->est = 0;
    sa->shivf_len = 0;
    sa->iv_len    = 0;
    sa->shsnf_len = 4;
    sa->arsn_len  = 4;
    memset(sa->arsn, 0, ARSN_SIZE);
    sa->arsnw_len = 1;
    sa->arsnw     = 64;
    sa->shplf_len = 0;
    sa->abm_len   = FRAME_LEN;
    memset(sa->abm, 0xFF, FRAME_LEN);
    sa->stmacf_len = 16;
    sa->ecs = CRYPTO_CIPHER_NONE;
    sa->acs = CRYPTO_MAC_HMAC_SHA256;
    sa->ecs_len = 1;
    sa->acs_len = 1;
    sa->ekid = 0;
    sa->akid = 136;

    crypto_key_t *ak = key_if->get_key(sa->akid);
    int klen = hex2bin(key_hex, ak->value, KEY_SIZE);
    if (klen != 32) return -1000;
    ak->key_len   = 32;
    ak->key_state = KEY_ACTIVE;
    key_if->get_key(sa->ekid)->key_state = KEY_ACTIVE;
    return CRYPTO_LIB_SUCCESS;
}

int main(int argc, char **argv)
{
    if (argc != 3) {
        fprintf(stderr, "usage: bridge apply|process <key_hex>\n");
        return 2;
    }
    int32_t st = setup(argv[2]);
    if (st != CRYPTO_LIB_SUCCESS) {
        fprintf(stderr, "setup failed: %d\n", st);
        return 1;
    }
    static char line[8192];
    uint8_t buf[FRAME_LEN];
    uint8_t vcfc = 0;
    while (fgets(line, sizeof line, stdin)) {
        if (strcmp(argv[1], "apply") == 0) {
            memset(buf, 0, sizeof buf);
            buf[0] = 0x02; buf[1] = 0xC0;           /* TFVN 0, SCID 44, VCID 0, no OCF */
            buf[2] = vcfc; buf[3] = vcfc++;         /* master / virtual channel frame counts */
            buf[4] = 0x18; buf[5] = 0x00;           /* data field status */
            buf[6] = 0x00; buf[7] = SPI;
            if (hex2bin(line, buf + 12, DATA_LEN) != DATA_LEN) { printf("ERR_INPUT\n"); continue; }
            tm_frame_pri_hdr.tfvn = 0; tm_frame_pri_hdr.scid = 44; tm_frame_pri_hdr.vcid = 0;
            Crypto_Get_Managed_Parameters_For_Gvcid(0, 44, 0, gvcid_managed_parameters_array,
                                                    &tm_current_managed_parameters_struct);
            st = Crypto_TM_ApplySecurity(buf, FRAME_LEN);
            if (st != CRYPTO_LIB_SUCCESS) { printf("ERR %d\n", st); continue; }
            print_hex(buf, FRAME_LEN);
            printf("\n");
        } else {
            int n = hex2bin(line, buf, FRAME_LEN);
            uint8_t *out = NULL;
            uint16_t out_len = 0;
            st = Crypto_TM_ProcessSecurity(buf, (uint16_t)n, &out, &out_len);
            printf("%d ", st);
            if (st == CRYPTO_LIB_SUCCESS && out) print_hex(out + 12, DATA_LEN);
            printf("\n");
            free(out);
        }
        fflush(stdout);
    }
    Crypto_Shutdown();
    return 0;
}
