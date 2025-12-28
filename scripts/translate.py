#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import hashlib
from pathlib import Path
from typing import Any, Dict, Tuple, Optional

import yaml

# Google Translate v2 client
from google.cloud import translate_v2 as translate
from google.oauth2 import service_account

CONTENT_ROOT = Path("content")

CACHE_FILE = Path(".cache/mt_cache.json")  # 可选缓存
FRONT_DELIM = "---"


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def split_frontmatter(md: str) -> Tuple[Optional[str], str]:
    """Only supports YAML frontmatter: --- ... ---"""
    if not md.startswith(FRONT_DELIM):
        return None, md
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", md, flags=re.S)
    if not m:
        return None, md
    return m.group(1), m.group(2)


def dump_frontmatter(data: Dict[str, Any]) -> str:
    y = yaml.safe_dump(data, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{y}\n---\n"


def load_cache() -> Dict[str, str]:
    if CACHE_FILE.exists():
        return json.loads(CACHE_FILE.read_text("utf-8"))
    return {}


def save_cache(cache: Dict[str, str]) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), "utf-8")


def normalize_translate_cfg(raw: Any) -> Optional[Dict[str, Any]]:
    """
    Accept:
      translate: {mode, targets, draft}
    If translate missing -> None
    """
    if raw is None:
        return None
    if isinstance(raw, str):
        # translate: google / stub
        return {"mode": raw, "targets": ["zh"]}
    if isinstance(raw, dict):
        return raw
    return None


def derive_slug(src_path: Path, fm: Dict[str, Any]) -> str:
    slug = fm.get("slug")
    if isinstance(slug, str) and slug.strip():
        return slug.strip()

    # bundle: content/<lang>/posts/xxx/index.md -> slug=xxx
    if src_path.name.lower() == "index.md":
        return src_path.parent.name

    # normal file: xxx.md -> xxx
    return src_path.stem


def get_rel_under_src(src_path: Path, src_root: Path) -> Path:
    return src_path.relative_to(src_root)


def ensure_translation_key(fm: Dict[str, Any], slug: str) -> Tuple[Dict[str, Any], bool, str]:
    """If missing translationKey, set to slug and return (fm, changed, translationKey)"""
    tk = fm.get("translationKey")
    if isinstance(tk, str) and tk.strip():
        return fm, False, tk.strip()

    fm["translationKey"] = slug
    return fm, True, slug


def build_target_frontmatter(
    src_fm: Dict[str, Any],
    slug: str,
    tk: str,
    draft: bool,
    mode: str,
) -> Dict[str, Any]:
    """
    Create new target frontmatter.
    Minimal script control fields:
      - kq_managed: true   (allow sync draft/translationKey later)
      - kq_mt: true/false  (used for MT notice; (you decided not to noindex by it))
    """
    fm = dict(src_fm)

    # normalize common frontmatter keys (Title->title, Date->date, Lastmod->lastmod)
    for k_from, k_to in (("Title", "title"), ("Date", "date"), ("Lastmod", "lastmod")):
        if k_from in fm and k_to not in fm:
            fm[k_to] = fm.pop(k_from)

    # optional: trim title
    if isinstance(fm.get("title"), str):
        fm["title"] = fm["title"].strip()

    fm.pop("translate", None)

    fm["translationKey"] = tk
    fm.setdefault("slug", slug)
    fm["draft"] = bool(draft)

    fm["kq_managed"] = True
    fm.setdefault("kq_mt", (mode == "google"))  # user can later set false manually

    return fm


def translate_text_google(client: translate.Client, text: str, source_lang: str, target_lang: str) -> str:
    res = client.translate(
        text,
        target_language=target_lang,
        source_language=source_lang,
        format_="text",
    )
    return res["translatedText"]


def translate_title_if_needed(
    client: translate.Client,
    fm: Dict[str, Any],
    source_lang: str,
    target_lang: str,
    mode: str,
) -> Optional[str]:
    """
    Title is treated like body:
    - Only translate when creating NEW target file (dst doesn't exist)
    - Never update existing file's title automatically
    """
    if mode != "google":
        return None
    t = fm.get("title")
    if not isinstance(t, str) or not t.strip():
        return None
    return translate_text_google(client, t.strip(), source_lang, target_lang)


def main() -> None:
    sa_json = os.environ.get("GCP_SA_KEY_JSON")
    if not sa_json:
        raise SystemExit("Missing env: GCP_SA_KEY_JSON (service account JSON)")

    creds = service_account.Credentials.from_service_account_info(json.loads(sa_json))
    client = translate.Client(credentials=creds)

    cache = load_cache()
    created = 0
    synced = 0
    adopted = 0
    skipped_exists = 0
    updated_src = 0
    skipped_no_translate = 0

    # ✅ 只认这些语言目录（避免扫到 shared/ 等）
    LANGS = {"en", "zh", "ja"}  # 按你的实际语言写
    lang_roots = [CONTENT_ROOT / l for l in LANGS if (CONTENT_ROOT / l).is_dir()]
    all_langs = sorted([p.name for p in lang_roots])

    for src_root in lang_roots:
        src_lang = src_root.name

        for src in src_root.rglob("*.md"):
            md = src.read_text("utf-8")
            fm_raw, body = split_frontmatter(md)
            if fm_raw is None:
                continue

            try:
                fm = yaml.safe_load(fm_raw) or {}
            except Exception as e:
                print(f"[WARN] YAML parse failed: {src} -> {e}")
                continue

            tcfg = normalize_translate_cfg(fm.get("translate"))
            if not tcfg:
                skipped_no_translate += 1
                continue

            mode = str(tcfg.get("mode", "")).strip().lower()
            if mode not in ("google", "stub"):
                print(f"[WARN] Unknown translate.mode in {src}: {mode} (use google|stub)")
                continue

            targets = tcfg.get("targets")
            if not targets:
                targets = [l for l in all_langs if l != src_lang]
            if isinstance(targets, str):
                targets = [targets]
            targets = [str(x).strip() for x in targets if str(x).strip()]
            targets = [x for x in targets if x != src_lang]

            draft = tcfg.get("draft")
            if draft is None:
                draft = True
            draft = bool(draft)

            slug = derive_slug(src, fm)

            # Ensure translationKey backwrite to SOURCE
            fm, changed, tk = ensure_translation_key(fm, slug)
            if changed:
                src.write_text(dump_frontmatter(fm) + body, "utf-8")
                updated_src += 1

            # Cache (record only)
            cache[str(src)] = sha256(fm_raw + "\n\n" + body)

            rel = get_rel_under_src(src, src_root)

            for lang in targets:
                dst = CONTENT_ROOT / lang / rel

                # ===== exists: sync frontmatter only (draft/translationKey), do not touch body/title =====
                if dst.exists():
                    dst_md = dst.read_text("utf-8")
                    dst_fm_raw, dst_body = split_frontmatter(dst_md)
                    if dst_fm_raw is None:
                        skipped_exists += 1
                        continue

                    try:
                        dst_fm = yaml.safe_load(dst_fm_raw) or {}
                    except Exception:
                        skipped_exists += 1
                        continue

                    # Auto-adopt old generated translations (before kq_managed existed)
                    params = dst_fm.get("params")
                    looks_generated = (
                        dst_fm.get("translationKey") in (None, tk)
                        or dst_fm.get("robotsNoIndex") is True
                        or (isinstance(params, dict) and params.get("mt") is True)
                        or (dst_fm.get("kq_mt") is True)
                    )

                    if dst_fm.get("kq_managed") is not True and looks_generated:
                        dst_fm["kq_managed"] = True
                        dst_fm.setdefault("kq_mt", (mode == "google"))
                        adopted += 1

                    if dst_fm.get("kq_managed") is True:
                        if dst_fm.get("kq_mt") is True:
                            dst_fm.setdefault("kq_mt_from", src_lang)
                            dst_fm.setdefault("kq_mt_to", lang)

                        dst_fm["draft"] = bool(draft)
                        dst_fm.setdefault("translationKey", tk)

                        dst.write_text(dump_frontmatter(dst_fm) + dst_body, "utf-8")
                        synced += 1
                    else:
                        skipped_exists += 1

                    continue
                # ================================================================================

                # ===== create new translation =====
                dst.parent.mkdir(parents=True, exist_ok=True)
                target_fm = build_target_frontmatter(fm, slug, tk, draft, mode)

                if mode == "google":
                    target_fm.setdefault("kq_mt_from", src_lang)
                    target_fm.setdefault("kq_mt_to", lang)

                # Only on FIRST creation: translate title (like body)
                new_title = translate_title_if_needed(client, fm, src_lang, lang, mode)
                if new_title:
                    target_fm["title"] = new_title

                if mode == "stub":
                    out_body = (
                        "<!-- TODO: translate manually -->\n\n"
                        f"> Source: /{src_lang}/{rel.as_posix().replace('index.md','')}\n"
                    )
                    out = dump_frontmatter(target_fm) + out_body
                else:
                    translated = translate_text_google(client, body, src_lang, lang)
                    out = dump_frontmatter(target_fm) + translated

                dst.write_text(out, "utf-8")
                created += 1
                # ===============================

    save_cache(cache)
    print(
        f"Done. created={created}, synced={synced}, adopted={adopted}, "
        f"skipped_exists={skipped_exists}, updated_src={updated_src}, skipped_no_translate={skipped_no_translate}"
    )


if __name__ == "__main__":
    main()
