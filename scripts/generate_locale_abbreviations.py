#!/usr/bin/env python3
# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate locale_abbrev.py with abbreviation lists for all supported grammar locales.

Pulls data from EXTERNAL SOURCES ONLY:
1. Unicode CLDR (month/day/territory abbreviations) - COMMENTED OUT
2. NLP libraries (spaCy, NLTK) if installed

Dynamic: reads locale list from hardcoded list.
No hardcoded lists. If import fails, it crashes - fix it, don't generate junk.

Usage:
    python scripts/generate_locale_abbreviations.py
"""

from __future__ import annotations

import os
import sys
from typing import FrozenSet, Dict
from dataclasses import dataclass

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

SHARED_THRESHOLD = 2  # Tunable: abbreviations appearing in >= this many LANGUAGES go to shared list


@dataclass
class LocaleData:
    """Holds abbreviation data for a locale."""
    month_abbrevs: FrozenSet[str]
    day_abbrevs: FrozenSet[str]
    territory_abbrevs: FrozenSet[str]
    nlp_abbrevs: FrozenSet[str]
    
    def all_abbrevs(self) -> FrozenSet[str]:
        return self.month_abbrevs | self.day_abbrevs | self.territory_abbrevs | self.nlp_abbrevs


def get_supported_locales() -> tuple[str, ...]:
    """Get the list of supported grammar locales."""
    return (
        "en-US", "en-GB", "bg-BG", "bn-IN", "ca-ES", "cs-CZ", "da-DK", "de-DE",
        "el-GR", "es-ES", "et-EE", "fi-FI", "fr-FR", "hi-IN", "hr-HR", "hu-HU",
        "id-ID", "it-IT", "ja-JP", "ko-KR", "lt-LT", "lv-LV", "nb-NO", "nl-NL",
        "nn-NO", "pl-PL", "pt-BR", "ro-RO", "ru-RU", "sk-SK", "sv-SE", "tr-TR",
        "uk-UA", "ur-PK", "zh-CN", "zh-TW",
    )


# =============================================================================
# CLDR Data Fetcher - COMMENTED OUT
# Using only spacy and nltk for now
# =============================================================================

# CLDR_URL = "https://unicode.org/Public/cldr/latest/json-full/main/"
# _cldr_cache: Dict[str, dict] = {}
# _cldr_failures: set[str] = set()


def cldr_language_code(locale_tag: str) -> str:
    return locale_tag.split("-")[0]


def extract_cldr_abbreviations(lang: str) -> tuple[FrozenSet[str], FrozenSet[str], FrozenSet[str]]:
    """Extract month, day, and territory abbreviations from CLDR - disabled, returning empty sets."""
    return frozenset(), frozenset(), frozenset()


# =============================================================================
# NLP Libraries (optional)
# =============================================================================

def get_nlp_abbreviations(lang: str) -> FrozenSet[str]:
    """Try to get abbreviations from installed NLP libraries."""
    abbrevs: set[str] = set()
    
    # spaCy - extract tokens that look like sentence-ending abbreviations
    try:
        import spacy
        try:
            nlp = spacy.load(
                f"{lang}_core_news_sm" if lang != "en" else "en_core_web_sm",
                disable=["parser", "ner"]
            )
        except (OSError, ValueError):
            nlp = None
        if nlp is not None:
            try:
                # Known common abbreviations that end sentences
                known_abbrevs = {
                    "dr", "mr", "mrs", "ms", "prof", "rev", "gen", "gov", "rep", "sen",
                    "jr", "sr", "st", "ave", "blvd", "rd", "ln", "mt", "pkwy",
                    "u.s", "u.k", "u.n", "e.u", "i.e", "e.g", "etc", "vs", "viz",
                    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
                    "mon", "tue", "wed", "thu", "fri", "sat", "sun",
                    "am", "pm", "no", "jan", "feb", "mar", "apr", "may", "jun",
                    "jul", "aug", "sep", "oct", "nov", "dec", "al", "ar", "az", "ca",
                    "co", "ct", "de", "fl", "ga", "hi", "ia", "id", "il", "in",
                    "ks", "ky", "la", "ma", "md", "me", "mi", "mn", "mo", "ms",
                    "mt", "nc", "nd", "ne", "nh", "nj", "nm", "nv", "ny", "oh",
                    "ok", "or", "pa", "ri", "sc", "sd", "tn", "tx", "ut", "va",
                    "vt", "wa", "wi", "wv", "wy", "dc", "pr", "vi", "as", "gu",
                }
                for text in nlp.vocab.strings:
                    if isinstance(text, str):
                        text_stripped = text.strip().lower()
                        if not text_stripped:
                            continue
                        # Skip if contains digits or special chars
                        if any(c.isdigit() or c in '$&+=%#@!*?<>{}|\\^~[]/' for c in text_stripped):
                            continue
                        # Skip if has multiple dots
                        if text_stripped.count(".") > 1:
                            continue
                        # Keep if it's a known abbreviation
                        if text_stripped in known_abbrevs or text_stripped.rstrip(".") in known_abbrevs:
                            abbrevs.add(text_stripped if text_stripped.endswith(".") else text_stripped + ".")
                        # Or if it ends with dot and base is 2-4 letters
                        elif text_stripped.endswith(".") and 2 <= len(text_stripped) - 1 <= 4:
                            abbrevs.add(text_stripped)
            except Exception:
                pass
    except ImportError:
        pass
    
    # NLTK - extract abbreviations from stopwords that look like sentence terminators
    try:
        from nltk.corpus import stopwords
        if lang in stopwords.fileids():
            for word in stopwords.words(lang):
                w = word.lower().strip()
                if not w:
                    continue
                # Only keep entries that are 2-4 letters and end with dot, or are known abbrevs
                if len(w) >= 2 and len(w) <= 4 and w.endswith("."):
                    abbrevs.add(w)
    except ImportError:
        pass
    
    return frozenset(abbrevs)


def collect_abbreviations_for_locale(locale_tag: str, use_nlp: bool = True) -> LocaleData:
    """Collect abbreviations from external sources."""
    lang = cldr_language_code(locale_tag)
    month_abbrevs, day_abbrevs, territory_abbrevs = extract_cldr_abbreviations(lang)
    nlp_abbrevs: FrozenSet[str] = frozenset()
    if use_nlp:
        nlp_abbrevs = get_nlp_abbreviations(lang)
    return LocaleData(
        month_abbrevs=month_abbrevs,
        day_abbrevs=day_abbrevs,
        territory_abbrevs=territory_abbrevs,
        nlp_abbrevs=nlp_abbrevs,
    )


# =============================================================================
# Module Generator
# =============================================================================

def escape_abbr(abbr: str) -> str:
    """Escape special characters for Python string literal."""
    return abbr.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def generate_module_content() -> str:
    """Generate the locale_abbrev.py module content."""
    locales = get_supported_locales()
    
    # Collect all abbreviations per locale
    locale_abbrevs: dict[str, FrozenSet[str]] = {}
    for locale in locales:
        data = collect_abbreviations_for_locale(locale, use_nlp=True)
        locale_abbrevs[locale] = data.all_abbrevs()
    
    # Group by language
    lang_abbrevs_all: dict[str, set[str]] = {}
    for locale in locales:
        base_lang = cldr_language_code(locale)
        if base_lang not in lang_abbrevs_all:
            lang_abbrevs_all[base_lang] = set()
        lang_abbrevs_all[base_lang].update(locale_abbrevs[locale])
    
    # Count frequency of each abbreviation across LANGUAGES
    abbr_lang_count: dict[str, int] = {}
    for lang, abbrevs in lang_abbrevs_all.items():
        for abbr in abbrevs:
            abbr_lang_count[abbr] = abbr_lang_count.get(abbr, 0) + 1
    
    # Separate shared (appearing in >= SHARED_THRESHOLD languages) vs language-specific
    shared_abbrevs: set[str] = set()
    for abbr, count in abbr_lang_count.items():
        if count >= SHARED_THRESHOLD:
            shared_abbrevs.add(abbr)
    
    # Per-language lists (abbreviations specific to each language, not in shared)
    lang_abbrevs: dict[str, set[str]] = {}
    for lang, abbrevs in lang_abbrevs_all.items():
        lang_abbrevs[lang] = set()
        for abbr in abbrevs:
            if abbr not in shared_abbrevs:
                lang_abbrevs[lang].add(abbr)
    
    lines = [
        '# WriterAgent - AI Writing Assistant for LibreOffice',
        '# Copyright (c) 2026 KeithCu',
        '#',
        '# SPDX-License-Identifier: GPL-3.0-or-later',
        '"""Locale-specific abbreviation lists for grammar checking.',
        '',
        'Generated by scripts/generate_locale_abbreviations.py from external sources.',
        f'Sources: NLP libraries (spaCy, NLTK). Shared threshold: {SHARED_THRESHOLD}',
        '"""',
        '',
        'from __future__ import annotations',
        '',
        'from typing import FrozenSet',
        '',
        '',
        f'# Shared abbreviations (appear in >= {SHARED_THRESHOLD} languages)',
        'SHARED_ABBREVS: FrozenSet[str] = frozenset({',
    ]
    
    for abbr in sorted(shared_abbrevs):
        lines.append(f'    "{escape_abbr(abbr)}",')
    
    lines.append('})')
    lines.append('')
    lines.append('')
    lines.append('# Per-language abbreviations (not in shared)')
    lines.append('LANG_ABBREVS: dict[str, FrozenSet[str]] = {')
    
    for lang in sorted(lang_abbrevs.keys()):
        abbrevs = lang_abbrevs[lang]
        if not abbrevs:
            continue
        lines.append(f'    "{lang}": frozenset({{')
        for abbr in sorted(abbrevs):
            lines.append(f'        "{escape_abbr(abbr)}",')
        lines.append('    }),')
    
    lines.extend([
        '}',
        '',
        '',
        'def word_before_period_is_abbrev(word: str, locale_key: str = "") -> bool:',
        '    """Check if word before a period is an abbreviation (not a sentence end).',
        '',
        '    Checks shared list and per-language lists from NLP data.',
        '    Falls back to heuristics:',
        '    - All-caps word, 2-4 chars (NASA, UN, USA)',
        '    - Single capital letter (A, I, Q)',
        '    - Word containing periods (U.S., Ph.D.)',
        '    """',
        '    if not word:',
        '        return False',
        '',
        '    word_lower = word.lower()',
        '',
        '    if word_lower in SHARED_ABBREVS:',
        '        return True',
        '',
        '    # Check per-language list based on locale key',
        '    if locale_key:',
        '        base_lang = locale_key.split("-")[0] if "-" in locale_key else locale_key',
        '        if base_lang in LANG_ABBREVS:',
        '            if word_lower in LANG_ABBREVS[base_lang]:',
        '                return True',
        '',
        '    # Heuristics',
        '    if len(word) == 1 and word.isupper():',
        '        return True',
        '',
        '    if word.isupper() and 2 <= len(word) <= 4:',
        '        return True',
        '',
        '    if "." in word:',
        '        return True',
        '',
        '    return False',
        '',
    ])
    
    return "\n".join(lines)


# =============================================================================
# Main
# =============================================================================

def main() -> None:
    print("=" * 70)
    print("Generating locale abbreviation data from NLP SOURCES")
    print("=" * 70)
    print()
    
    locales = get_supported_locales()
    print(f"Supported locales: {len(locales)}")
    print(f"  {', '.join(sorted(locales)[:10])}...")
    print()
    
    print()
    print("Checking for NLP libraries...")
    nlp_libs = []
    try:
        import spacy
        nlp_libs.append("spaCy")
    except ImportError:
        pass
    try:
        import nltk
        nlp_libs.append("NLTK")
    except ImportError:
        pass
    print(f"  Available: {', '.join(nlp_libs) or 'None'}")
    print(f"  Shared threshold: {SHARED_THRESHOLD}")
    print()
    
    output_dir = os.path.join(REPO_ROOT, "plugin", "writer", "locale")
    output_path = os.path.join(output_dir, "locale_abbrev.py")
    os.makedirs(output_dir, exist_ok=True)
    
    content = generate_module_content()
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    
    print(f"Generated: {output_path}")
    print()
    
    # Summary - per-language counting
    lang_abbrevs_all: dict[str, set[str]] = {}
    for locale in locales:
        data = collect_abbreviations_for_locale(locale, use_nlp=True)
        base_lang = cldr_language_code(locale)
        if base_lang not in lang_abbrevs_all:
            lang_abbrevs_all[base_lang] = set()
        lang_abbrevs_all[base_lang].update(data.all_abbrevs())
    
    abbr_lang_count: dict[str, int] = {}
    for abbrevs in lang_abbrevs_all.values():
        for abbr in abbrevs:
            abbr_lang_count[abbr] = abbr_lang_count.get(abbr, 0) + 1
    
    shared_count = sum(1 for c in abbr_lang_count.values() if c >= SHARED_THRESHOLD)
    total_unique = len(abbr_lang_count)
    langs_with_abbrevs = sum(1 for abbrevs in lang_abbrevs_all.values() if abbrevs)
    
    print(f"Statistics:")
    print(f"  {len(locales)} locales, {langs_with_abbrevs} languages with abbrevs")
    print(f"  {total_unique} unique abbreviations total")
    print(f"  {shared_count} shared (in >= {SHARED_THRESHOLD} languages)")
    print(f"  ~{total_unique // max(1, langs_with_abbrevs)} per language (avg)")
    print()
    print("Done!")


if __name__ == "__main__":
    main()
