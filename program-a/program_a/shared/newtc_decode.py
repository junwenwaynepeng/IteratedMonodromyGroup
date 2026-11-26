"""Free cancellation during NEWTC proof expansion; independent checkers unchanged."""

from .exact import Limit, require


def reduced_expand(w, images, cap, tick=lambda: None):
    out = []
    steps = 0
    for g in w:
        require(
            type(g) is int and 0 < abs(g) <= len(images), "NEWTC_EXPANSION_ALPHABET"
        )
        b = images[abs(g) - 1]
        for a in b if g > 0 else (-x for x in reversed(b)):
            steps += 1
            if steps % 1024 == 0:
                tick()
            if out and out[-1] == -a:
                out.pop()
            else:
                out.append(a)
            if len(out) > cap:
                raise Limit("expanded_word_length")
    return tuple(out)


def checked_expression(w, rank, encoded_cap, tick):
    require(type(w) is list, "NEWTC_EXPRESSION_SHAPE")
    for i, g in enumerate(w):
        if i % 1024 == 0:
            tick()
        require(type(g) is int and 0 < abs(g) <= rank, "NEWTC_EXPRESSION_ALPHABET")
    if len(w) > encoded_cap:
        raise Limit("NEWTC_encoded_expression_letters")
    return w
