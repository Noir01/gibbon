data Tree = Leaf Int | Node Int Tree Tree

mk_tree :: Int -> Tree
mk_tree depth = if depth <= 0 then Leaf 1 else Node depth (mk_tree (depth - 1)) (mk_tree (depth - 1))

sum_leaves :: Tree -> Int
sum_leaves tree = case tree of
  Leaf value -> value
  Node _ left right -> sum_leaves left + sum_leaves right

gibbon_main = sum_leaves (mk_tree sizeParam)
