"""Evaluate (3 + 4) * 2 + 5 using a mutable vector as a stack.

Tokens: nonnegative integers push operands; -1 adds and -2 multiplies.
The fixture assumes a well-formed expression; it is not an input validator.
"""


def main() -> int:
    tokens = [3, 4, -1, 2, -2, 5, -1]
    stack = [0] * len(tokens)
    top = 0
    for i in range(len(tokens)):
        token = tokens[i]
        if token >= 0:
            stack[top] = token
            top += 1
        else:
            if token == -1:
                stack[top - 2] = stack[top - 2] + stack[top - 1]
            else:
                stack[top - 2] = stack[top - 2] * stack[top - 1]
            top -= 1
    return stack[0]
