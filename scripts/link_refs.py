#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
docs/ 以下の Markdown 本文中にある節番号（例: 0-2節, 1-2・1-4節, 0-4〜0-6節）および
部番号（例: 第1部）を、同一テーマ内の相対パスリンクへ自動変換するスクリプト。

使い方（リポジトリのルートで実行）:
    python scripts/link_refs.py                   # 全テーマに対して実行
    python scripts/link_refs.py seeing-4d         # 指定したテーマだけ実行
    python scripts/link_refs.py docs/iitaka/3     # 指定ディレクトリ・ファイルのみ実行
    python scripts/link_refs.py --dry-run         # 書き換えずに差分プレビューのみ表示

安全設計（冪等・誤爆防止）:
  - コードブロック / インラインコード / 数式 ($...$, $$...$$) / SVG・HTMLタグ /
    見出し行 / 既存リンク ([...](...)) / URL 内は一切書き換えない。
  - 同一テーマ内に実在する節・部のみをリンク化し、自分自身の節への自己リンクは張らない。
  - 各テーマの index.md の `### 第X部...` 見出しに `{ #part-X }` アンカーを自動付与する。
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT_DIR / "docs"

# 記事ファイル名: <part>-<sec>.md
SECTION_FILE_RE = re.compile(r"^(\d+)-(\d+)\.md$")
# index.md の部見出し: ### 第X部...
PART_HEADING_RE = re.compile(r"^(###\s+第(\d+)部[^\r\n]*?)(\s*\{\s*#part-\2\s*\})?\s*$")

# 行内で保護（マスク）するトークン: 既存リンク・画像 / 数式 / インラインコード / HTMLタグ / URL
PROTECTED_RE = re.compile(
    r"!?\[[^\]]*\]\([^)]+\)"           # Markdown リンク・画像
    r"|\$\$[^\n]+?\$\$"                # 単一行ディスプレイ数式
    r"|(?<!\\)\$(?:\\.|[^$\\\n])+?\$"  # インライン数式
    r"|`[^`\n]+`"                      # インラインコード
    r"|<[^>]+>"                        # HTML タグ
    r"|https?://[^\s)>\]\"']+"         # 生 URL
)

# 節参照: 0-2節 / 1-2・1-4節 / 0-4〜0-6節 / 0-2・0-3・0-4節 など
SECTION_REF_RE = re.compile(
    r"(?<![0-9０-９\-/])(\d+-\d+(?:\s*[・〜～、,]\s*\d+-\d+)*)(節)"
)
# 個別の P-S トークン
SINGLE_SEC_RE = re.compile(r"(\d+)-(\d+)")

# 部参照: 第1部 など
PART_REF_RE = re.compile(r"第(\d+)部")

# ブロック開始・終了判定
FENCE_RE = re.compile(r"^\s*(?:>\s*)*(```|~~~)")
DISPLAY_MATH_DELIM_RE = re.compile(r"^\s*(?:>\s*)*\$\$\s*$")
HEADING_RE = re.compile(r"^\s*#{1,6}\s+")


@dataclass
class ThemeIndex:
    theme_dir: Path
    sections: set[tuple[int, int]]
    parts: set[int]


def build_theme_index(theme_dir: Path) -> ThemeIndex:
    sections: set[tuple[int, int]] = set()
    parts: set[int] = set()

    for md in theme_dir.glob("*/*.md"):
        m = SECTION_FILE_RE.match(md.name)
        if m and md.parent.name == m.group(1):
            p, s = int(m.group(1)), int(m.group(2))
            sections.add((p, s))
            parts.add(p)

    # index.md に見出しがある部も確認
    index_md = theme_dir / "index.md"
    if index_md.is_file():
        for line in index_md.read_text(encoding="utf-8").splitlines():
            m = PART_HEADING_RE.match(line)
            if m:
                parts.add(int(m.group(2)))

    return ThemeIndex(theme_dir=theme_dir, sections=sections, parts=parts)


def ensure_index_part_anchors(theme_dir: Path, dry_run: bool = False) -> int:
    """テーマの index.md の `### 第X部...` 見出しに `{ #part-X }` アンカーを付与する。"""
    index_md = theme_dir / "index.md"
    if not index_md.is_file():
        return 0

    original = index_md.read_text(encoding="utf-8")
    lines = original.splitlines()
    out: list[str] = []
    added = 0

    for line in lines:
        m = PART_HEADING_RE.match(line)
        if m and not m.group(3):
            part_num = m.group(2)
            heading_body = m.group(1).rstrip()
            out.append(f"{heading_body} {{ #part-{part_num} }}")
            added += 1
        else:
            out.append(line)

    if added > 0 and not dry_run:
        result = "\n".join(out)
        if original.endswith("\n"):
            result += "\n"
        index_md.write_text(result, encoding="utf-8", newline="\n")

    return added


def make_section_relpath(curr_part: int, target_part: int, target_sec: int) -> str:
    if curr_part == target_part:
        return f"{target_part}-{target_sec}.md"
    return f"../{target_part}/{target_part}-{target_sec}.md"


def linkify_line(
    line: str,
    curr_part: int,
    curr_sec: int,
    theme_idx: ThemeIndex,
    include_parts: bool = True,
) -> tuple[str, int, int]:
    """1行の本文テキストに対して安全に節・部リンクを付与する。"""
    if HEADING_RE.match(line):
        return line, 0, 0

    # 保護領域をプレースホルダに退避
    protected: list[str] = []

    def _mask(match: re.Match[str]) -> str:
        idx = len(protected)
        protected.append(match.group(0))
        return f"\x00PROT{idx}\x00"

    masked = PROTECTED_RE.sub(_mask, line)

    sec_links = 0
    part_links = 0

    # 1. 節番号（単体および連記・範囲）をリンク化
    def _replace_section_group(match: re.Match[str]) -> str:
        nonlocal sec_links
        body = match.group(1)  # 例: "1-2・1-4" または "0-2"
        suffix = match.group(2)  # "節"

        tokens = list(SINGLE_SEC_RE.finditer(body))
        if not tokens:
            return match.group(0)

        parts_out: list[str] = []
        pos = 0
        for i, tok in enumerate(tokens):
            parts_out.append(body[pos : tok.start()])
            p, s = int(tok.group(1)), int(tok.group(2))
            is_last = i == len(tokens) - 1
            label = f"{p}-{s}{suffix}" if is_last else f"{p}-{s}"

            if (p, s) in theme_idx.sections and (p, s) != (curr_part, curr_sec):
                rel = make_section_relpath(curr_part, p, s)
                parts_out.append(f"[{label}]({rel})")
                sec_links += 1
            else:
                parts_out.append(label)
            pos = tok.end()

        parts_out.append(body[pos:])
        return "".join(parts_out)

    masked = SECTION_REF_RE.sub(_replace_section_group, masked)

    # 節リンクで新しく生成した [...](...) を保護し直す（念のため）
    if sec_links:
        masked = PROTECTED_RE.sub(_mask, masked)

    # 2. 部番号（第X部）をリンク化
    if include_parts:
        def _replace_part(match: re.Match[str]) -> str:
            nonlocal part_links
            p = int(match.group(1))
            if p in theme_idx.parts:
                part_links += 1
                return f"[第{p}部](../index.md#part-{p})"
            return match.group(0)

        masked = PART_REF_RE.sub(_replace_part, masked)

    # プレースホルダを復元（ネスト対策で逆順・複数回不要な1パス置換）
    def _unmask(match: re.Match[str]) -> str:
        return protected[int(match.group(1))]

    # 2段マスクに対応するため最大2回展開
    restored = re.sub(r"\x00PROT(\d+)\x00", _unmask, masked)
    if "\x00PROT" in restored:
        restored = re.sub(r"\x00PROT(\d+)\x00", _unmask, restored)

    return restored, sec_links, part_links


def process_article(
    path: Path,
    theme_idx: ThemeIndex,
    include_parts: bool = True,
    dry_run: bool = False,
) -> tuple[int, int, list[tuple[int, str, str]]]:
    m = SECTION_FILE_RE.match(path.name)
    if not m or path.parent.name != m.group(1):
        return 0, 0, []

    curr_part, curr_sec = int(m.group(1)), int(m.group(2))
    original = path.read_text(encoding="utf-8")
    lines = original.splitlines()
    out: list[str] = []

    in_fence: str | None = None
    in_display_math = False
    in_raw_html: str | None = None  # "svg" | "style" | "script"

    total_sec = 0
    total_part = 0
    changes: list[tuple[int, str, str]] = []

    for lineno, line in enumerate(lines, start=1):
        # コードフェンス判定
        fm = FENCE_RE.match(line)
        if fm and not in_display_math and not in_raw_html:
            fence_char = fm.group(1)
            if in_fence is None:
                in_fence = fence_char
            elif in_fence == fence_char:
                in_fence = None
            out.append(line)
            continue

        if in_fence is not None:
            out.append(line)
            continue

        # 複数行 $$ ブロック判定
        if DISPLAY_MATH_DELIM_RE.match(line) and not in_raw_html:
            in_display_math = not in_display_math
            out.append(line)
            continue

        if in_display_math:
            out.append(line)
            continue

        # <svg> / <figure> / <figcaption> / <summary> / <style> / <script> ブロック判定
        lower = line.lower()
        if in_raw_html is None:
            for tag in ("svg", "figure", "figcaption", "summary", "style", "script"):
                if f"<{tag}" in lower:
                    if f"</{tag}>" not in lower:
                        in_raw_html = tag
                    out.append(line)
                    break
            else:
                pass
            if in_raw_html is not None or any(
                f"<{tag}" in lower for tag in ("svg", "figure", "figcaption", "summary", "style", "script")
            ):
                continue
        else:
            if f"</{in_raw_html}>" in lower:
                in_raw_html = None
            out.append(line)
            continue

        new_line, s_cnt, p_cnt = linkify_line(
            line, curr_part, curr_sec, theme_idx, include_parts=include_parts
        )
        if new_line != line:
            total_sec += s_cnt
            total_part += p_cnt
            changes.append((lineno, line, new_line))
        out.append(new_line)

    if changes and not dry_run:
        result = "\n".join(out)
        if original.endswith("\n"):
            result += "\n"
        path.write_text(result, encoding="utf-8", newline="\n")

    return total_sec, total_part, changes


def resolve_targets(targets: list[str]) -> list[Path]:
    if not targets:
        return sorted(DOCS_DIR.glob("*/*/*.md"))

    files: list[Path] = []
    for t in targets:
        candidates = [DOCS_DIR / t, ROOT_DIR / t, Path(t)]
        for cand in candidates:
            if cand.is_file() and cand.suffix == ".md":
                files.append(cand.resolve())
                break
            if cand.is_dir():
                files.extend(sorted(p.resolve() for p in cand.rglob("*.md")))
                break
    # 本文ファイル (<theme>/<part>/<part>-<sec>.md) のみ抽出
    article_files: list[Path] = []
    for f in dict.fromkeys(files):
        try:
            rel = f.relative_to(DOCS_DIR.resolve())
        except ValueError:
            continue
        if len(rel.parts) == 3 and SECTION_FILE_RE.match(rel.name):
            article_files.append(f)
    return sorted(article_files)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="本文中の節番号・部番号の参照を相対パスリンクへ自動変換します。"
    )
    parser.add_argument(
        "targets",
        nargs="*",
        help="対象テーマ・ディレクトリ・ファイル（省略時は docs/ 全体）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="ファイルを書き換えずに変更プレビューのみ表示する",
    )
    parser.add_argument(
        "--no-parts",
        action="store_true",
        help="第X部 のリンク化をスキップし、節番号のみリンク化する",
    )
    parser.add_argument(
        "--show-all",
        action="store_true",
        help="--dry-run 時に各ファイルの全変更行を表示する",
    )
    args = parser.parse_args()

    files = resolve_targets(args.targets)
    if not files:
        print("対象の記事ファイルが見つかりませんでした。")
        return

    # テーマ単位でインデックス構築 & index.md のアンカー補完
    theme_indices: dict[Path, ThemeIndex] = {}
    total_anchors = 0
    for f in files:
        theme_dir = f.parent.parent
        if theme_dir not in theme_indices:
            theme_indices[theme_dir] = build_theme_index(theme_dir)
            if not args.no_parts:
                added = ensure_index_part_anchors(theme_dir, dry_run=args.dry_run)
                if added:
                    total_anchors += added
                    rel_idx = (theme_dir / "index.md").relative_to(ROOT_DIR).as_posix()
                    tag = "検出" if args.dry_run else "更新"
                    print(f"[{tag}] {rel_idx} (部アンカー追加: {added}箇所)")

    total_files_mod = 0
    total_sec_links = 0
    total_part_links = 0

    for f in files:
        theme_dir = f.parent.parent
        s_cnt, p_cnt, changes = process_article(
            f,
            theme_indices[theme_dir],
            include_parts=not args.no_parts,
            dry_run=args.dry_run,
        )
        if changes:
            total_files_mod += 1
            total_sec_links += s_cnt
            total_part_links += p_cnt
            rel = f.relative_to(ROOT_DIR).as_posix()
            tag = "予定" if args.dry_run else "更新"
            print(f"[{tag}] {rel} (節リンク: {s_cnt}件, 部リンク: {p_cnt}件)")
            if args.dry_run:
                limit = len(changes) if args.show_all else 3
                for lineno, old, new in changes[:limit]:
                    print(f"  L{lineno}:")
                    print(f"    - {old.strip()[:120]}")
                    print(f"    + {new.strip()[:120]}")
                if not args.show_all and len(changes) > limit:
                    print(f"  ... 他 {len(changes) - limit} 行")

    print("-" * 60)
    mode = "ドライラン" if args.dry_run else "完了"
    print(
        f"{mode}: 対象 {len(files)} ファイル / 変更 {total_files_mod} ファイル "
        f"(節リンク {total_sec_links}件, 部リンク {total_part_links}件, "
        f"index.mdアンカー追加 {total_anchors}件)"
    )


if __name__ == "__main__":
    main()
