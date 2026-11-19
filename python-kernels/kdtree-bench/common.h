// Input and output shared by the C/C++ baselines: the same files the Gibbon
// program reads, and the same output format (build SELFTIMED line, then the
// iterate block, then one neighbour index per line).
#ifndef KDBENCH_COMMON_H
#define KDBENCH_COMMON_H
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

static double now(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC_RAW, &t);
    return t.tv_sec + t.tv_nsec * 1e-9;
}

static int cmp_double(const void *a, const void *b) {
    double x = *(const double *)a, y = *(const double *)b;
    return (x > y) - (x < y);
}

static float *read_floats(const char *path, long n) {
    FILE *f = fopen(path, "r");
    if (!f) { perror(path); exit(1); }
    float *x = (float *)malloc(n * sizeof(float));
    for (long i = 0; i < n; i++)
        if (fscanf(f, "%f", &x[i]) != 1) { fprintf(stderr, "bad file %s\n", path); exit(1); }
    fclose(f);
    return x;
}

static void print_results(double *times, long iters, long nq, const int64_t *out) {
    double total = 0;
    for (long it = 0; it < iters; it++) total += times[it];
    qsort(times, iters, sizeof(double), cmp_double);
    printf("ITERS: %ld\nSIZE: %ld\nBATCHTIME: %e\nSELFTIMED: %e\n", iters, nq, total, times[iters / 2]);
    for (long j = 0; j < nq; j++) printf("%ld\n", (long)out[j]);
}
#endif
