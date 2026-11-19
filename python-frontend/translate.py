"""A deliberately small, statically typed Python-source to Gibbon frontend."""
import ast
import math


class FrontendError(Exception):
    """Unsupported or ill-typed source, with a source location."""


class Frontend:
    def __init__(self, filename):
        self.filename = filename
        self.functions = {}
        self.used = set()
        self.constructors = {}
        self.root = None
        self.helpers = []
        self.vector_helpers = {}
        self.borrowed = set()

    def local(self, name):
        candidate = 'p_' + name
        while candidate in self.used or candidate in {'p_' + n for n in self.functions}:
            candidate += '_'
        self.used.add(candidate)
        return candidate

    def upper_name(self, node, name):
        if not name.isascii() or not name[0].isupper() or not name.replace('_', '').isalnum() or name in ('Int', 'Bool', 'Float', 'Vector', 'True', 'False'):
            self.fail(node, 'invalid or reserved uppercase constructor/type name')

    def annotation(self, node):
        if isinstance(node, ast.Name) and node.id in ('int', 'bool', 'float'):
            return {'int': 'Int', 'bool': 'Bool', 'float': 'Float'}[node.id]
        if self.root and ((isinstance(node, ast.Name) and node.id == self.root) or (isinstance(node, ast.Constant) and node.value == self.root)):
            return self.root
        self.fail(node, 'unsupported type annotation')

    def parameter_annotation(self, node):
        # Vectors are permitted only as borrowed parameters, never ADT fields
        # or results. Keep annotation() scalar/packed-only.
        if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
                and node.value.id == 'list' and isinstance(node.slice, ast.Name)
                and node.slice.id in ('int', 'float')):
            return 'Vector ' + self.annotation(node.slice)
        return self.annotation(node)

    def writable(self, node, name):
        if name in self.borrowed:
            self.fail(node, 'borrowed vector parameters are read-only (no writes or rebinding)')

    def fail(self, node, message):
        raise FrontendError(f'{self.filename}:{getattr(node, "lineno", 1)}:{getattr(node, "col_offset", 0) + 1}: {message}')

    def ensure_vectors(self, element_type):
        """Monomorphic runtime primitives for each fixed-size list element type."""
        if element_type not in self.vector_helpers:
            repeat, fill, checked = (self.local(n) for n in ('repeat', 'fill', 'checked_index'))
            self.vector_helpers[element_type] = repeat, checked
            self.helpers.extend([
                f'{repeat} :: {element_type} -> Int -> Vector {element_type}',
                f'{repeat} seed count = (if count <= 0 then (let {{ empty :: Vector {element_type}; empty = valloc 0 }} in empty) else (let {{ vec :: Vector {element_type}; vec = valloc count }} in {fill} 0 count seed vec))',
                f'{fill} :: Int -> Int -> {element_type} -> Vector {element_type} -> Vector {element_type}',
                f'{fill} index count seed vec = (if index < count then (let updated = inplacevupdate vec index seed in {fill} (index + 1) count seed updated) else vec)',
                f'{checked} :: Vector {element_type} -> Int -> Int',
                f'{checked} vec raw = (let size = vlength vec in (let index = (if raw < 0 then raw + size else raw) in (if index < 0 then error "list index out of bounds" else (if index >= size then error "list index out of bounds" else index))))',
            ])
        return self.vector_helpers[element_type]

    def vector_read(self, node, env):
        if not isinstance(node.value, ast.Name):
            self.fail(node, 'indexing requires a local vector name')
        vector, typ = self.expr(node.value, env)
        index, itype = self.expr(node.slice, env)
        if typ not in ('Vector Int', 'Vector Float') or itype != 'Int':
            self.fail(node, 'vector and integer index required')
        element_type = typ.split()[1]
        _, checked = self.ensure_vectors(element_type)
        return f'(vnth {vector} ({checked} {vector} ({index})))', element_type

    def vector_write(self, node, env, finish):
        target = node.targets[0]
        if not isinstance(target.value, ast.Name) or target.value.id not in env:
            self.fail(target, 'vector update requires a local vector name')
        self.writable(target, target.value.id)
        vector, typ = env[target.value.id]
        # Python assignment evaluates the RHS before its subscript target.
        value, vtype = self.expr(node.value, env)
        index, itype = self.expr(target.slice, env)
        if typ not in ('Vector Int', 'Vector Float') or typ != 'Vector ' + vtype or itype != 'Int':
            self.fail(node, 'vector update requires matching element type and integer index')
        _, checked = self.ensure_vectors(vtype)
        val_binding, idx_binding, updated = (self.local(n) for n in ('element', 'offset', target.value.id))
        body = finish(dict(env, **{target.value.id: (updated, typ)}))
        return (f'(let {val_binding} = {value} in (let {idx_binding} = {checked} {vector} ({index}) '
                f'in (let {updated} = inplacevupdate {vector} {idx_binding} {val_binding} in {body})))')

    def list_literal(self, node, env):
        elements = []
        element_type = None
        for element in node.elts:
            text, typ = self.expr(element, env)
            if typ not in ('Int', 'Float') or (element_type is not None and typ != element_type):
                self.fail(element, 'list literal elements must have one matching int or float type')
            element_type = typ
            elements.append((self.local('literal_element'), text))
        vector_type = 'Vector ' + (element_type or 'Int')
        vector = self.local('literal_vector')
        writes, current = [], vector
        for index, (value, _) in enumerate(elements):
            updated = self.local('literal_vector')
            writes.append((updated, f'inplacevupdate {current} {index} {value}'))
            current = updated
        body = current
        for binding, text in reversed(writes):
            body = f'(let {binding} = {text} in {body})'
        body = f'(let {{ {vector} :: {vector_type}; {vector} = valloc {len(elements)} }} in {body})'
        # Evaluate all element expressions left-to-right before filling the vector.
        for binding, text in reversed(elements):
            body = f'(let {binding} = {text} in {body})'
        return body, vector_type

    def expr(self, node, env):
        if isinstance(node, ast.List):
            return self.list_literal(node, env)
        if isinstance(node, ast.Subscript):
            return self.vector_read(node, env)
        if (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult)
                and isinstance(node.left, ast.List) and len(node.left.elts) == 1):
            seed, stype = self.expr(node.left.elts[0], env)
            count, ctype = self.expr(node.right, env)
            if stype not in ('Int', 'Float') or ctype != 'Int':
                self.fail(node, 'list repetition requires int or float seed and integer count')
            repeat, _ = self.ensure_vectors(stype)
            return f'({repeat} ({seed}) ({count}))', 'Vector ' + stype
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == 'len' and not node.keywords and len(node.args) == 1
                and 'len' not in env and 'len' not in self.functions):
            value, typ = self.expr(node.args[0], env)
            if typ not in ('Vector Int', 'Vector Float'):
                self.fail(node, 'len requires a vector')
            return f'(vlength ({value}))', 'Int'
        if isinstance(node, ast.Constant) and type(node.value) is float:
            # Gibbon's Float is IEEE binary32: operations and literals round to
            # that precision, including subnormal underflow (not Python float64).
            if not math.isfinite(node.value) or abs(node.value) > 3.4028234663852886e38:
                self.fail(node, 'float literal outside finite float32 range')
            return repr(node.value), 'Float'
        if isinstance(node, ast.Constant) and type(node.value) in (int, bool):
            if type(node.value) is int and not -(2**63) <= node.value < 2**63:
                self.fail(node, 'integer literal outside signed 64-bit range')
            return str(node.value), 'Bool' if type(node.value) is bool else 'Int'
        if (isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub)
                and isinstance(node.operand, ast.Constant)
                and type(node.operand.value) is int and node.operand.value == 2**63):
            return '((0 - 9223372036854775807) - 1)', 'Int'
        if isinstance(node, ast.Name) and node.id in env:
            return env[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            value, typ = self.expr(node.operand, env)
            if typ not in ('Int', 'Float'):
                self.fail(node, 'unary minus requires int or float')
            # Exact -1 multiplication also flips signed zero, unlike 0.0 - x.
            return (f'((0.0 .-. 1.0) .*. {value})' if typ == 'Float' else f'(0 - {value})'), typ
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            left, lt = self.expr(node.left, env)
            right, rt = self.expr(node.comparators[0], env)
            ops = {ast.Eq: '==', ast.NotEq: '/=', ast.Lt: '<', ast.LtE: '<=', ast.Gt: '>', ast.GtE: '>='}
            op = ops.get(type(node.ops[0]))
            if op is None or lt != rt or lt not in ('Int', 'Bool', 'Float') or (lt == 'Bool' and type(node.ops[0]) not in (ast.Eq, ast.NotEq)):
                self.fail(node, 'unsupported comparison types')
            if lt == 'Float':
                if isinstance(node.ops[0], ast.NotEq):
                    return f'(if ({left} .==. {right}) then False else True)', 'Bool'
                op = '.' + op + '.'
            return f'({left} {op} {right})', 'Bool'
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
            name = node.func.id
            if name in env:
                self.fail(node, 'shadowed call')
            if name in self.constructors:
                params, result, callee = self.constructors[name], self.root, name
            elif name in self.functions:
                params, result = self.functions[name]
                callee = 'p_' + name
            else:
                self.fail(node, 'unknown call')
            args = [self.expr(arg, env) for arg in node.args]
            if [typ for _, typ in args] != params:
                self.fail(node, 'call argument type/arity mismatch')
            return ('(' + callee + ''.join(' (' + text + ')' for text, _ in args) + ')'), result
        if isinstance(node, ast.BinOp) and type(node.op) in (ast.Add, ast.Sub, ast.Mult):
            a, ta = self.expr(node.left, env)
            b, tb = self.expr(node.right, env)
            if ta != tb or ta not in ('Int', 'Float'):
                self.fail(node, 'arithmetic requires matching int or float types')
            op = {ast.Add: '+', ast.Sub: '-', ast.Mult: '*'}[type(node.op)]
            if ta == 'Float':
                op = '.' + op + '.'
            return f'({a} {op} {b})', ta
        self.fail(node, 'unsupported expression or unknown name')

    def assignment_form(self, node):
        if (isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name)
                and type(node.op) in (ast.Add, ast.Sub, ast.Mult)):
            read = ast.copy_location(ast.Name(id=node.target.id, ctx=ast.Load()), node.target)
            value = ast.copy_location(ast.BinOp(left=read, op=node.op, right=node.value), node)
            return ast.copy_location(ast.Assign(targets=[node.target], value=value), node)
        return node

    def loop_body(self, statements, env, finish):
        """Emit an iteration in continuation-passing style, without object mutation."""
        if not statements:
            return finish(env)
        node, *rest = statements
        node = self.assignment_form(node)
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Subscript)):
            return self.vector_write(node, env, lambda updated: self.loop_body(rest, updated, finish))
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            text, typ = self.expr(node.value, env)
            self.writable(node, name)
            if typ in ('Vector Int', 'Vector Float') and isinstance(node.value, ast.Name):
                self.fail(node, 'vector aliases are not supported')
            if name in env and env[name][1] != typ:
                self.fail(node, 'loop-carried variables must keep their type')
            binding = self.local(name)
            updated = dict(env, **{name: (binding, typ)})
            return f'(let {binding} = {text} in {self.loop_body(rest, updated, finish)})'
        if isinstance(node, ast.If):
            cond, typ = self.expr(node.test, env)
            if typ != 'Bool':
                self.fail(node.test, 'if requires bool')
            yes = self.loop_body(node.body + rest, env.copy(), finish)
            no = self.loop_body(node.orelse + rest, env.copy(), finish)
            return f'(if {cond} then {yes} else {no})'
        self.fail(node, 'loop body supports assignments and conditionals only')

    def for_loop(self, node, rest, env, result):
        """Lower range loops to a top-level recursive helper carrying live bindings."""
        call = node.iter
        if (node.orelse or not isinstance(node.target, ast.Name)
                or not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name)
                or call.func.id != 'range' or call.keywords or not 1 <= len(call.args) <= 3
                or 'range' in env or 'range' in self.functions):
            self.fail(node, 'only unshadowed range loops without else are supported')
        target = node.target.id
        if target in env:
            self.fail(node.target, 'loop target must be fresh')
        if any(isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id == target
               for statement in rest for n in ast.walk(statement)):
            self.fail(node.target, 'loop target cannot be used after loop')
        if any(isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store) and n.id == target
               for statement in node.body for n in ast.walk(statement)):
            self.fail(node.target, 'assigning the loop target is unsupported')
        arguments = [self.expr(arg, env) for arg in call.args[:2]]
        if any(typ != 'Int' for _, typ in arguments):
            self.fail(call, 'range bounds require int')
        start, stop = ('0', arguments[0][0]) if len(arguments) == 1 else (arguments[0][0], arguments[1][0])
        step = 1
        if len(call.args) == 3:
            step_node = call.args[2]
            if isinstance(step_node, ast.Constant) and type(step_node.value) is int:
                step = step_node.value
            elif (isinstance(step_node, ast.UnaryOp) and isinstance(step_node.op, ast.USub)
                  and isinstance(step_node.operand, ast.Constant) and type(step_node.operand.value) is int):
                step = -step_node.operand.value
            else:
                self.fail(step_node, 'range step must be a nonzero literal')
            if step == 0 or not -(2**63) < step < 2**63:
                self.fail(step_node, 'range step must be a nonzero in-range literal')
        helper = self.local('loop')
        index, bound = self.local('index'), self.local('bound')
        states = {name: (self.local(name), typ) for name, (_, typ) in env.items()}
        iteration = dict(states, **{target: (index, 'Int')})
        increment = f'({index} + {step})' if step > 0 else f'({index} - {-step})'

        def recur(updated):
            for name, (_, typ) in states.items():
                if updated[name][1] != typ:
                    self.fail(node, 'loop-carried type mismatch')
            values = [increment, bound] + [updated[name][0] for name in states]
            return '(' + helper + ''.join(f' ({value})' for value in values) + ')'

        body = self.loop_body(node.body, iteration, recur)
        # Continuation uses the latest state, not the original bindings.
        done = self.block(rest, states, result)
        params = [index, bound] + [binding for binding, _ in states.values()]
        signature = ' -> '.join(['Int', 'Int'] + [typ for _, typ in states.values()] + [result])
        condition = '<' if step > 0 else '>'
        self.helpers.extend([
            f'{helper} :: {signature}',
            f'{helper} ' + ' '.join(params) + f' = (if ({index} {condition} {bound}) then {body} else {done})',
        ])
        values = [start, stop] + [binding for binding, _ in env.values()]
        return '(' + helper + ''.join(f' ({value})' for value in values) + ')'

    def block(self, statements, env, result):
        if not statements:
            self.fail(ast.Module(), 'block must return')
        node, *rest = statements
        node = self.assignment_form(node)
        if isinstance(node, ast.For):
            return self.for_loop(node, rest, env, result)
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Subscript)):
            return self.vector_write(node, env, lambda updated: self.block(rest, updated, result))
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            value, typ = self.expr(node.value, env)
            self.writable(node, name)
            if typ in ('Vector Int', 'Vector Float') and isinstance(node.value, ast.Name):
                self.fail(node, 'vector aliases are not supported')
            binding = self.local(name)
            body = self.block(rest, dict(env, **{name: (binding, typ)}), result)
            return f'(let {binding} = {value} in {body})'
        if isinstance(node, ast.If):
            if rest:
                self.fail(rest[0], 'unreachable statement after terminal if')
            cond, typ = self.expr(node.test, env)
            if typ != 'Bool':
                self.fail(node.test, 'if requires bool')
            yes = self.block(node.body, env.copy(), result)
            no = self.block(node.orelse, env.copy(), result)
            return f'(if {cond} then {yes} else {no})'
        if isinstance(node, ast.Match):
            if rest:
                self.fail(rest[0], 'unreachable statement after terminal match')
            subject, typ = self.expr(node.subject, env)
            if not self.root or typ != self.root:
                self.fail(node, 'match requires ADT')
            seen, arms = set(), []
            for case in node.cases:
                pat = case.pattern
                if case.guard is not None:
                    self.fail(pat, 'match guards unsupported')
                if not isinstance(pat, ast.MatchClass) or not isinstance(pat.cls, ast.Name) or pat.kwd_attrs or pat.kwd_patterns:
                    self.fail(pat, 'only positional constructor patterns supported')
                name = pat.cls.id
                if name not in self.constructors or name in seen:
                    self.fail(pat, 'unknown or duplicate constructor pattern')
                fields = self.constructors[name]
                if len(fields) != len(pat.patterns):
                    self.fail(pat, 'constructor pattern arity mismatch')
                seen.add(name)
                arm_env, bindings, names = env.copy(), [], set()
                for sub, field_type in zip(pat.patterns, fields):
                    if not isinstance(sub, ast.MatchAs) or sub.pattern is not None:
                        self.fail(sub, 'only name/wildcard fields supported')
                    if sub.name is None:
                        bindings.append('_')
                    else:
                        self.writable(sub, sub.name)
                        if sub.name in names:
                            self.fail(sub, 'duplicate pattern binding')
                        names.add(sub.name)
                        binding = self.local(sub.name)
                        bindings.append(binding)
                        arm_env[sub.name] = binding, field_type
                body = self.block(case.body, arm_env, result)
                arms.append(name + ''.join(' ' + b for b in bindings) + ' -> ' + body)
            if seen != set(self.constructors):
                self.fail(node, 'nonexhaustive match')
            return '(case ' + subject + ' of { ' + '; '.join(arms) + ' })'
        if isinstance(node, ast.Return) and node.value is not None:
            value, typ = self.expr(node.value, env)
            if typ != result:
                self.fail(node, 'return type mismatch')
            if rest:
                self.fail(rest[0], 'unreachable statement')
            return value
        self.fail(node, 'unsupported statement')

    def run(self, source):
        try:
            tree = ast.parse(source, self.filename, type_comments=True)
        except SyntaxError as error:
            raise FrontendError(f'{self.filename}:{error.lineno or 1}:{error.offset or 1}: {error.msg}') from None
        if tree.type_ignores:
            self.fail(tree.type_ignores[0], 'type ignores unsupported')
        for node in ast.walk(tree):
            if getattr(node, 'type_comment', None):
                self.fail(node, 'type comments unsupported')
            name = node.id if isinstance(node, ast.Name) else node.arg if isinstance(node, ast.arg) else node.name if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.MatchAs)) else None
            if name is not None and not name.isascii():
                self.fail(node, 'only ASCII identifiers supported')
        classes, functions, aliases = [], [], []
        if ast.get_docstring(tree) is not None:
            tree.body = tree.body[1:]
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.module == 'dataclasses' and node.level == 0 and len(node.names) == 1 and node.names[0].name == 'dataclass' and node.names[0].asname is None:
                continue
            if isinstance(node, ast.ClassDef):
                classes.append(node)
            elif isinstance(node, ast.FunctionDef):
                functions.append(node)
            elif isinstance(node, ast.Assign):
                aliases.append(node)
            else:
                self.fail(node, 'unsupported top-level statement')
        if classes or aliases:
            if len(aliases) != 1 or not classes:
                self.fail(tree, 'expected exactly one ADT alias for dataclasses')
            alias = aliases[0]
            if len(alias.targets) != 1 or not isinstance(alias.targets[0], ast.Name):
                self.fail(alias, 'expected ADT alias name')
            self.root = alias.targets[0].id
            self.upper_name(alias.targets[0], self.root)
            def members(node):
                if isinstance(node, ast.Name):
                    return [node.id]
                if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
                    return members(node.left) + members(node.right)
                self.fail(node, 'expected constructor union')
            variants = members(alias.value)
            class_names = [cls.name for cls in classes]
            if len(variants) < 2 or len(set(variants)) != len(variants) or set(variants) != set(class_names) or len(set(class_names)) != len(class_names) or self.root in class_names:
                self.fail(alias, 'ADT alias must list each constructor exactly once')
            for cls in classes:
                self.upper_name(cls, cls.name)
                if cls.bases or cls.keywords or getattr(cls, 'type_params', []) or len(cls.decorator_list) != 1 or not isinstance(cls.decorator_list[0], ast.Name) or cls.decorator_list[0].id != 'dataclass':
                    self.fail(cls, 'only plain @dataclass constructors supported')
                fields, field_names, recursive = [], set(), False
                for field in cls.body:
                    if isinstance(field, ast.Pass) and len(cls.body) == 1:
                        continue
                    if not isinstance(field, ast.AnnAssign) or not isinstance(field.target, ast.Name) or field.value is not None or not field.simple or field.target.id in field_names:
                        self.fail(field, 'expected unique annotated dataclass field without default')
                    field_names.add(field.target.id)
                    typ = self.annotation(field.annotation)
                    if recursive and typ != self.root:
                        self.fail(field, 'scalar field after recursive field')
                    recursive = recursive or typ == self.root
                    fields.append(typ)
                self.constructors[cls.name] = fields
            self.constructors = {name: self.constructors[name] for name in variants}
        for fn in functions:
            args = fn.args
            if fn.name in self.functions or fn.name in self.constructors or fn.name == self.root:
                self.fail(fn, 'duplicate declaration')
            if fn.decorator_list or getattr(fn, 'type_params', []) or fn.type_comment or args.posonlyargs or args.kwonlyargs or args.vararg or args.kwarg or args.defaults or args.kw_defaults:
                self.fail(fn, 'only plain annotated positional functions without defaults supported')
            if len({a.arg for a in args.args}) != len(args.args):
                self.fail(fn, 'duplicate parameter')
            if any(a.type_comment for a in args.args):
                self.fail(fn, 'parameter type comments unsupported')
            self.functions[fn.name] = ([self.parameter_annotation(a.annotation) for a in args.args], self.annotation(fn.returns))
        if 'main' not in self.functions or self.functions['main'][0] or self.functions['main'][1] not in ('Int', 'Bool', 'Float'):
            self.fail(tree, 'expected scalar main()')
        lines = []
        if self.root:
            lines.append('data ' + self.root + ' = ' + ' | '.join(name + ''.join(' ' + t for t in fields) for name, fields in self.constructors.items()))
        for fn in functions:
            params, typ = self.functions[fn.name]
            self.borrowed = {a.arg for a, t in zip(fn.args.args, params) if t in ('Vector Int', 'Vector Float')}
            body = fn.body[1:] if ast.get_docstring(fn) is not None else fn.body
            env = {a.arg: (self.local(a.arg), t) for a, t in zip(fn.args.args, params)}
            arguments = ''.join(' ' + env[a.arg][0] for a in fn.args.args)
            lines.extend([f'p_{fn.name} :: ' + ' -> '.join(params + [typ]), f'p_{fn.name}{arguments} = {self.block(body, env, typ)}'])
        return '\n'.join(lines + self.helpers + ['gibbon_main = p_main', ''])


def translate(source: str, filename='<input>') -> str:
    return Frontend(filename).run(source)


def main():
    import argparse
    import pathlib
    import sys

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=pathlib.Path)
    parser.add_argument('-o', '--output', required=True, type=pathlib.Path)
    args = parser.parse_args()
    try:
        output = translate(args.input.read_text(encoding='utf-8'), str(args.input))
        args.output.write_text(output, encoding='utf-8')
    except (FrontendError, OSError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
