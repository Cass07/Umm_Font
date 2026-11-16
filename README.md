# Umm_Font

한글 음절을 seed 기반으로 치환한 데이터와, 그 치환에 맞춰 수정한 폰트를 만든다.
이 폰트를 적용한 화면에서만 원문이 보이고, HTML을 긁어 가는 크롤러는 엉뚱한 글자를 얻는다.

## 설치

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'      # 실행만 할 거면 '.'
```

기본 원본 폰트로 Noto Sans KR 가변 폰트(`Umm_Font/fonts/`, SIL OFL)가 들어 있다.

## 사용법

```python
from Umm_Font import build_font, encrypt, decrypt

build_font("my-seed", "umm.woff2")  # 기본 Noto Sans KR
build_font("my-seed", "umm.woff2", "Pretendard.otf")  # 가진 폰트 지정 (TTF/OTF/가변)

enc = encrypt("my-seed", "가나 ABC")  # 예: '뎌\U000f1a2b ABC' (한글만 바뀜)
decrypt("my-seed", enc)  # '가나 ABC'
```

```bash
python -m Umm_Font build   --seed my-seed -o out/umm.woff2 [--font my.ttf]
python -m Umm_Font encrypt --seed my-seed "가나 ABC"
python -m Umm_Font decrypt --seed my-seed "<암호문>"
```

웹에서 적용:

```html
<style>
  @font-face { font-family: umm; src: url(/fonts/umm.woff2) format("woff2"); }
  .umm { font-family: umm; }
</style>
<p class="umm">{{ 암호화된 문자열 }}</p>
```

### 옵션

| 인자 | 기본값 | 설명 |
|---|---|---|
| `variants` | 3 | 한 글자당 암호 코드포인트 수(1~12). **build/encrypt/decrypt에 같은 값을 줘야 한다.** 1이면 한글끼리만 치환, 2 이상이면 사설 영역(PUA) 문자도 섞인다. |
| `weight` | 400 | 가변 폰트일 때 고정할 굵기 |
| `jitter` | 8 | 좌표를 흔드는 폭(font unit, 1em=1000). 얇은 굵기에서는 줄이는 게 좋다. |
| `extra_points` | 2 | 컨투어마다 추가할 보이지 않는 점의 최대 개수 |
| `family_name` | seed 기반 무작위 | 폰트 내부 이름 |
| `rng` (encrypt) | 시스템 난수 | 변형 선택 RNG. 넘기지 않으면 같은 원문도 매번 다른 암호문이 된다. |

seed는 `str`이나 `int`이고, `1234`와 `"1234"`는 같은 seed다.
같은 seed와 같은 원본 폰트로 만들면 바이트 단위로 같은 파일이 나온다.

## 적용된 난독화

1. **폰트 내부 단서 제거**: 글리프 이름 삭제(post format 3), 한글 글리프 ID 순서 셔플, 원래 한글 코드포인트 재할당,
   폰트 이름 교체, GSUB/GPOS/힌팅/세로쓰기 등 부가 테이블 삭제
2. **윤곽선 변형**: 좌표 jitter, 컨투어 시작점 회전, 직선 구간에 점 추가.
   원본 폰트와 좌표나 점 개수를 대조하는 매칭이 맞지 않게 된다(jitter=0이면 원본과 픽셀 단위로 같다).
3. **1:N 치환**: 원문 한 글자 → 암호 코드포인트 `variants`개 중 무작위. 빈도 분석과 diff를 방해한다.

## 주의

- 페이지에 암호화하지 않은 한글을 이 폰트로 표시하면 엉뚱한 글자가 나온다. 암호화한 텍스트에만 적용할 것.
- 복사·붙여넣기, 브라우저 내 검색, 스크린리더, 검색엔진 색인 모두 암호문 기준으로 동작한다.
- OFL 요구사항에 따라 저작권·라이선스 name 레코드(ID 0, 13, 14)는 남긴다. 원본 폰트 계열을 짐작할 수는 있지만, 글자 매핑과는 무관하다.
- 한글 외 문자(영문, 숫자, 한자, 자모)는 원본 그대로 렌더링된다.

## 테스트

```bash
.venv/bin/python -m pytest
.venv/bin/python -m ots out/umm.woff2   # 브라우저 폰트 검증기(OTS) 통과 여부
```
