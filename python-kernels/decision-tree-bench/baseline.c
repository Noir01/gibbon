// Conventional array-of-structs decision-tree inference (the layout used by
// scikit-learn and most native runtimes), reading the same input files as the
// Gibbon program and printing results in the same format.
//
// usage: baseline NODES NUM_NODES FEATURES NUM_ROWS NUM_FEATURES ITERS
#define _GNU_SOURCE
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

typedef struct { int32_t feature; float threshold; int32_t left; int32_t right; } Node;

static double now(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC_RAW, &t);
    return t.tv_sec + t.tv_nsec * 1e-9;
}

static int cmp(const void *a, const void *b) {
    double x = *(const double *)a, y = *(const double *)b;
    return (x > y) - (x < y);
}

static int64_t predict(const Node *nodes, const float *x) {
    int32_t i = 0;
    while (nodes[i].feature >= 0)
        i = x[nodes[i].feature] <= nodes[i].threshold ? nodes[i].left : nodes[i].right;
    return nodes[i].right;
}

int main(int argc, char **argv) {
    if (argc != 7) { fprintf(stderr, "usage: %s NODES NUM_NODES FEATURES NUM_ROWS NUM_FEATURES ITERS\n", argv[0]); return 2; }
    long nn = atol(argv[2]), rows = atol(argv[4]), nf = atol(argv[5]), iters = atol(argv[6]);
    FILE *f = fopen(argv[1], "r");
    Node *nodes = malloc(nn * sizeof(Node));
    for (long i = 0; i < nn; i++) {
        long feat, l, r, c; float t;
        if (fscanf(f, "%ld %f %ld %ld %ld", &feat, &t, &l, &r, &c) != 5) { fprintf(stderr, "bad nodes file\n"); return 1; }
        nodes[i] = (Node){ (int32_t)feat, t, (int32_t)l, (int32_t)(feat < 0 ? c : r) };
    }
    fclose(f);
    f = fopen(argv[3], "r");
    float *x = malloc(rows * nf * sizeof(float));
    for (long i = 0; i < rows * nf; i++)
        if (fscanf(f, "%f", &x[i]) != 1) { fprintf(stderr, "bad features file\n"); return 1; }
    fclose(f);
    int64_t *out = malloc(rows * sizeof(int64_t));
    double *times = malloc(iters * sizeof(double)), total = 0;
    for (long it = 0; it < iters; it++) {
        double t0 = now();
        for (long r = 0; r < rows; r++) out[r] = predict(nodes, x + r * nf);
        times[it] = now() - t0;
        total += times[it];
        __asm__ volatile("" : : "r"(out) : "memory");
    }
    qsort(times, iters, sizeof(double), cmp);
    printf("ITERS: %ld\nSIZE: %ld\nBATCHTIME: %e\nSELFTIMED: %e\n", iters, rows, total, times[iters / 2]);
    for (long r = 0; r < rows; r++) printf("%ld\n", (long)out[r]);
    return 0;
}
