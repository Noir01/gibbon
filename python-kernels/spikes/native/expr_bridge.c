/* Private feasibility bridge: callers supply valid, flat Expr buffers.
 * Not an untrusted-buffer API. The generated scalar traversal does not allocate
 * or access runtime state on this representation, so it needs no RTS startup.
 * Retained transformed values will require a separate ownership/init contract.
 */
#define main expr_generated_main
#include "expr_sum_add.c"
#undef main

int64_t expr_sum(const uint8_t *data, size_t length)
{
    GibCursor root = (GibCursor) data;
    GibCursorGibCursorGibIntProd result = sum_ints(root + length, root);
    return result.field2;
}

/* Shape-preserving --biginf writer: ordinary cases write exactly input length,
 * with no allocation/barrier/growth calls. Output must not overlap input.
 * As with expr_sum, the byte sequence must already be validated by the caller.
 */
ssize_t expr_add(const uint8_t *data, size_t length, int64_t amount,
                 uint8_t *output, size_t capacity)
{
    if (!data || !output || length == 0 || capacity < length) return -1;
    GibCursor root = (GibCursor) data;
    GibCursor dest = (GibCursor) output;
    GibCursorGibCursorGibCursorGibCursorGibCursorProd result =
        add_ints(root + length, dest + capacity, dest, root, amount);
    return result.field4 - dest;
}
