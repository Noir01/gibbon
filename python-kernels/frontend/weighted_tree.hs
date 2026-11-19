data WeightedTree = Tip Int | Fork Int WeightedTree WeightedTree

sum_ints :: WeightedTree -> Int
sum_ints x = case x of
  Tip f0 -> f0
  Fork f0 f1 f2 -> f0 + sum_ints f1 + sum_ints f2

add_ints :: WeightedTree -> Int -> WeightedTree
add_ints x amount = case x of
  Tip f0 -> Tip (f0 + amount)
  Fork f0 f1 f2 -> Fork (f0 + amount) (add_ints f1 amount) (add_ints f2 amount)

gibbon_main = sum_ints (Fork 10 (Tip 2) (Tip 3))
