import pytest
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.reverseContourPen import ReverseContourPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
from PIL import Image, ImageChops, ImageDraw, ImageFont

from Umm_Font import DEFAULT_FONT, build_font, cipher_map, encrypt
from Umm_Font.cipher import HANGUL

SEED = "test-seed"
SAMPLE_CHARS = "가나힣글폰트"
TINY_CHARS = "가나다"
# 기본 jitter(±8 unit)로 96px 렌더 시 외곽 픽셀이 3~15% 바뀐다. 다른 글자끼리는 ~58%.
SAME_GLYPH = 0.2
DIFFERENT_GLYPH = 0.3


@pytest.fixture(scope="session")
def built_font(tmp_path_factory):
    return build_font(SEED, tmp_path_factory.mktemp("font") / "built.ttf")


@pytest.fixture(scope="session")
def tiny_cff_font(tmp_path_factory):
    """원본 Noto에서 몇 글자만 뽑아 만든 CFF(OTF) 폰트. 사용자 지정 폰트·CFF 경로 테스트용."""
    source = instancer.instantiateVariableFont(TTFont(DEFAULT_FONT), {"wght": 400})  # 기본 인스턴스는 Thin
    glyph_set, cmap, hmtx = source.getGlyphSet(), source.getBestCmap(), source["hmtx"]
    names = [".notdef"] + [f"g{i}" for i in range(len(TINY_CHARS))]
    charstrings, metrics = {}, {}
    for name, ch in zip(names, [None, *TINY_CHARS]):
        source_name = cmap[ord(ch)] if ch else ".notdef"
        advance, lsb = hmtx[source_name]
        pen = T2CharStringPen(advance, glyph_set)
        glyph_set[source_name].draw(ReverseContourPen(pen))
        charstrings[name], metrics[name] = pen.getCharString(), (advance, lsb)

    builder = FontBuilder(1000, isTTF=False)
    builder.setupGlyphOrder(names)
    builder.setupCharacterMap({ord(ch): name for ch, name in zip(TINY_CHARS, names[1:])})
    builder.setupCFF("Tiny-Regular", {"FullName": "Tiny"}, charstrings, {})
    builder.setupHorizontalMetrics(metrics)
    builder.setupHorizontalHeader(ascent=880, descent=-120)
    builder.setupNameTable({"familyName": "Tiny", "styleName": "Regular"})
    builder.setupOS2()
    builder.setupPost()
    path = tmp_path_factory.mktemp("tiny") / "tiny.otf"
    builder.save(path)
    return path


def _render(font_path, text, weight=None):
    font = ImageFont.truetype(str(font_path), 96)
    if weight is not None:
        font.set_variation_by_axes([weight])
    image = Image.new("L", (140 * len(text), 140), 255)
    ImageDraw.Draw(image).text((10, 10), text, font=font, fill=0)
    return image


def _mismatch(a, b):
    """잉크 픽셀 대비 다르게 그려진 픽셀 비율."""
    diff = ImageChops.difference(a, b).point(lambda v: 255 if v > 128 else 0)
    ink = ImageChops.darker(a, b).point(lambda v: 255 if v < 128 else 0)
    return diff.histogram()[255] / max(ink.histogram()[255], 1)


def _render_source(text):
    return _render(DEFAULT_FONT, text, weight=400)


def test_every_cipher_variant_renders_original_glyph(built_font):
    mapping = cipher_map(SEED)

    for ch in SAMPLE_CHARS:
        for cipher in mapping[ord(ch)]:
            assert _mismatch(_render(built_font, chr(cipher)), _render_source(ch)) < SAME_GLYPH, ch


def test_encrypted_text_renders_as_plain_text(built_font):
    text = "한글 폰트 테스트"

    assert _mismatch(_render(built_font, encrypt(SEED, text)), _render_source(text)) < SAME_GLYPH


def test_original_codepoint_no_longer_renders_original_glyph(built_font):
    assert _mismatch(_render(built_font, "가"), _render_source("가")) > DIFFERENT_GLYPH


def test_glyph_names_and_source_name_are_removed(built_font):
    font = TTFont(built_font)
    raw = built_font.read_bytes()

    assert font["post"].formatType == 3.0
    assert b"uniAC00" not in raw
    assert "Noto" not in font["name"].getDebugName(1)


def test_hangul_glyph_ids_are_not_in_codepoint_order(built_font):
    font = TTFont(built_font)
    cmap = font.getBestCmap()
    first_variant = {plain: ciphers[0] for plain, ciphers in cipher_map(SEED).items()}
    glyph_ids = [font.getGlyphID(cmap[first_variant[plain]]) for plain in HANGUL]

    assert glyph_ids != sorted(glyph_ids)


def test_outline_points_differ_from_source(built_font):
    source = TTFont(DEFAULT_FONT)
    built = TTFont(built_font)
    built_name = built.getBestCmap()[cipher_map(SEED)[ord("가")][0]]

    source_coords = list(source["glyf"]["uniAC00"].coordinates)
    built_coords = list(built["glyf"][built_name].coordinates)

    assert built_coords != source_coords


def test_custom_cff_font_is_converted_and_remapped(tiny_cff_font, tmp_path):
    with pytest.warns(UserWarning, match="원본 폰트에 없는 한글 음절"):
        path = build_font(SEED, tmp_path / "tiny.ttf", tiny_cff_font)

    assert "glyf" in TTFont(path) and "CFF " not in TTFont(path)
    for ch in TINY_CHARS:
        rendered = _render(path, encrypt(SEED, ch))
        assert _mismatch(rendered, _render(tiny_cff_font, ch)) < SAME_GLYPH, ch


@pytest.mark.filterwarnings("ignore:원본 폰트에 없는 한글 음절")
@pytest.mark.parametrize("seed_b, same", [(SEED, True), ("other-seed", False)])
def test_same_seed_produces_identical_file(tiny_cff_font, tmp_path, seed_b, same):
    a = build_font(SEED, tmp_path / "a.ttf", tiny_cff_font)
    b = build_font(seed_b, tmp_path / "b.ttf", tiny_cff_font)

    assert (a.read_bytes() == b.read_bytes()) is same


@pytest.mark.filterwarnings("ignore:원본 폰트에 없는 한글 음절")
@pytest.mark.parametrize("suffix, flavor", [(".ttf", None), (".woff", "woff"), (".woff2", "woff2")])
def test_output_format_follows_extension(tiny_cff_font, tmp_path, suffix, flavor):
    path = build_font(SEED, tmp_path / f"out{suffix}", tiny_cff_font)

    assert TTFont(path).flavor == flavor
