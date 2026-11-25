"""Near-duplicate detection for proposed tasks.

Cheap lexical similarity (Jaccard over word sets and word bigrams, with the
title weighted heavily). It runs inside the queue on every new proposal, so it
must be fast and deterministic; it flags, and a triager decides.
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Set, Tuple

STOP = set("""a an and are as at be been but by can could do does for from has have how i if in
into is it its may must not of on or our should so that the their them then there these this
those to was we were what when where which while who will with without you your add fix make
update use task issue""".split())


def tokens(text: str) -> List[str]:
    text = re.sub(r"```.*?```", " ", text or "", flags=re.S)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    text = re.sub(r"https?://\S+", " ", text)
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [w for w in words if len(w) > 2 and w not in STOP]


def features(title: str, body: str) -> Tuple[Set[str], Set[str]]:
    t = tokens(title)
    b = tokens(body)[:400]
    bi = {f"{x} {y}" for x, y in zip(b, b[1:])}
    return set(t), set(b) | bi


def jaccard(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def similarity(a: Tuple[Set[str], Set[str]], b: Tuple[Set[str], Set[str]]) -> float:
    title = jaccard(a[0], b[0])
    if not a[1] or not b[1]:
        return title
    combined = 0.65 * title + 0.35 * jaccard(a[1], b[1])
    # Long, near-identical titles are a strong signal on their own.
    if min(len(a[0]), len(b[0])) >= 4:
        combined = max(combined, 0.9 * title)
    return combined


def matches(title: str, body: str, others: Iterable[Dict], threshold: float, limit: int = 3) -> List[Tuple[int, float]]:
    """[(issue number, score)] of others at or above threshold, best first."""
    me = features(title, body)
    out = []
    for o in others:
        s = similarity(me, features(o.get("title", ""), o.get("body", "") or ""))
        if s >= threshold:
            out.append((o["number"], round(s, 2)))
    out.sort(key=lambda x: -x[1])
    return out[:limit]
