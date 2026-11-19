"""Irregular recursive ADT; no handwritten Gibbon datatype or traversal."""
from dataclasses import dataclass, fields
from api import compile_type


@dataclass
class Pair:
    first: int
    second: int


@dataclass
class Wrapper:
    weight: int
    child: "Weird"


@dataclass
class Fork:
    bias: int
    bonus: int
    left: "Weird"
    middle: "Weird"
    right: "Weird"


Weird = Pair | Wrapper | Fork


def python_sum(value, selected=None):
    total = 0
    for field in fields(value):
        item = getattr(value, field.name)
        if type(item) is int:
            if selected is None or type(value).__name__ in selected:
                total += item
        else:
            total += python_sum(item, selected)
    return total


def python_add(value, amount):
    return type(value)(*(
        getattr(value, field.name) + amount
        if type(getattr(value, field.name)) is int
        else python_add(getattr(value, field.name), amount)
        for field in fields(value)
    ))


def run_demo():
    value = Fork(
        bias=7,
        bonus=11,
        left=Wrapper(weight=100, child=Pair(3, -2)),
        middle=Pair(5, 6),
        right=Wrapper(weight=-50, child=Fork(
            bias=-10, bonus=20,
            left=Pair(1, 2), middle=Pair(4, 8), right=Pair(-3, 9),
        )),
    )
    ops = compile_type(Weird, globals(), name='Weird')
    packed = ops.pack(value)
    assert ops.unpack(packed) == value
    total = ops.sum_ints(packed)
    assert total == python_sum(value)
    updated = ops.add_ints(packed, 4)
    expected = python_add(value, 4)
    assert ops.unpack(updated) == expected
    assert ops.sum_ints(updated) == python_sum(expected)
    assert ops.unpack(packed) == value

    leaf_ops = compile_type(Weird, globals(), name='Weird', sum_constructors=('Pair',))
    leaf_packed = leaf_ops.pack(value)
    leaf_total = leaf_ops.sum_ints(leaf_packed)
    assert leaf_total == python_sum(value, {'Pair'})
    # Reuse each compiled datatype with different shapes/constructor roots.
    for fixture in (Pair(2, -7), Wrapper(weight=9, child=Pair(3, 4)), value):
        buf = ops.pack(fixture)
        assert ops.sum_ints(buf) == python_sum(fixture)
        assert ops.unpack(ops.add_ints(buf, -2)) == python_add(fixture, -2)
        assert leaf_ops.sum_ints(leaf_ops.pack(fixture)) == python_sum(fixture, {'Pair'})

    print('All integer fields:', total)
    print('Pair fields only:', leaf_total)
    print('After adding 4 to every integer:', ops.sum_ints(updated))
    print('Round-trip and Python reference checks: passed')
    print('Generated Gibbon source:', ops.build_directory / 'module.hs')


if __name__ == '__main__':
    run_demo()
