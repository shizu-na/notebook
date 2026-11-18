#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
docs/ 以下の Markdown ファイルの表記ゆれ修正・構文チェックを行うスクリプト。

使い方（リポジトリのルートで実行）:
    python scripts/fix_md.py              # 全テーマの自動修正（\boldsymbol置換・$$前後の空行調整）＋ 構文チェック
    python scripts/fix_md.py iitaka       # 指定したテーマだけ実行
    python scripts/fix_md.py --check-only # ファイルを書き換えずにチェックだけ行う

自動修正する内容:
  1. \boldsymbol → \mathbf への一括置換
  2. 独立行のディスプレイ数式 $$...$$ の前後に空行がない場合、空行を挿入（引用ブロック `> ` 内にも対応）

警告（チェック）する内容:
  - 1行の中で太字記号 `**` の個数が奇数（片割れ・閉じ忘れ）になっている箇所を行番号付きで表示
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT_DIR / "docs"
EXCLUDE_DIRS = {"javascripts", "stylesheets", "assets", "images"}

# 単一行のディスプレイ数式: 任意の `> ` プレフィックス + $$...$$
SINGLE_LINE_DISPLAY_MATH_RE = re.compile(r"^(\s*(?:>\s*)*)\$\$(.+)\$\$\s*$")
# 数式内の ** (例: V^{**}) を除外するためのパターン
MATH_SPAN_RE = re.compile(r"\$\$[\s\S]*?\$\$|\$[^$\n]+\$")
CODE_SPAN_RE = re.compile(r"`[^`\n]+`")


def iter_md_files(themes: list[str]) -> list[Path]:
    if not themes:
        return sorted(DOCS_DIR.rglob("*.md"))
    files: list[Path] = []
    for theme in themes:
        target = DOCS_DIR / theme
        if target.is_file():
            files.append(target)
        elif target.is_dir():
            files.extend(sorted(target.rglob("*.md")))
    return files


def ensure_blank_lines_around_display_math(text: str) -> tuple[str, int]:
    """単一行 $$...$$ の前後に空行がない場合、空行を補う（引用ブロック対応）。"""
    lines = text.splitlines()
    out: list[str] = []
    added = 0

    for i, line in enumerate(lines):
        m = SINGLE_LINE_DISPLAY_MATH_RE.match(line)
        if m:
            prefix = m.group(1).rstrip()
            # 前の行が空行（または同じ引用レベルの空行）でなければ挿入
            if out:
                prev = out[-1].strip()
                if prev != "" and prev != ">":
                    out.append(prefix)
                    added += 1
            out.append(line)
            # 次の行が空行でなければ挿入
            if i + 1 < len(lines):
                nxt = lines[i + 1].strip()
                if nxt != "" and nxt != ">":
                    out.append(prefix)
                    added += 1
        else:
            out.append(line)

    result = "\n".join(out)
    if text.endswith("\n"):
        result += "\n"
    return result, added


def find_unmatched_bold_lines(text: str) -> list[tuple[int, str]]:
    """数式 ($...$) やインラインコード (`...`) を除いた部分で `**` が奇数個の行を検出する。"""
    warnings: list[tuple[int, str]] = []
    in_code_block = False

    for idx, line in enumerate(text.splitlines(), start=1):
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue

        # 数式とインラインコードを除去してから ** の個数を数える
        cleaned = MATH_SPAN_RE.sub("", line)
        cleaned = CODE_SPAN_RE.sub("", cleaned)
        count = cleaned.count("**")
        if count % 2 == 1:
            warnings.append((idx, line.strip()))

    return warnings


def process_file(path: Path, check_only: bool = False) -> tuple[int, int, list[tuple[int, str]]]:
    original = path.read_text(encoding="utf-8")
    if not original:
        return 0, 0, []

    # 1. \boldsymbol -> \mathbf
    bs_count = len(re.findall(r"\\boldsymbol\b", original))
    updated = re.sub(r"\\boldsymbol\b", r"\\mathbf", original)

    # 2. $$...$$ 前後の空行確保
    updated, math_blank_count = ensure_blank_lines_around_display_math(updated)

    if not check_only and updated != original:
        path.write_text(updated, encoding="utf-8")

    # 3. ** の片割れチェック
    warnings = find_unmatched_bold_lines(updated)
    return bs_count, math_blank_count, warnings


def main() -> None:
    parser = argparse.ArgumentParser(description="Markdown ファイルの自動整形と構文チェックを行います。")
    parser.add_argument("themes", nargs="*", help="対象のテーマ名（省略時は docs/ 全体）")
    parser.add_argument("--check-only", action="store_true", help="ファイルを書き換えずにチェックのみ行う")
    args = parser.parse_args()

    files = iter_md_files(args.themes)
    total_bs = 0
    total_math_blanks = 0
    total_warnings = 0
    modified_files = 0

    for md_path in files:
        bs_count, math_blank_count, warnings = process_file(md_path, check_only=args.check_only)
        rel = md_path.relative_to(ROOT_DIR).as_posix()

        if bs_count or math_blank_count:
            modified_files += 1
            total_bs += bs_count
            total_math_blanks += math_blank_count
            action = "検出" if args.check_only else "修正"
            details = []
            if bs_count:
                details.append(f"\\boldsymbol→\\mathbf: {bs_count}箇所")
            if math_blank_count:
                details.append(f"$$前後の空行追加: {math_blank_count}行")
            print(f"[{action}] {rel} ({', '.join(details)})")

        if warnings:
            total_warnings += len(warnings)
            for line_no, preview in warnings:
                short = preview if len(preview) <= 70 else preview[:67] + "..."
                print(f"  [要確認: 太字 ** の片割れ] {rel}:{line_no}  {short}")

    print("-" * 60)
    print(
        f"完了: 対象 {len(files)} ファイル / "
        f"修正 {modified_files} ファイル (\\boldsymbol置換 {total_bs}件, $$空行補完 {total_math_blanks}件) / "
        f"太字(`**`)片割れ警告 {total_warnings}件"
    )


if __name__ == "__main__":
    main()
