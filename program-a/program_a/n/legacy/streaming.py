"""Length/lex streaming of reduced words, with direct ordinal skipping."""


def words(rank, depth, count, start=0, invol=False):
    assert rank > 0 and depth >= 0 and count >= 0 and start >= 0
    letters = (
        tuple(range(1, rank + 1))
        if invol
        else tuple(range(1, rank + 1)) + tuple(range(-rank, 0))
    )
    branch = len(letters) - 1
    ordinal = 0
    produced = 0
    if start == 0 and count:
        yield 0, ()
        produced = 1
    ordinal = 1

    def walk(prefix, left, skip):
        if not left:
            if skip == 0:
                yield tuple(prefix)
            return
        for g in letters:
            if prefix and (prefix[-1] == g if invol else prefix[-1] == -g):
                continue
            block = branch ** (left - 1)
            if skip >= block:
                skip -= block
                continue
            prefix.append(g)
            yield from walk(prefix, left - 1, skip)
            prefix.pop()
            skip = 0

    for length in range(1, depth + 1):
        size = len(letters) * branch ** (length - 1)
        if ordinal + size <= start:
            ordinal += size
            continue
        offset = max(0, start - ordinal)
        index = ordinal + offset
        for w in walk([], length, offset):
            if produced >= count:
                return
            yield index, w
            produced += 1
            index += 1
        ordinal += size
