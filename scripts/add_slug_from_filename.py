#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations
import argparse
import re
from pathlib import Path
from typing import Tuple, Optional, List, Dict

DATE_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[-_]+")

def detect_language(md_path: Path) -> str:
    # crude but practical: content/en/... or content/zh/...
    parts = [p.lower() for p in md_path.parts]
    if "content" in parts:
        i = parts.index("content")
        if i + 1 < len(parts):
            lang = parts[i + 1]
            if lang in ("en", "zh"):
                return lang
    return "unknown"

def slugify_from_name(name: str) -> str:
    # remove extension already; normalize
    s = name.strip()
    s = DATE_PREFIX_RE.sub("", s)
    s = s.replace(" ", "-").replace("_", "-")
    s = s.lower()
    # collapse multiple hyphens
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "untitled"

def split_front_matter(text: str) -> Tuple[Optional[str], str, Optional[str]]:
    """
    Return (front_matter, body, fm_delim) where fm_delim is '---' if YAML FM exists.
    If no YAML FM, return (None, text, None)
    """
    # Allow BOM
    if text.startswith("\ufeff"):
        text_wo_bom = text[1:]
        bom = "\ufeff"
    else:
        text_wo_bom = text
        bom = ""

    if not text_wo_bom.startswith("---"):
        return None, text, None

    # find closing '---' on its own line
    # We keep original newlines
    lines = text_wo_bom.splitlines(keepends=True)
    if not lines:
        return None, text, None
    if not lines[0].lstrip().startswith("---"):
        return None, text, None

    # scan for second delimiter line
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return None, text, None

    fm = "".join(lines[1:end_idx])
    body = "".join(lines[end_idx + 1 :])
    # restore BOM if any (keep it in front matter start)
    return fm, bom + body, "---"

def has_key(fm: str, key: str) -> bool:
    # match YAML top-level key:   key: ...
    # allow indentation 0..2 (some people indent by mistake)
    pattern = re.compile(rf"^[ \t]{{0,2}}{re.escape(key)}\s*:", re.MULTILINE)
    return bool(pattern.search(fm))

def insert_slug(fm: str, slug_value: str) -> str:
    slug_line = f'slug: "{slug_value}"\n'

    # Prefer inserting after title: line if exists, else near top.
    m = re.search(r"^([ \t]{0,2}title\s*:[^\n]*\n)", fm, flags=re.MULTILINE)
    if m:
        insert_pos = m.end(1)
        return fm[:insert_pos] + slug_line + fm[insert_pos:]

    # Else insert after first non-empty line, or at beginning
    lines = fm.splitlines(keepends=True)
    if not lines:
        return slug_line
    for idx, line in enumerate(lines):
        if line.strip() != "":
            # insert after this line
            lines.insert(idx + 1, slug_line)
            return "".join(lines)
    # all empty
    return slug_line + fm

def compute_slug_for_file(md_path: Path) -> str:
    name = md_path.stem  # without .md
    if md_path.name.lower() == "index.md":
        # leaf bundle: use parent dir
        parent = md_path.parent.name
        return slugify_from_name(parent)
    return slugify_from_name(name)

def iter_markdown_files(roots: List[Path]) -> List[Path]:
    files: List[Path] = []
    for root in roots:
        if not root.exists():
            continue
        files.extend([p for p in root.rglob("*.md") if p.is_file()])
    # stable order
    return sorted(files, key=lambda p: str(p))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--roots",
        nargs="+",
        default=["content/en/posts", "content/zh/posts"],
        help="Roots to scan (default: content/en/posts content/zh/posts)",
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Write changes to files. Without this flag, does a dry-run.",
    )
    args = ap.parse_args()

    roots = [Path(r).resolve() for r in args.roots]
    files = iter_markdown_files(roots)

    used_slugs: Dict[str, Dict[str, int]] = {}  # lang -> slug -> count
    planned: List[Tuple[Path, str]] = []

    # First pass: decide slugs and de-dup per language
    for f in files:
        if f.name.lower() == "_index.md":
            continue  # section index: skip

        text = f.read_text(encoding="utf-8")
        fm, body, delim = split_front_matter(text)
        if delim != "---" or fm is None:
            continue  # only YAML FM

        # skip if slug/url already exists
        if has_key(fm, "slug") or has_key(fm, "url"):
            continue

        lang = detect_language(f)
        slug = compute_slug_for_file(f)

        used_slugs.setdefault(lang, {})
        if slug in used_slugs[lang]:
            used_slugs[lang][slug] += 1
            slug = f"{slug}-{used_slugs[lang][slug]}"
        else:
            used_slugs[lang][slug] = 1

        planned.append((f, slug))

    if not planned:
        print("No files need slug. (Either already have slug/url, or not YAML front matter.)")
        return

    # Second pass: apply
    changed = 0
    for f, slug in planned:
        text = f.read_text(encoding="utf-8")
        fm, body, delim = split_front_matter(text)
        if fm is None or delim != "---":
            continue

        new_fm = insert_slug(fm, slug)
        new_text = "---\n" + new_fm + "---\n" + body

        if args.apply:
            f.write_text(new_text, encoding="utf-8")
        changed += 1
        print(f"{'[APPLY]' if args.apply else '[DRY]  '} {f.relative_to(Path.cwd())}  -> slug={slug}")

    print(f"\nDone. {'Wrote' if args.apply else 'Planned'} {changed} files.")

if __name__ == "__main__":
    main()
