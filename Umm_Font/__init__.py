"""한글 치환 + 난독화 폰트로 크롤러에게는 엉뚱한 글자를, 사람에게는 원문을 보여 준다."""

from .cipher import DEFAULT_VARIANTS, MAX_VARIANTS, cipher_map, decrypt, encrypt
from .font import DEFAULT_FONT, build_font

__all__ = [
    "DEFAULT_FONT", "DEFAULT_VARIANTS", "MAX_VARIANTS",
    "build_font", "cipher_map", "decrypt", "encrypt",
]
