#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import hashlib
import html
from pathlib import Path
from typing import Any, Dict, Tuple, Optional, List

import yaml

# Google Translate v2 client
from google.cloud import translate_v2 as translate
from google.oauth2 import service_account

FRONT_DELIM = "---"

# ✅ Do NOT carry vertical:true into these languages
VERTICAL_ALLOWED_LANGS = {"zh", "ja"}

# ✅ Tag dictionary
TAG_MAP_FILE_REL = Path("data/kq_tag_map.yaml")

# ✅ Batch-fix tags on existing translated files without adding any new frontmatter fields:
#   KQ_TAGS_SYNC=1 python3 translate.py
TAGS_SYNC = os.environ.get("KQ_TAGS_SYNC", "").strip().lower() in ("1", "true", "yes")

# ✅ If tag map missing / tag missing mapping -> fallback to machine translate (default ON)
#   KQ_TAGS_MT=0 to disable
TAGS_MT_FALLBACK = os.environ.get("KQ_TAGS_MT", "").strip().lower() not in ("0", "false", "no", "off")

# ✅ Optional: force re-translate body for existing managed MT files (DANGEROUS: overwrites manual edits)
#   KQ_FORCE_MT=1 python3 translate.py
FORCE_MT = os.environ.get("KQ_FORCE_MT", "").strip().lower() in ("1", "true", "yes")


def find_repo_root() -> Path:
    """
    Make paths stable no matter where you run the script from.
    Priority:
      1) env KQ_REPO_ROOT
      2) nearest parent containing "content/" directory
      3) script dir (or its parent)
    """
    env_root = os.environ.get("KQ_REPO_ROOT", "").strip()
    if env_root:
        p = Path(env_root).expanduser().resolve()
        if (p / "content").is_dir():
            return p

    here = Path(__file__).resolve()
    for p in [here.parent] + list(here.parents):
        if (p / "content").is_dir():
            return p

    # fallback: maybe script is in scripts/
    if (here.parent.parent / "content").is_dir():
        return here.parent.parent

    return here.parent


REPO_ROOT = find_repo_root()
CONTENT_ROOT = (REPO_ROOT / "content").resolve()
CACHE_FILE = (REPO_ROOT / ".cache/mt_cache.json").resolve()
TAG_MAP_FILE = (REPO_ROOT / TAG_MAP_FILE_REL).resolve()


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def split_frontmatter(md: str) -> Tuple[Optional[str], str]:
    """Only supports YAML frontmatter: --- ... ---"""
    # ✅ handle UTF-8 BOM
    md = md.lstrip("\ufeff")

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
        try:
            return json.loads(CACHE_FILE.read_text("utf-8"))
        except Exception:
            return {}
    return {}


def save_cache(cache: Dict[str, str]) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), "utf-8")


def normalize_frontmatter_keys(fm: Dict[str, Any]) -> None:
    """Normalize common key casing: Title/Date/Lastmod -> title/date/lastmod"""
    for k_from, k_to in (("Title", "title"), ("Date", "date"), ("Lastmod", "lastmod")):
        if k_from in fm and k_to not in fm:
            fm[k_to] = fm.pop(k_from)

    if isinstance(fm.get("title"), str):
        fm["title"] = fm["title"].strip()


def is_under_posts(rel: Path) -> bool:
    return bool(rel.parts) and rel.parts[0].lower() == "posts"


def load_tag_map() -> Tuple[Dict[str, Dict[str, str]], Dict[str, str]]:
    """
    Load tag map + build reverse index.

    Canonical recommended:
      building-site:
        en: Building Site
        zh: 建站
        ja: サイト構築

    Also supports old format:
      Building Site:
        zh: 建站
        ja: サイト構築
    (no "en" key; for en we fallback to the canonical key itself)

    Returns:
      tag_map: canonical -> {lang: name}
      rev: any_name(casefold) -> canonical
    """
    if not TAG_MAP_FILE.exists():
        return {}, {}

    try:
        raw = yaml.safe_load(TAG_MAP_FILE.read_text("utf-8")) or {}
        if not isinstance(raw, dict):
            return {}, {}

        tag_map: Dict[str, Dict[str, str]] = {}
        rev: Dict[str, str] = {}

        for canonical, langs in raw.items():
            if not isinstance(canonical, str) or not canonical.strip():
                continue
            if not isinstance(langs, dict):
                continue

            c = canonical.strip()
            tag_map.setdefault(c, {})

            # allow reverse lookup by canonical itself
            rev[c.casefold()] = c

            for lang, name in langs.items():
                lang_s = str(lang).strip()
                name_s = str(name).strip()
                if not lang_s or not name_s:
                    continue

                tag_map[c][lang_s] = name_s
                rev[name_s.casefold()] = c  # reverse lookup

        return tag_map, rev
    except Exception:
        return {}, {}


def normalize_translate_cfg(raw: Any) -> Optional[Dict[str, Any]]:
    """
    Accept many formats:

    1) translate: google / stub
    2) translate: true
    3) translate:
         mode: google|stub
         targets: [...]
         draft: true|false
    4) translate:
         enabled: true|false
         provider: google|stub  (provider treated as mode)
         targets: [...]
         draft: ...
    5) translate:
         enabled: true
         targets: [...]
         draft: ...
       (provider/mode omitted => default google)

    Returns normalized dict:
      {mode, targets, draft}
    or None when disabled/missing.
    """
    if raw is None:
        return None

    if raw is True:
        return {"mode": "google", "targets": None, "draft": True}

    if isinstance(raw, str):
        return {"mode": raw.strip().lower(), "targets": None, "draft": True}

    if isinstance(raw, dict):
        enabled = raw.get("enabled")
        if enabled is False:
            return None

        mode = raw.get("mode")
        provider = raw.get("provider")

        if (not mode) and provider:
            mode = provider

        if (not mode) and (enabled is True):
            mode = "google"

        if not mode:
            return None

        return {
            "mode": str(mode).strip().lower(),
            "targets": raw.get("targets"),
            "draft": raw.get("draft"),
        }

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
    target_lang: str,
    rel: Path,
) -> Dict[str, Any]:
    fm = dict(src_fm)
    normalize_frontmatter_keys(fm)

    # remove translate config from targets
    fm.pop("translate", None)

    # ✅ multi-language: do NOT carry fixed url into translations
    fm.pop("url", None)

    # ✅ type rules (compatible with your historical: type: post)
    if is_under_posts(rel):
        # posts/: don't write type, keep clean & avoid post/posts confusion
        fm.pop("type", None)
    else:
        # outside posts/: ensure it can appear in archives/list pages
        if not isinstance(fm.get("type"), str) or not fm["type"].strip():
            fm["type"] = "post"

    fm["translationKey"] = tk
    fm.setdefault("slug", slug)
    fm["draft"] = bool(draft)

    fm["kq_managed"] = True
    fm.setdefault("kq_mt", (mode == "google"))  # user can later set false manually

    # ✅ do not carry vertical to languages that don't need it
    if target_lang not in VERTICAL_ALLOWED_LANGS:
        fm.pop("vertical", None)

    return fm


def translate_text_google(client: translate.Client, text: str, source_lang: str, target_lang: str) -> str:
    res = client.translate(
        text,
        target_language=target_lang,
        source_language=source_lang,
        format_="text",
    )
    # v2 may return HTML entities
    return html.unescape(res["translatedText"])


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


def translate_tags(
    client: Optional[translate.Client],
    src_tags: Any,
    tag_map: Dict[str, Dict[str, str]],
    rev: Dict[str, str],
    source_lang: str,
    target_lang: str,
    mode: str,
) -> Optional[List[str]]:
    """
    Tags:
      1) Prefer kq_tag_map.yaml mapping (case-insensitive)
      2) If missing (file missing OR tag not mapped for that lang) and TAGS_MT_FALLBACK:
           - use Google MT when mode==google and client available
      3) Else keep raw tag

    Note:
      - If target_lang == "en" and canonical exists in tag_map, we can use canonical for old-format friendliness.
    """
    if not isinstance(src_tags, list) or not src_tags:
        return None

    out: List[str] = []
    for t in src_tags:
        if not isinstance(t, str) or not t.strip():
            continue
        raw = t.strip()

        canonical = rev.get(raw.casefold(), raw)
        mapped = tag_map.get(canonical, {}).get(target_lang)

        if mapped:
            out.append(mapped)
            continue

        # old-format friendly: en display as canonical if canonical is known
        if target_lang == "en" and canonical in tag_map:
            out.append(canonical)
            continue

        # fallback MT
        if TAGS_MT_FALLBACK and mode == "google" and client is not None:
            try:
                out.append(translate_text_google(client, raw, source_lang, target_lang))
                continue
            except Exception:
                pass

        out.append(raw)

    return out


def main() -> None:
    # ---- credentials ----
    sa_json = os.environ.get("GCP_SA_KEY_JSON", "").strip()
    creds = None

    if sa_json:
        creds = service_account.Credentials.from_service_account_info(json.loads(sa_json))
    else:
        # allow GOOGLE_APPLICATION_CREDENTIALS=file.json
        gac = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
        if gac and Path(gac).expanduser().exists():
            creds = service_account.Credentials.from_service_account_file(str(Path(gac).expanduser()))

    if creds is None:
        raise SystemExit(
            "Missing credentials. Set either:\n"
            "  - GCP_SA_KEY_JSON='{\"type\":...}'\n"
            "or\n"
            "  - GOOGLE_APPLICATION_CREDENTIALS=/path/to/service_account.json"
        )

    client = translate.Client(credentials=creds)

    tag_map, tag_rev = load_tag_map()
    cache = load_cache()

    created = 0
    synced = 0
    adopted = 0
    skipped_exists = 0
    updated_src = 0
    skipped_no_translate = 0
    warned_unknown_mode = 0

    # ✅ Only these language folders (avoid shared/ etc)
    LANGS = {"en", "zh", "ja"}  # adjust if you add more
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

            normalize_frontmatter_keys(fm)

            tcfg = normalize_translate_cfg(fm.get("translate"))
            if not tcfg:
                skipped_no_translate += 1
                continue

            mode = str(tcfg.get("mode", "")).strip().lower()
            if mode not in ("google", "stub"):
                print(f"[WARN] Unknown translate mode/provider in {src}: {mode} (use google|stub)")
                warned_unknown_mode += 1
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

                # ===== exists: sync frontmatter only (draft/translationKey + vertical + optional tags) =====
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

                    normalize_frontmatter_keys(dst_fm)

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

                        # ✅ multi-language: remove fixed url from translations
                        dst_fm.pop("url", None)

                        # ✅ type rules (compatible with your historical: type: post)
                        if is_under_posts(rel):
                            dst_fm.pop("type", None)
                        else:
                            if not isinstance(dst_fm.get("type"), str) or not dst_fm["type"].strip():
                                dst_fm["type"] = "post"

                        # ✅ vertical rule (sync branch too)
                        if lang not in VERTICAL_ALLOWED_LANGS:
                            dst_fm.pop("vertical", None)

                        dst_fm["draft"] = bool(draft)
                        dst_fm.setdefault("translationKey", tk)

                        # ✅ optional: batch-fix tags on existing translations via env var
                        if TAGS_SYNC:
                            new_tags = translate_tags(
                                client=client,
                                src_tags=fm.get("tags"),
                                tag_map=tag_map,
                                rev=tag_rev,
                                source_lang=src_lang,
                                target_lang=lang,
                                mode=mode,
                            )
                            if new_tags is not None:
                                dst_fm["tags"] = new_tags

                        # ⚠️ optional: force overwrite body for existing MT files
                        if FORCE_MT and dst_fm.get("kq_mt") is True and mode == "google":
                            try:
                                dst_body = translate_text_google(client, body, src_lang, lang)
                            except Exception as e:
                                print(f"[WARN] FORCE_MT body translate failed: {dst} -> {e}")

                        dst.write_text(dump_frontmatter(dst_fm) + dst_body, "utf-8")
                        synced += 1
                    else:
                        skipped_exists += 1

                    continue
                # ================================================================================

                # ===== create new translation =====
                dst.parent.mkdir(parents=True, exist_ok=True)
                target_fm = build_target_frontmatter(
                    src_fm=fm,
                    slug=slug,
                    tk=tk,
                    draft=draft,
                    mode=mode,
                    target_lang=lang,
                    rel=rel,
                )

                if mode == "google":
                    target_fm.setdefault("kq_mt_from", src_lang)
                    target_fm.setdefault("kq_mt_to", lang)

                # Only on FIRST creation: translate title (like body)
                new_title = translate_title_if_needed(client, fm, src_lang, lang, mode)
                if new_title:
                    target_fm["title"] = new_title

                # ✅ Only on FIRST creation: tags (map first, then MT fallback)
                new_tags = translate_tags(
                    client=client,
                    src_tags=fm.get("tags"),
                    tag_map=tag_map,
                    rev=tag_rev,
                    source_lang=src_lang,
                    target_lang=lang,
                    mode=mode,
                )
                if new_tags is not None:
                    target_fm["tags"] = new_tags

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
        "Done. "
        f"created={created}, synced={synced}, adopted={adopted}, "
        f"skipped_exists={skipped_exists}, updated_src={updated_src}, skipped_no_translate={skipped_no_translate}, "
        f"warned_unknown_mode={warned_unknown_mode}\n"
        f"(repo_root={REPO_ROOT})"
    )


if __name__ == "__main__":
    main()
