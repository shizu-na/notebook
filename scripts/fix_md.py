#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
docs/ 以下の Markdown ファイルの表記ゆれ修正・リスト整形・構文チェックを行うスクリプト。

使い方（リポジトリのルートで実行）:
    python scripts/fix_md.py              # 全テーマの自動修正 ＋ 構文チェック
    python scripts/fix_md.py iitaka       # 指定したテーマだけ実行
    python scripts/fix_md.py --check-only # ファイルを書き換えずにチェックだけ行う

自動修正する内容:
  1. \boldsymbol → \mathbf への一括置換
  2. \xleftrightarrow{...} → \overset{...}{\longleftrightarrow} への一括置換
  3. 独立行のディスプレイ数式 $$...$$ の前後に空行がない場合、空行を挿入（引用ブロック `> ` 内にも対応）
  4. 箇条書き（`* ` や `1. `）の直前の行が非空行でリスト項目でない場合や、インデントされた段落の直後に
     別レベルのリスト項目が続くことで Python-Markdown がリストとして認識できない箇所に自動で空行を補完

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
# リスト項目の行: 任意の `> ` プレフィックス + インデント + (`* ` or `- ` or `1. `)
LIST_ITEM_RE = re.compile(r"^((?:>\s*)*)(\s*)(?:[\*\-]\s+|\d+\.\s+)")
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
            if out:
                prev = out[-1].strip()
                if prev != "" and prev != ">":
                    out.append(prefix)
                    added += 1
            out.append(line)
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


def ensure_blank_lines_before_lists(text: str) -> tuple[str, int]:
    """
    Python-Markdown でリスト項目 (`* ` や `1. `) が直前の段落に吸収されてしまうのを防ぐため、
    必要な箇所に空行を挿入する。
    """
    lines = text.splitlines()
    out: list[str] = []
    added = 0
    in_code_block = False

    for line in lines:
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            out.append(line)
            continue
        if in_code_block:
            out.append(line)
            continue

        m = LIST_ITEM_RE.match(line)
        if m and out:
            quote_prefix = m.group(1).rstrip()
            curr_indent = len(m.group(2))
            prev_line = out[-1]
            prev_stripped = prev_line.strip()

            # 前の行が空行でなく、見出しでも引用開始だけの行でもない場合
            if prev_stripped != "" and prev_stripped != ">":
                prev_m = LIST_ITEM_RE.match(prev_line)
                if not prev_m:
                    # 前の行が通常のテキスト行（リスト継続段落など）のとき、空行を入れる
                    out.append(quote_prefix)
                    added += 1
                else:
                    # 前の行もリスト項目だが、インデントが深くなる（ネスト開始）または浅くなるとき、
                    # Python-Markdown はネスト開始前に空行を要求する場合がある
                    prev_indent = len(prev_m.group(2))
                    if curr_indent != prev_indent:
                        out.append(quote_prefix)
                        added += 1

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

        cleaned = MATH_SPAN_RE.sub("", line)
        cleaned = CODE_SPAN_RE.sub("", cleaned)
        count = cleaned.count("**")
        if count % 2 == 1:
            warnings.append((idx, line.strip()))

    return warnings


def process_file(path: Path, check_only: bool = False) -> tuple[int, int, int, int, list[tuple[int, str]]]:
    original = path.read_text(encoding="utf-8")
    if not original:
        return 0, 0, 0, 0, []

    # 1. \boldsymbol -> \mathbf
    bs_count = len(re.findall(r"\\boldsymbol\b", original))
    updated = re.sub(r"\\boldsymbol\b", r"\\mathbf", original)

    # 2. \xleftrightarrow{...} -> \overset{...}{\longleftrightarrow}
    updated, xlra_count = re.subn(
        r"\\xleftrightarrow\{([^{}]*)\}",
        r"\\overset{\1}{\\longleftrightarrow}",
        updated,
    )

    # 3. $$...$$ 前後の空行確保
    updated, math_blank_count = ensure_blank_lines_around_display_math(updated)

    # 4. リスト項目直前の空行確保
    updated, list_blank_count = ensure_blank_lines_before_lists(updated)

    if not check_only and updated != original:
        path.write_text(updated, encoding="utf-8", newline="\n")

    # 5. ** の片割れチェック
    warnings = find_unmatched_bold_lines(updated)
    return bs_count, xlra_count, math_blank_count, list_blank_count, warnings


def main() -> None:
    parser = argparse.ArgumentParser(description="Markdown ファイルの自動整形と構文チェックを行います。")
    parser.add_argument("themes", nargs="*", help="対象のテーマ名（省略時は docs/ 全体）")
    parser.add_argument("--check-only", action="store_true", help="ファイルを書き換えずにチェックのみ行う")
    args = parser.parse_args()

    files = iter_md_files(args.themes)
    total_bs = 0
    total_xlra = 0
    total_math_blanks = 0
    total_list_blanks = 0
    total_warnings = 0
    modified_files = 0

    for md_path in files:
        bs_count, xlra_count, math_blank_count, list_blank_count, warnings = process_file(
            md_path, check_only=args.check_only
        )
        rel = md_path.relative_to(ROOT_DIR).as_posix()

        if bs_count or xlra_count or math_blank_count or list_blank_count:
            modified_files += 1
            total_bs += bs_count
            total_xlra += xlra_count
            total_math_blanks += math_blank_count
            total_list_blanks += list_blank_count
            action = "検出" if args.check_only else "修正"
            details = []
            if bs_count:
                details.append(f"\\boldsymbol→\\mathbf: {bs_count}箇所")
            if xlra_count:
                details.append(f"\\xleftrightarrow置換: {xlra_count}箇所")
            if math_blank_count:
                details.append(f"$$前後の空行追加: {math_blank_count}行")
            if list_blank_count:
                details.append(f"リスト前空行追加: {list_blank_count}行")
            print(f"[{action}] {rel} ({', '.join(details)})")

        if warnings:
            total_warnings += len(warnings)
            for line_no, preview in warnings:
                short = preview if len(preview) <= 70 else preview[:67] + "..."
                print(f"  [要確認: 太字 ** の片割れ] {rel}:{line_no}  {short}")

    print("-" * 60)
    print(
        f"完了: 対象 {len(files)} ファイル / "
        f"修正 {modified_files} ファイル (\\boldsymbol置換 {total_bs}件, \\xleftrightarrow置換 {total_xlra}件, "
        f"$$空行補完 {total_math_blanks}件, リスト空行補完 {total_list_blanks}件) / "
        f"太字(`**`)片割れ警告 {total_warnings}件"
    )


if __name__ == "__main__":
    main()
