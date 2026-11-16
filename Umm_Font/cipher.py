"""Seed 기반 한글 치환 매핑과 데이터 암호화/복호화.

각 한글 음절(가~힣, 11,172자)은 ``variants`` 개의 암호 코드포인트를 갖는다(1:N 치환).
암호화할 때는 매 글자마다 그중 하나를 무작위로 고르므로, 같은 원문도 매번 다른 문자열이 된다.
복호화는 역매핑 한 번으로 끝난다.

암호 코드포인트는 아래 순서로 앞에서부터 채운다.

1. 한글 음절 영역   U+AC00–U+D7A3     (11,172)  → 암호문이 그럴듯한 한글로 보임
2. 보충 사설 영역 A U+F0000–U+FFFFD   (65,534)
3. 보충 사설 영역 B U+100000–U+10FFFD (65,534)

BMP 사설 영역(U+E000–F8FF)은 쓰지 않는다. BMP 코드포인트는 cmap format 4에 들어가는데,
한자가 많은 한글 폰트에서는 format 4가 64KB 한도를 넘기 때문이다.
"""

from __future__ import annotations

import itertools
import random
from functools import lru_cache

HANGUL_FIRST = 0xAC00
HANGUL_LAST = 0xD7A3
HANGUL = range(HANGUL_FIRST, HANGUL_LAST + 1)

CIPHER_RANGES = (
    (HANGUL_FIRST, HANGUL_LAST),
    (0xF0000, 0xFFFFD),
    (0x100000, 0x10FFFD),
)
_POOL_SIZE = sum(last - first + 1 for first, last in CIPHER_RANGES)

DEFAULT_VARIANTS = 3
MAX_VARIANTS = _POOL_SIZE // len(HANGUL)  # 12

_SYSTEM_RANDOM = random.SystemRandom()

Seed = str | int


def seeded_rng(seed: Seed, purpose: str) -> random.Random:
    """seed와 용도별로 독립적인 결정적 RNG. 정수 1234와 문자열 "1234"는 같은 seed로 취급한다."""
    return random.Random(f"font-umm:{purpose}:{seed}")


def in_cipher_ranges(cp: int) -> bool:
    return any(first <= cp <= last for first, last in CIPHER_RANGES)


def _check_variants(variants: int) -> None:
    if not 1 <= variants <= MAX_VARIANTS:
        raise ValueError(f"variants는 1~{MAX_VARIANTS} 사이여야 합니다: {variants}")


def _pool(size: int) -> list[int]:
    ranges = (range(first, last + 1) for first, last in CIPHER_RANGES)
    return list(itertools.islice(itertools.chain.from_iterable(ranges), size))


@lru_cache(maxsize=32)
def _tables(seed: str, variants: int) -> tuple[dict[int, tuple[str, ...]], dict[int, str]]:
    pool = _pool(len(HANGUL) * variants)
    seeded_rng(seed, "mapping").shuffle(pool)
    forward: dict[int, tuple[str, ...]] = {}
    inverse: dict[int, str] = {}
    for i, plain in enumerate(HANGUL):
        ciphers = pool[i * variants:(i + 1) * variants]
        forward[plain] = tuple(chr(c) for c in ciphers)
        for c in ciphers:
            inverse[c] = chr(plain)
    return forward, inverse


def cipher_map(seed: Seed, variants: int = DEFAULT_VARIANTS) -> dict[int, tuple[int, ...]]:
    """원문 한글 코드포인트 → 암호 코드포인트 튜플. 폰트 생성에 쓰인다."""
    _check_variants(variants)
    forward, _ = _tables(str(seed), variants)
    return {plain: tuple(ord(c) for c in ciphers) for plain, ciphers in forward.items()}


def encrypt(seed: Seed, text: str, variants: int = DEFAULT_VARIANTS,
            rng: random.Random | None = None) -> str:
    """한글 음절만 치환하고 나머지 문자는 그대로 둔다.

    ``rng``를 주지 않으면 변형 선택은 매번 달라진다(복호화 결과는 항상 같다).
    재현 가능한 출력이 필요하면 ``random.Random(값)``을 넘긴다.
    """
    _check_variants(variants)
    forward, _ = _tables(str(seed), variants)
    pick = (rng or _SYSTEM_RANDOM).choice
    return "".join(pick(forward[ord(ch)]) if HANGUL_FIRST <= ord(ch) <= HANGUL_LAST else ch
                   for ch in text)


def decrypt(seed: Seed, text: str, variants: int = DEFAULT_VARIANTS) -> str:
    _check_variants(variants)
    _, inverse = _tables(str(seed), variants)
    return text.translate(inverse)
