from frontend import extract_schema, generate_source
from test_frontend import Expr, WeightedTree

examples = (
    (Expr, 'expr.hs', 'gibbon_main = sum_ints (Add (Lit 2) (Lit 3))'),
    (WeightedTree, 'weighted_tree.hs', 'gibbon_main = sum_ints (Fork 10 (Tip 2) (Tip 3))'),
)

for alias, filename, main in examples:
    schema = extract_schema(alias, namespace=globals())
    with open(filename, 'w', encoding='utf-8') as output:
        output.write(generate_source(schema))
        output.write('\n' + main + '\n')
