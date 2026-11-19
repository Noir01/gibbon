from construction import ConstructionOps

ops = ConstructionOps()
for depth in (0, 1, 10):
    packed = ops.build_tree(depth)
    print(f'depth={depth} bytes={len(packed)} native_leaf_sum={ops.sum_leaves(packed)}')
