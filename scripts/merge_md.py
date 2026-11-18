#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
docs/<テーマ>/ 以下のマークダウンを1つのファイルに結合するスクリプト。

使い方（リポジトリのルートで実行）:
    python scripts/merge_md.py iitaka        # 指定したテーマを結合
    python scripts/merge_md.py --all         # すべてのテーマを結合
    python scripts/merge_md.py --list        # テーマ一覧を表示

保存先: output/<テーマ>_all.md

構成のルール:
    docs/<テーマ>/index.md        テーマの目次（先頭に入る）
    docs/<テーマ>/<N>/<N>-<M>.md  第N部の第M節（数字順に並ぶ）
部の見出しは index.md 中の「第N部：…」という見出しから取得し、
見つからなければ「第N部」とする。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT_DIR / "docs"
OUTPUT_DIR = ROOT_DIR / "output"

# docs 直下でテーマとして扱わないディレクトリ
EXCLUDE_DIRS = {"javascripts", "stylesheets", "assets", "images"}

PART_HEADING_RE = re.compile(r"^#+\s*(第\s*(\d+)\s*部.*?)\s*$")
SECTION_FILE_RE = re.compile(r"^(\d+)-(\d+)\.md$")


def list_themes() -> list[str]:
    return sorted(
        p.name
        for p in DOCS_DIR.iterdir()
        if p.is_dir() and p.name not in EXCLUDE_DIRS and not p.name.startswith(".")
    )


def read_part_titles(index_text: str) -> dict[int, str]:
    titles: dict[int, str] = {}
    for line in index_text.splitlines():
        m = PART_HEADING_RE.match(line)
        if m:
            titles.setdefault(int(m.group(2)), m.group(1))
    return titles


def section_files(part_dir: Path) -> list[Path]:
    files = []
    for p in part_dir.glob("*.md"):
        m = SECTION_FILE_RE.match(p.name)
        if m:
            files.append((int(m.group(2)), p))
    return [p for _, p in sorted(files)]


def merge_theme(theme: str) -> Path:
    theme_dir = DOCS_DIR / theme
    if not theme_dir.is_dir():
        raise SystemExit(f"テーマが見つかりません: {theme}（候補: {', '.join(list_themes())}）")

    sections: list[str] = []

    index_path = theme_dir / "index.md"
    index_text = index_path.read_text(encoding="utf-8").strip() if index_path.exists() else ""
    if index_text:
        sections.append(index_text)
    part_titles = read_part_titles(index_text)

    part_dirs = sorted(
        (p for p in theme_dir.iterdir() if p.is_dir() and p.name.isdigit()),
        key=lambda p: int(p.name),
    )
    for part_dir in part_dirs:
        part_num = int(part_dir.name)
        part_chunks: list[str] = [f"# {part_titles.get(part_num, f'第{part_num}部')}"]
        for md_path in section_files(part_dir):
            content = md_path.read_text(encoding="utf-8").strip()
            rel = md_path.relative_to(theme_dir).as_posix()
            part_chunks.append(content if content else f"<!-- {rel} (未記入) -->")
        sections.append("\n\n---\n\n".join(part_chunks))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / f"{theme}_all.md"
    output_file.write_text("\n\n---\n\n".join(sections) + "\n", encoding="utf-8")
    return output_file


def main() -> None:
    parser = argparse.ArgumentParser(description="テーマごとにマークダウンを結合します。")
    parser.add_argument("themes", nargs="*", help="結合するテーマ名（docs/ 直下のフォルダ名）")
    parser.add_argument("--all", action="store_true", help="すべてのテーマを結合")
    parser.add_argument("--list", action="store_true", help="テーマ一覧を表示")
    args = parser.parse_args()

    if args.list:
        print("\n".join(list_themes()))
        return

    themes = list_themes() if args.all else args.themes
    if not themes:
        parser.print_help()
        sys.exit(1)

    for theme in themes:
        out = merge_theme(theme)
        print(f"結合完了: {out.relative_to(ROOT_DIR).as_posix()}")


if __name__ == "__main__":
    main()
