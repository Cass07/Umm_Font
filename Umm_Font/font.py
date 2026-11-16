"""Seed로 치환 매핑에 맞는 폰트를 만든다.

적용하는 난독화:
- cmap 교체: 암호 코드포인트가 원문 글자의 글리프를 가리킨다. 원래 한글 코드포인트는 모두 재할당된다.
- 단서 제거: 글리프 이름 삭제(post format 3), 글리프 순서(ID) 셔플, 힌팅·레이아웃 등 부가 테이블 삭제,
  폰트 이름 교체.
- 윤곽선 변형: 좌표 jitter, 컨투어 시작점 회전, 직선 구간에 보이지 않는 점 추가.
  원본 폰트와 좌표, 점 개수를 대조하는 매칭을 어렵게 한다.
"""

from __future__ import annotations

import os
import warnings
from pathlib import Path

from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates
from fontTools.varLib import instancer

from .cipher import DEFAULT_VARIANTS, HANGUL, Seed, cipher_map, in_cipher_ranges, seeded_rng

DEFAULT_FONT = Path(__file__).parent / "fonts" / "NotoSansKR-VF.ttf"

# 매핑 추적에 쓰일 수 있거나, 윤곽선·글리프 순서를 바꾸면 깨지는 테이블
_DROP_TABLES = (
    "GSUB", "GPOS", "GDEF", "BASE", "JSTF", "MATH", "kern", "morx", "feat",
    "fpgm", "prep", "cvt ", "hdmx", "LTSH", "VDMX", "DSIG", "meta",
    "vhea", "vmtx", "VORG", "STAT",
)
_KEEP_NAME_IDS = (0, 13, 14)  # 저작권, 라이선스 설명, 라이선스 URL (OFL 요구사항)
_ON_CURVE = 0x01
_OVERLAP_SIMPLE = 0x40


def build_font(
    seed: Seed,
    output_path: str | os.PathLike,
    font_path: str | os.PathLike | None = None,
    *,
    variants: int = DEFAULT_VARIANTS,
    weight: float = 400,
    jitter: int = 8,
    extra_points: int = 2,
    family_name: str | None = None,
) -> Path:
    """seed에 맞는 난독화 폰트를 ``output_path``에 저장한다.

    font_path: 원본 폰트(TTF/OTF, 가변 폰트 가능). 생략하면 내장 Noto Sans KR.
    variants: 한 글자당 암호 코드포인트 수. encrypt/decrypt와 같은 값을 써야 한다.
    weight: 가변 폰트일 때 고정할 굵기(wght 축).
    jitter: 좌표를 흔드는 최대 폭(font unit). Noto Sans KR은 1em = 1000 unit.
    extra_points: 컨투어마다 추가할 보이지 않는 점의 최대 개수.
    family_name: CSS font-family 등에 쓰일 이름. 생략하면 seed에서 무작위로 만든다.
    출력 형식은 확장자로 정한다: .woff2 / .woff / 그 외(.ttf).
    """
    font = TTFont(font_path or DEFAULT_FONT)
    font.recalcTimestamp = False  # 같은 seed, 같은 원본이면 같은 파일이 나오도록
    if "fvar" in font:
        font = _instantiate(font, weight)

    for tag in _DROP_TABLES:
        if tag in font:
            del font[tag]

    _make_simple_truetype(font)
    _distort_outlines(font, seeded_rng(seed, "outline"), jitter, extra_points)
    hangul_glyphs = _remap_cmap(font, cipher_map(seed, variants))
    _shuffle_glyph_order(font, hangul_glyphs, seeded_rng(seed, "glyph-order"))
    font["post"].formatType = 3.0
    _rename(font, family_name or _random_family(seed))

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    font.flavor = {".woff2": "woff2", ".woff": "woff"}.get(output_path.suffix.lower())
    font.save(output_path)
    return output_path


def _instantiate(font: TTFont, weight: float) -> TTFont:
    location = {axis.axisTag: axis.defaultValue for axis in font["fvar"].axes}
    if "wght" in location:
        location["wght"] = weight
    return instancer.instantiateVariableFont(font, location)


def _make_simple_truetype(font: TTFont) -> None:
    """모든 글리프를 힌팅 없는 단순(비복합) TrueType 글리프로 만든다. CFF 폰트는 glyf로 변환한다."""
    order = font.getGlyphOrder()
    glyph_set = font.getGlyphSet()

    if "glyf" in font:
        glyf = font["glyf"]
        for name in order:
            glyph = glyf[name]
            if glyph.isComposite():
                glyf[name] = _redraw(glyph_set, name, cubic=False)
            else:
                glyph.removeHinting()
        return

    if "CFF " not in font:
        raise ValueError("glyf 또는 CFF 윤곽선이 있는 폰트만 지원합니다.")
    glyphs = {name: _redraw(glyph_set, name, cubic=True) for name in order}
    glyf = font["glyf"] = newTable("glyf")
    glyf.glyphOrder = order
    glyf.glyphs = glyphs
    font["loca"] = newTable("loca")
    del font["CFF "]
    font.sfntVersion = "\x00\x01\x00\x00"
    font["head"].glyphDataFormat = 0
    maxp = font["maxp"]
    maxp.tableVersion = 0x00010000
    maxp.maxZones = 1
    for attr in ("maxTwilightPoints", "maxStorage", "maxFunctionDefs", "maxInstructionDefs",
                 "maxStackElements", "maxSizeOfInstructions", "maxComponentElements",
                 "maxComponentDepth"):
        setattr(maxp, attr, 0)
    font["post"].formatType = 3.0


def _redraw(glyph_set, name: str, cubic: bool):
    recording = DecomposingRecordingPen(glyph_set)
    glyph_set[name].draw(recording)
    tt_pen = TTGlyphPen(None)
    # CFF는 3차 곡선, 반대 방향 → 2차 곡선으로 근사하고 방향을 뒤집는다.
    recording.replay(Cu2QuPen(tt_pen, max_err=1.0, reverse_direction=True) if cubic else tt_pen)
    return tt_pen.glyph()


def _distort_outlines(font: TTFont, rng, jitter: int, extra_points: int) -> None:
    glyf, hmtx = font["glyf"], font["hmtx"]
    for name in font.getGlyphOrder():
        glyph = glyf[name]
        if glyph.numberOfContours <= 0:
            continue
        overlap = glyph.flags[0] & _OVERLAP_SIMPLE
        coords: list[tuple[int, int]] = []
        flags = bytearray()
        ends: list[int] = []
        start = 0
        for end in glyph.endPtsOfContours:
            points = [(tuple(glyph.coordinates[i]), glyph.flags[i] & _ON_CURVE)
                      for i in range(start, end + 1)]
            start = end + 1
            points = _insert_points(points, rng, extra_points)
            k = rng.randrange(len(points))
            points = points[k:] + points[:k]
            for (x, y), on_curve in points:
                coords.append((round(x) + rng.randint(-jitter, jitter),
                               round(y) + rng.randint(-jitter, jitter)))
                flags.append(on_curve)
            ends.append(len(coords) - 1)
        flags[0] |= overlap
        glyph.coordinates = GlyphCoordinates(coords)
        glyph.flags = flags
        glyph.endPtsOfContours = ends
        glyph.recalcBounds(glyf)
        advance, _ = hmtx[name]
        hmtx[name] = (advance, glyph.xMin)


def _insert_points(points, rng, max_extra: int):
    """연속한 두 on-curve 점(직선) 사이에 중점을 넣는다. 모양은 그대로이고 점 개수와 순서만 바뀐다."""
    count = rng.randint(0, max_extra)
    for _ in range(count):
        n = len(points)
        lines = [i for i in range(n) if points[i][1] and points[(i + 1) % n][1]]
        if not lines:
            break
        i = rng.choice(lines)
        (x0, y0), _ = points[i]
        (x1, y1), _ = points[(i + 1) % n]
        points.insert(i + 1, (((x0 + x1) / 2, (y0 + y1) / 2), _ON_CURVE))
    return points


def _remap_cmap(font: TTFont, mapping: dict[int, tuple[int, ...]]) -> set[str]:
    """cmap을 암호 매핑으로 교체하고, 한글 음절 글리프 이름 집합을 돌려준다."""
    source = font.getBestCmap()
    new_map = {cp: g for cp, g in source.items() if not in_cipher_ranges(cp)}
    hangul_glyphs: set[str] = set()
    missing = 0
    for plain, ciphers in mapping.items():
        glyph_name = source.get(plain)
        if glyph_name is None:
            missing += 1
            continue
        hangul_glyphs.add(glyph_name)
        for c in ciphers:
            new_map[c] = glyph_name
    if missing:
        warnings.warn(f"원본 폰트에 없는 한글 음절 {missing}/{len(HANGUL)}자는 빈 글자(.notdef)로 표시됩니다.")

    bmp = {cp: g for cp, g in new_map.items() if cp <= 0xFFFF}
    specs = [(4, 0, 3, bmp), (4, 3, 1, bmp)]
    if len(bmp) != len(new_map):
        specs += [(12, 0, 4, new_map), (12, 3, 10, new_map)]
    cmap = font["cmap"]
    cmap.tables = []
    for fmt, platform_id, encoding_id, entries in specs:
        table = CmapSubtable.newSubtable(fmt)
        table.platformID, table.platEncID, table.language = platform_id, encoding_id, 0
        table.cmap = dict(entries)
        cmap.tables.append(table)
    return hangul_glyphs


def _shuffle_glyph_order(font: TTFont, hangul_glyphs: set[str], rng) -> None:
    """한글 글리프끼리만 ID 자리를 섞는다.

    전체를 섞어도 숨기는 효과는 같지만, 그러면 한자 등 나머지 글리프의 cmap 구간이 잘게 쪼개져
    format 4 서브테이블이 64KB 한도를 넘는다.
    """
    for tag in font.keys():  # 순서를 바꾸기 전에 모든 테이블을 현재 순서로 읽어 둔다
        font[tag]
    new_order = list(font.getGlyphOrder())
    slots = [i for i, name in enumerate(new_order) if name in hangul_glyphs]
    names = [new_order[i] for i in slots]
    rng.shuffle(names)
    for i, name in zip(slots, names):
        new_order[i] = name
    font.setGlyphOrder(new_order)
    font["glyf"].glyphOrder = new_order


def _random_family(seed: Seed) -> str:
    rng = seeded_rng(seed, "family")
    return "F" + "".join(rng.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(11))


def _rename(font: TTFont, family: str) -> None:
    name = font["name"]
    name.names = [record for record in name.names if record.nameID in _KEEP_NAME_IDS]
    ps_name = "".join(ch for ch in family if ch.isalnum() or ch == "-")[:63] or "UmmFont"
    for name_id, value in ((1, family), (2, "Regular"), (3, f"{ps_name}-Regular"),
                           (4, family), (6, ps_name)):
        name.setName(value, name_id, 3, 1, 0x409)
