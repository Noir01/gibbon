// Plain C k-d tree with the same algorithm as KDTree.hs.in (one point per node,
// axis cycling with depth, median split found by sorting (coordinate, index)
// keys), nodes in a flat array of structs. Reads the same input files as the
// Gibbon program and prints results in the same format, followed by the total
// number of nodes the queries visit.
//
// usage: baseline POINTS NUM_POINTS QUERIES NUM_QUERIES DIMS ITERS
#define _GNU_SOURCE
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

typedef struct { int32_t point; float split; int32_t left, right; } Node;
typedef struct { float key; int64_t index; } Key;

static const float *pts;
static long dims;
static Node *nodes;
static long num_nodes;

static double now(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC_RAW, &t);
    return t.tv_sec + t.tv_nsec * 1e-9;
}

static int cmp_double(const void *a, const void *b) {
    double x = *(const double *)a, y = *(const double *)b;
    return (x > y) - (x < y);
}

static int cmp_key(const void *a, const void *b) {
    const Key *x = a, *y = b;
    if (x->key < y->key) return -1;
    if (y->key < x->key) return 1;
    return (x->index > y->index) - (x->index < y->index);
}

static int32_t build(int64_t *idx, Key *keys, long n, long axis) {
    if (n == 0) return -1;
    for (long j = 0; j < n; j++) keys[j] = (Key){ pts[idx[j] * dims + axis], idx[j] };
    qsort(keys, n, sizeof(Key), cmp_key);
    for (long j = 0; j < n; j++) idx[j] = keys[j].index;
    long m = n / 2, next = axis + 1 == dims ? 0 : axis + 1;
    int32_t self = (int32_t)num_nodes++;
    nodes[self].point = (int32_t)idx[m];
    nodes[self].split = keys[m].key;
    int32_t l = build(idx, keys, m, next);
    int32_t r = build(idx + m + 1, keys, n - m - 1, next);
    nodes[self].left = l;
    nodes[self].right = r;
    return self;
}

static float sqdist(const float *p, const float *q) {
    float acc = 0.0f;
    for (long k = 0; k < dims; k++) { float t = p[k] - q[k]; acc = acc + t * t; }
    return acc;
}

static void nearest(int32_t node, const float *q, long axis, float *best_d, int64_t *best_i) {
    if (node < 0) return;
    const Node *nd = &nodes[node];
    float dist = sqdist(pts + (long)nd->point * dims, q);
    if (dist < *best_d) { *best_d = dist; *best_i = nd->point; }
    float diff = q[axis] - nd->split;
    long next = axis + 1 == dims ? 0 : axis + 1;
    int32_t first = diff < 0.0f ? nd->left : nd->right, second = diff < 0.0f ? nd->right : nd->left;
    nearest(first, q, next, best_d, best_i);
    if (diff * diff < *best_d) nearest(second, q, next, best_d, best_i);
}

// Same search as nearest, counting the nodes it visits; run outside the timings.
static long visits;
static void nearest_counted(int32_t node, const float *q, long axis, float *best_d, int64_t *best_i) {
    if (node < 0) return;
    visits++;
    const Node *nd = &nodes[node];
    float dist = sqdist(pts + (long)nd->point * dims, q);
    if (dist < *best_d) { *best_d = dist; *best_i = nd->point; }
    float diff = q[axis] - nd->split;
    long next = axis + 1 == dims ? 0 : axis + 1;
    int32_t first = diff < 0.0f ? nd->left : nd->right, second = diff < 0.0f ? nd->right : nd->left;
    nearest_counted(first, q, next, best_d, best_i);
    if (diff * diff < *best_d) nearest_counted(second, q, next, best_d, best_i);
}

static float *read_floats(const char *path, long n) {
    FILE *f = fopen(path, "r");
    if (!f) { perror(path); exit(1); }
    float *x = malloc(n * sizeof(float));
    for (long i = 0; i < n; i++)
        if (fscanf(f, "%f", &x[i]) != 1) { fprintf(stderr, "bad file %s\n", path); exit(1); }
    fclose(f);
    return x;
}

int main(int argc, char **argv) {
    if (argc != 7) { fprintf(stderr, "usage: %s POINTS NUM_POINTS QUERIES NUM_QUERIES DIMS ITERS\n", argv[0]); return 2; }
    long np = atol(argv[2]), nq = atol(argv[4]), iters = atol(argv[6]);
    dims = atol(argv[5]);
    pts = read_floats(argv[1], np * dims);
    const float *qs = read_floats(argv[3], nq * dims);

    double t0 = now();
    nodes = malloc(np * sizeof(Node));
    int64_t *idx = malloc(np * sizeof(int64_t));
    Key *keys = malloc(np * sizeof(Key));
    for (long i = 0; i < np; i++) idx[i] = i;
    num_nodes = 0;
    int32_t root = build(idx, keys, np, 0);
    double build_s = now() - t0;
    free(idx);
    free(keys);
    printf("SELFTIMED: %e\n", build_s);

    int64_t *out = malloc(nq * sizeof(int64_t));
    double *times = malloc(iters * sizeof(double)), total = 0;
    for (long it = 0; it < iters; it++) {
        double s = now();
        for (long j = 0; j < nq; j++) {
            const float *q = qs + j * dims;
            float best_d = sqdist(pts, q);
            int64_t best_i = 0;
            nearest(root, q, 0, &best_d, &best_i);
            out[j] = best_i;
        }
        times[it] = now() - s;
        total += times[it];
        __asm__ volatile("" : : "r"(out) : "memory");
    }
    qsort(times, iters, sizeof(double), cmp_double);
    printf("ITERS: %ld\nSIZE: %ld\nBATCHTIME: %e\nSELFTIMED: %e\n", iters, nq, total, times[iters / 2]);
    for (long j = 0; j < nq; j++) printf("%ld\n", (long)out[j]);
    for (long j = 0; j < nq; j++) {
        const float *q = qs + j * dims;
        float best_d = sqdist(pts, q);
        int64_t best_i = 0;
        nearest_counted(root, q, 0, &best_d, &best_i);
    }
    printf("VISITS: %ld\n", visits);
    return 0;
}
