// Brute-force exact 1-NN: every query against every point, single thread.
// Same input files and output format as baseline.c; build time is zero.
//
// usage: brute POINTS NUM_POINTS QUERIES NUM_QUERIES DIMS ITERS
#include "common.h"

int main(int argc, char **argv) {
    if (argc != 7) { fprintf(stderr, "usage: %s POINTS NUM_POINTS QUERIES NUM_QUERIES DIMS ITERS\n", argv[0]); return 2; }
    long np = atol(argv[2]), nq = atol(argv[4]), dims = atol(argv[5]), iters = atol(argv[6]);
    const float *pts = read_floats(argv[1], np * dims);
    const float *qs = read_floats(argv[3], nq * dims);
    printf("SELFTIMED: %e\n", 0.0);

    int64_t *out = malloc(nq * sizeof(int64_t));
    double *times = malloc(iters * sizeof(double));
    for (long it = 0; it < iters; it++) {
        double s = now();
        for (long j = 0; j < nq; j++) {
            const float *q = qs + j * dims;
            float best_d = __builtin_inff();
            int64_t best_i = 0;
            for (long i = 0; i < np; i++) {
                const float *p = pts + i * dims;
                float acc = 0.0f;
                for (long k = 0; k < dims; k++) { float t = p[k] - q[k]; acc = acc + t * t; }
                if (acc < best_d) { best_d = acc; best_i = i; }
            }
            out[j] = best_i;
        }
        times[it] = now() - s;
        __asm__ volatile("" : : "r"(out) : "memory");
    }
    print_results(times, iters, nq, out);
    return 0;
}
