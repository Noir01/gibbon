from dataclasses import dataclass, fields, is_dataclass
import builtins
import re
import types
import typing
from typing import Union, get_args, get_origin


@dataclass(frozen=True)
class SchemaField:
    name: str
    kind: str
    target: str | None = None


@dataclass(frozen=True)
class Constructor:
    name: str
    fields: tuple[SchemaField, ...]

    def __init__(self, name, fields):
        object.__setattr__(self, 'name', name)
        object.__setattr__(self, 'fields', tuple(fields))


@dataclass(frozen=True)
class Schema:
    name: str
    constructors: tuple[Constructor, ...]

    def __init__(self, name, constructors):
        object.__setattr__(self, 'name', name)
        object.__setattr__(self, 'constructors', tuple(constructors))


def extract_schema(root_union, namespace=None, root_name=None):
    namespace = dict(namespace or {})
    namespace.setdefault('__builtins__', vars(builtins))
    origin = get_origin(root_union)
    alternatives = get_args(root_union) if origin in (Union, types.UnionType) else (root_union,)
    if not alternatives or not all(is_dataclass(t) and isinstance(t, type) for t in alternatives):
        raise TypeError('root must be a union of dataclass alternatives')
    if root_name is None:
        root_name = next((name for name, value in namespace.items() if value is root_union and name[:1].isupper()), None) or getattr(root_union, '__name__', None) or ''.join(t.__name__ for t in alternatives)
    result = []
    for typ in alternatives:
        try:
            hints = typing.get_type_hints(typ, globalns=namespace, localns=namespace)
        except NameError as exc:
            raise TypeError(f'unresolved reference {exc.name!r} on {typ.__name__}') from exc
        fs = []
        for f in fields(typ):
            annotation = hints[f.name]
            if annotation is int:
                fs.append(SchemaField(f.name, 'int'))
            elif annotation is bool:
                raise TypeError(f'unsupported field {typ.__name__}.{f.name}: bool is not int')
            elif annotation is root_union:
                fs.append(SchemaField(f.name, 'recursive', root_name))
            else:
                raise TypeError(f'unsupported field {typ.__name__}.{f.name}: {annotation!r}')
        result.append(Constructor(typ.__name__, fs))
    return Schema(root_name, result)


def generate_source(schema, sum_constructors=None):
    if not re.fullmatch(r'[A-Z][A-Za-z0-9_\']*', schema.name):
        raise ValueError(f'invalid Haskell constructor/root name: {schema.name!r}')
    seen = set()
    for c in schema.constructors:
        if not re.fullmatch(r'[A-Z][A-Za-z0-9_\']*', c.name):
            raise ValueError(f'invalid Haskell constructor name: {c.name!r}')
        if c.name in seen:
            raise ValueError(f'duplicate constructor name: {c.name!r}')
        seen.add(c.name)
    selected = seen if sum_constructors is None else set(sum_constructors)
    unknown = selected - seen
    if unknown:
        raise ValueError(f'unknown sum constructors: {sorted(unknown)}')
    declarations = 'data ' + schema.name + ' = ' + ' | '.join(
        c.name + ((' ' + ' '.join('Int' if f.kind == 'int' else schema.name for f in c.fields)) if c.fields else '')
        for c in schema.constructors)
    sums, adds = [], []
    for c in schema.constructors:
        names = [f'f{i}' for i in range(len(c.fields))]
        pattern = c.name + ((' ' + ' '.join(names)) if names else '')
        scalar_terms = [n for n, f in zip(names, c.fields)
                        if f.kind == 'int' and c.name in selected]
        child_terms = [f'sum_ints {n}' for n, f in zip(names, c.fields)
                       if f.kind == 'recursive']
        sums.append(f'  {pattern} -> ' + (' + '.join(scalar_terms + child_terms) or '0'))
        values = [f'({n} + amount)' if f.kind == 'int' else f'(add_ints {n} amount)' for n, f in zip(names, c.fields)]
        adds.append(f'  {pattern} -> {c.name}' + ((' ' + ' '.join(values)) if values else ''))
    return declarations + '\n\nsum_ints :: ' + schema.name + ' -> Int\nsum_ints x = case x of\n' + '\n'.join(sums) + '\n\nadd_ints :: ' + schema.name + ' -> Int -> ' + schema.name + '\nadd_ints x amount = case x of\n' + '\n'.join(adds) + '\n'


__all__ = ['SchemaField', 'Constructor', 'Schema', 'extract_schema', 'generate_source']
