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

SRC_LANG = "en"
CONTENT_ROOT = Path("content")
SRC_ROOT = CONTENT_ROOT / SRC_LANG

CACHE_FILE = Path(".cache/mt_cache.json")  # 可选缓存（额外保险）
FRONT_DELIM = "---"


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def split_frontmatter(md: str) -> Tuple[Optional[str], str]:
    """
    Only supports YAML frontmatter: --- ... ---
    """
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

    # bundle: content/en/posts/xxx/index.md -> slug=xxx
    if src_path.name.lower() == "index.md":
        return src_path.parent.name

    # normal file: xxx.md -> xxx
    return src_path.stem


def get_rel_under_src(src_path: Path) -> Path:
    return src_path.relative_to(SRC_ROOT)


def ensure_translation_key(fm: Dict[str, Any], slug: str) -> Tuple[Dict[str, Any], bool, str]:
    """
    If missing translationKey, set to slug and return (fm, changed, translationKey)
    """
    tk = fm.get("translationKey")
    if isinstance(tk, str) and tk.strip():
        return fm, False, tk.strip()

    fm["translationKey"] = slug
    return fm, True, slug


def build_target_frontmatter(
    src_fm: Dict[str, Any],
    target_lang: str,
    slug: str,
    tk: str,
    draft: bool,
    mode: str,
) -> Dict[str, Any]:
    fm = dict(src_fm)
    fm.pop("translate", None)

    fm["translationKey"] = tk
    fm.setdefault("slug", slug)        # 不覆盖你手动改的中文 slug
    fm["draft"] = bool(draft)

    # 脚本接管标记（只要这个为 true，脚本就只同步 frontmatter，不动正文）
    fm["kq_managed"] = True

    # 机器翻译标记：google = true；stub = false
    # 注意：这里用 setdefault，允许你之后手动把 kq_mt 改成 false 并保持不被脚本改回去
    fm.setdefault("kq_mt", (mode == "google"))

    return fm



def translate_text_google(client: translate.Client, text: str, target_lang: str) -> str:
    res = client.translate(text, target_language=target_lang, format_="text")
    return res["translatedText"]


def main() -> None:
    sa_json = os.environ.get("GCP_SA_KEY_JSON")
    if not sa_json:
        raise SystemExit("Missing env: GCP_SA_KEY_JSON (service account JSON)")

    creds = service_account.Credentials.from_service_account_info(json.loads(sa_json))
    client = translate.Client(credentials=creds)

    cache = load_cache()
    created = 0
    synced = 0
    skipped_exists = 0
    updated_src = 0
    skipped_no_translate = 0

    for src in SRC_ROOT.rglob("*.md"):
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

        targets = tcfg.get("targets") or ["zh"]
        if isinstance(targets, str):
            targets = [targets]
        targets = [str(x).strip() for x in targets if str(x).strip()]

        draft = tcfg.get("draft")
        if draft is None:
            draft = True
        draft = bool(draft)

        slug = derive_slug(src, fm)

        # Ensure translationKey backwrite to EN
        fm, changed, tk = ensure_translation_key(fm, slug)
        if changed:
            src.write_text(dump_frontmatter(fm) + body, "utf-8")
            updated_src += 1

        # Optional cache key (extra safety)
        cache_key = str(src)
        cache[cache_key] = sha256(fm_raw + "\n\n" + body)

        rel = get_rel_under_src(src)

        for lang in targets:
            dst = CONTENT_ROOT / lang / rel

            # ===== 方案C：存在则只同步 frontmatter，不动正文 =====
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

                if dst_fm.get("kq_managed") is True:
                    # 1) draft 同步（发布/下线开关）
                    dst_fm["draft"] = bool(draft)

                    # 2) translationKey 保底同步
                    dst_fm.setdefault("translationKey", tk)

                    # 3) 机器翻译阶段才强制 noindex + mt
                    if dst_fm.get("kq_mt") is True:
                        dst_fm["robotsNoIndex"] = True
                        params = dst_fm.get("params")
                        if not isinstance(params, dict):
                            params = {}
                        params["mt"] = True
                        params.setdefault("mt_source", "google")
                        dst_fm["params"] = params

                    dst.write_text(dump_frontmatter(dst_fm) + dst_body, "utf-8")
                    synced += 1
                else:
                    skipped_exists += 1

                continue
            # =====================================================

            dst.parent.mkdir(parents=True, exist_ok=True)
            target_fm = build_target_frontmatter(fm, lang, slug, tk, draft, mode)

            if mode == "stub":
                out_body = (
                    "<!-- TODO: translate manually -->\n\n"
                    f"> Source: /{SRC_LANG}/{rel.as_posix().replace('index.md','')}\n"
                )
                out = dump_frontmatter(target_fm) + out_body
            else:
                zh_body = translate_text_google(client, body, lang)
                out = dump_frontmatter(target_fm) + zh_body

            dst.write_text(out, "utf-8")
            created += 1

    save_cache(cache)
    print(
        f"Done. created={created}, synced={synced}, skipped_exists={skipped_exists}, "
        f"updated_src={updated_src}, skipped_no_translate={skipped_no_translate}"
    )


if __name__ == "__main__":
    main()
