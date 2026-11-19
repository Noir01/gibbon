// nanoflann (https://github.com/jlblancoc/nanoflann) k-d tree over the same
// float32 points, exact 1-NN with knnSearch, dimension chosen at run time.
// Same input files and output format as baseline.c.
//
// usage: nanoflann_bench POINTS NUM_POINTS QUERIES NUM_QUERIES DIMS ITERS LEAF_SIZE
#include <nanoflann.hpp>
#include "common.h"

struct Cloud {
    const float *p;
    size_t n, d;
    size_t kdtree_get_point_count() const { return n; }
    float kdtree_get_pt(size_t i, size_t k) const { return p[i * d + k]; }
    template <class BBox> bool kdtree_get_bbox(BBox &) const { return false; }
};

using Tree = nanoflann::KDTreeSingleIndexAdaptor<nanoflann::L2_Simple_Adaptor<float, Cloud>, Cloud, -1, uint32_t>;

int main(int argc, char **argv) {
    if (argc != 8) { fprintf(stderr, "usage: %s POINTS NUM_POINTS QUERIES NUM_QUERIES DIMS ITERS LEAF_SIZE\n", argv[0]); return 2; }
    long np = atol(argv[2]), nq = atol(argv[4]), dims = atol(argv[5]), iters = atol(argv[6]), leaf = atol(argv[7]);
    const float *pts = read_floats(argv[1], np * dims);
    const float *qs = read_floats(argv[3], nq * dims);
    Cloud cloud{pts, (size_t)np, (size_t)dims};

    double t0 = now();
    Tree tree((int)dims, cloud, nanoflann::KDTreeSingleIndexAdaptorParams((size_t)leaf));
    printf("SELFTIMED: %e\n", now() - t0);

    int64_t *out = (int64_t *)malloc(nq * sizeof(int64_t));
    double *times = (double *)malloc(iters * sizeof(double));
    for (long it = 0; it < iters; it++) {
        double s = now();
        for (long j = 0; j < nq; j++) {
            uint32_t idx;
            float dist;
            tree.knnSearch(qs + j * dims, 1, &idx, &dist);
            out[j] = idx;
        }
        times[it] = now() - s;
        __asm__ volatile("" : : "r"(out) : "memory");
    }
    print_results(times, iters, nq, out);
    return 0;
}
