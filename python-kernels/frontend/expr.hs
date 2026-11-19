data Expr = Lit Int | Add Expr Expr

sum_ints :: Expr -> Int
sum_ints x = case x of
  Lit f0 -> f0
  Add f0 f1 -> 0 + sum_ints f0 + sum_ints f1

add_ints :: Expr -> Int -> Expr
add_ints x amount = case x of
  Lit f0 -> Lit (f0 + amount)
  Add f0 f1 -> Add (add_ints f0 amount) (add_ints f1 amount)

gibbon_main = sum_ints (Add (Lit 2) (Lit 3))
