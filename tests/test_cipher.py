import random

import pytest

from Umm_Font import MAX_VARIANTS, cipher_map, decrypt, encrypt
from Umm_Font.cipher import HANGUL, HANGUL_FIRST, HANGUL_LAST

SAMPLE = "가나다 힣! ABC 123, ㄱㅏ 漢字 😀\n줄바꿈"


@pytest.mark.parametrize("variants", [1, 3, MAX_VARIANTS])
def test_decrypt_restores_encrypted_text(variants):
    encrypted = encrypt("seed", SAMPLE, variants)

    assert encrypted != SAMPLE
    assert decrypt("seed", encrypted, variants) == SAMPLE


def test_only_hangul_syllables_are_replaced():
    encrypted = encrypt("seed", SAMPLE)

    for plain, cipher in zip(SAMPLE, encrypted, strict=True):
        if HANGUL_FIRST <= ord(plain) <= HANGUL_LAST:
            assert cipher != plain
        else:
            assert cipher == plain


@pytest.mark.parametrize("seed_a, seed_b, same", [
    (1234, "1234", True),
    ("seed", "seed", True),
    ("seed", "seed2", False),
])
def test_mapping_depends_only_on_seed(seed_a, seed_b, same):
    assert (cipher_map(seed_a) == cipher_map(seed_b)) is same


@pytest.mark.parametrize("variants", [1, 3, MAX_VARIANTS])
def test_every_cipher_codepoint_is_unique(variants):
    mapping = cipher_map("seed", variants)
    ciphers = [c for group in mapping.values() for c in group]

    assert len(mapping) == len(HANGUL)
    assert all(len(group) == variants for group in mapping.values())
    assert len(set(ciphers)) == len(ciphers)


def test_single_variant_is_permutation_of_hangul():
    ciphers = {group[0] for group in cipher_map("seed", 1).values()}

    assert ciphers == set(HANGUL)


@pytest.mark.parametrize("rng_a, rng_b, same", [
    (random.Random(1), random.Random(1), True),
    (random.Random(1), random.Random(2), False),
])
def test_variant_choice_follows_rng(rng_a, rng_b, same):
    text = "가" * 50

    assert (encrypt("seed", text, rng=rng_a) == encrypt("seed", text, rng=rng_b)) is same


@pytest.mark.parametrize("variants", [0, MAX_VARIANTS + 1])
def test_rejects_out_of_range_variants(variants):
    with pytest.raises(ValueError):
        encrypt("seed", "가", variants)
