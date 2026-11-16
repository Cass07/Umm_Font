"""CLI.

python -m Umm_Font build   --seed S [-o out.woff2] [--font my.ttf] [--variants 3]
python -m Umm_Font encrypt --seed S [--variants 3] 텍스트   (텍스트 생략 시 stdin)
python -m Umm_Font decrypt --seed S [--variants 3] 텍스트
"""

import argparse
import sys

from .cipher import DEFAULT_VARIANTS, decrypt, encrypt
from .font import build_font


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="Umm_Font")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="seed로 난독화 폰트 생성")
    build.add_argument("-o", "--output", default="out/umm-font.woff2")
    build.add_argument("--font", help="원본 폰트 경로 (기본: 내장 Noto Sans KR)")
    build.add_argument("--weight", type=float, default=400)
    build.add_argument("--jitter", type=int, default=8)
    build.add_argument("--extra-points", type=int, default=2)
    build.add_argument("--family", help="폰트 패밀리 이름 (기본: seed 기반 무작위)")

    for command in ("encrypt", "decrypt"):
        p = sub.add_parser(command, help=f"seed로 데이터 {'암호화' if command == 'encrypt' else '복호화'}")
        p.add_argument("text", nargs="?", help="생략하면 stdin을 읽음")

    for p in sub.choices.values():
        p.add_argument("--seed", required=True)
        p.add_argument("--variants", type=int, default=DEFAULT_VARIANTS)

    args = parser.parse_args(argv)
    if args.command == "build":
        path = build_font(args.seed, args.output, args.font, variants=args.variants,
                          weight=args.weight, jitter=args.jitter,
                          extra_points=args.extra_points, family_name=args.family)
        print(path)
        return

    text = args.text if args.text is not None else sys.stdin.read()
    func = encrypt if args.command == "encrypt" else decrypt
    sys.stdout.write(func(args.seed, text, args.variants))
    if args.text is not None:
        sys.stdout.write("\n")


if __name__ == "__main__":
    main()
