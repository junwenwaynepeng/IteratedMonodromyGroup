"""Exact first-level permutations for search signatures; no sections computed.
Whole-tree identity/certificate verification stays in the unchanged interpreter.
"""

from collections import OrderedDict
from .exact import Limit


def root_only(action, value):
    w = tuple(value)
    action.tick()
    if len(w) > action.L["word_length"]:
        raise Limit("word_length")
    wreath_cache = getattr(action, "wcache", {})
    if w in wreath_cache:
        return wreath_cache[w][0]
    cache = getattr(action, "_root_only_cache", None)
    if cache is None:
        cache = OrderedDict()
        action._root_only_cache = cache
    if w in cache:
        cache.move_to_end(w)
        return cache[w]
    permutation = tuple(range(action.d))
    for i, g in enumerate(w):
        if i % 1024 == 0:
            action.tick()
        r = action.roots[g - 1] if g > 0 else action.inverse_roots[-g - 1]
        permutation = tuple(r[x] for x in permutation)
    action.stats["letter_steps"] += len(w) * action.d
    if action.stats["letter_steps"] > action.L["letter_steps"]:
        raise Limit("letter_steps")
    while len(cache) >= min(100000, action.L["cache_entries"]):
        cache.popitem(last=False)
    cache[w] = permutation
    return permutation


def selected_depth_two(action, value):
    """Same finite signature as full decomposition, computing only used sections."""
    w = tuple(value)
    action.tick()
    cache = getattr(action, "_selected_depth_two_cache", None)
    if cache is None:
        cache = OrderedDict()
        action._selected_depth_two_cache = cache
    if w in cache:
        cache.move_to_end(w)
        return cache[w]
    full = getattr(action, "wcache", {}).get(w)
    root = full[0] if full is not None else root_only(action, w)
    answer = [root]
    for x in (0, action.d - 1):
        section = full[1][x] if full is not None else action.step(w, x)[1]
        answer.append(root_only(action, section))
    result = tuple(answer)
    while len(cache) >= min(100000, action.L["cache_entries"]):
        cache.popitem(last=False)
    cache[w] = result
    return result
