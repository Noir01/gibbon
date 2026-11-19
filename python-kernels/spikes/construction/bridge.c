#define main construction_generated_main
#include "module.c"
#undef main

ssize_t kernel_build(uint8_t *output, size_t capacity, int64_t depth) {
    if (!output || depth < 0 || depth > 12) return -1;
    size_t need = 9;
    for (int64_t i = 0; i < depth; ++i) {
        if (need > (SIZE_MAX - (size_t)9) / 2) return -1;
        need = 2 * need + 9;
    }
    if (capacity < need) return -1;
    GibCursor start = (GibCursor)output;
    GibCursorGibCursorGibCursorProd result = mk_tree(start + capacity, start, depth);
    return result.field2 - start;
}

int64_t kernel_sum(const uint8_t *data, size_t length) {
    if (!data || !length) return INT64_MIN;
    GibCursor start = (GibCursor)data;
    return sum_leaves(start + length, start).field2;
}
