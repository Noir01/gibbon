data Expr = Lit Int | Add Expr Expr

sum_ints :: Expr -> Int
sum_ints x = case x of
  Lit n -> n
  Add a b -> sum_ints a + sum_ints b

add_ints :: Expr -> Int -> Expr
add_ints x amount = case x of
  Lit n -> Lit (n + amount)
  Add a b -> Add (add_ints a amount) (add_ints b amount)

mk_expr :: Int -> Expr
mk_expr depth =
  if depth <= 0
  then Lit 1
  else Add (mk_expr (depth - 1)) (Lit depth)

gibbon_main = sum_ints (add_ints (mk_expr sizeParam) 1)
