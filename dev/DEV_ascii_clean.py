"""
DEV_ascii_clean.py - Scan the BLENDER addon repository for disallowed
non-ASCII symbols (em-dashes, arrows, circled digits, warning signs, emojis,
smart quotes, etc.) and emit a Markdown report with optional auto-fix.

In addition to the curated DISALLOWED list of named characters, this tool
enforces a strict ASCII-only policy: ANY character with a code point above
U+007F is flagged as a violation. This catches all emojis (U+1F300-U+1FAFF),
CJK characters, Greek letters, mathematical symbols, and any other stray
unicode that the curated list might miss. Character names are resolved via
unicodedata.name() so the report identifies exactly what was found.

Adapted for the BLENDER addon project layout: default targets are the
addon/ scripts plus dev/, docs/, notes/, test/, batch/, and keymap/; output
is written under dev/ascii_clean_reports/.

Usage:
    python dev/DEV_ascii_clean.py
    python dev/DEV_ascii_clean.py --iterations
    python dev/DEV_ascii_clean.py --fix --apply
    python dev/DEV_ascii_clean.py --fix --fix-unknown --apply
    python dev/DEV_ascii_clean.py --filter .md
    python dev/DEV_ascii_clean.py --targets addon

Output structure (default):
    dev/ascii_clean_reports/ascii_clean_<YYYYMMDD_HHMMSS>.txt

With --iterations:
    dev/ascii_clean_reports/iterations/<DATE>/ascii_clean_report.md
    dev/ascii_clean_reports/iterations/<DATE>/summary.json

VERSION::20260821
"""

#region imports
 
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

#endregion

#region config
# Configuration: paths, file extensions, skip lists, DISALLOWED char table, fix replacements, escape regex
REPO_ROOT = Path(__file__).resolve().parent.parent

SCRIPT_DIR = Path(__file__).resolve().parent

DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "ascii_clean_reports"

DEFAULT_ITERATIONS_DIR = DEFAULT_OUTPUT_DIR / "iterations"

# Default scan targets relative to repo root. Glob patterns are expanded at
# the repo root, so "addon" matches the addon scripts directory. The primary
# content is addon/ (the z_blender_*.py scripts); dev/, docs/, notes/, test/,
# batch/, and keymap/ hold tooling, documentation, and supporting scripts.
DEFAULT_TARGETS = ["addon", "dev", "docs", "notes", "test", "batch", "keymap"]

def default_output_path() -> Path:
    """Return a datetime-prefixed output path under dev/ascii_clean_reports/."""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return DEFAULT_OUTPUT_DIR / f"ascii_clean_{timestamp}.txt"

# Extensions to audit as text files

TEXT_EXTENSIONS = {
    ".py", ".json", ".md", ".txt", ".yml", ".yaml", ".ini", ".xml",
    ".bat", ".cfg", ".conf", ".csv", ".html", ".toml", ".sh", ".ps1",
    ".js",
    ".editorconfig", ".gitignore", ".gitattributes",
}

# Directories to skip entirely (only non-source cache/build/venv/backup dirs;
# all actual project content is audited)

SKIP_DIR_NAMES = {
    ".git", "node_modules", ".venv", "venv", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".ruff_cache",
    # Backup / removed / staging dirs under addon/ and notes/ that hold
    # duplicated or superseded content, not primary project source.
    "backup", "removed", "wip",
    # Generated output dirs under notes/ (logs, reports, snapshots, staging).
    "logs", "reports", "snapshots", "one_staging",
    # Linter / validation output produced by dev/DEV_run_linters.py and
    # related tools; gitignored generated content, not prose.
    "linter_reports",
}

# Extra path globs to skip (matched against relative posix path)

SKIP_PATH_PATTERNS = {
    # Exclude self: this file contains the disallowed-char reference tables
    "dev/DEV_ascii_clean.py",
    # Exclude the reference tools under dev/ref/ (they contain literal
    # DISALLOWED character tables / unicode samples that self-trigger).
    "dev/ref/*",
    # Output folders produced by this tool itself
    "dev/ascii_clean_reports/*",
    # Exclude this tool's own output files (they contain \uXXXX escape
    # sequences in report content and would self-trigger violations)
    "dev/ascii_clean_reports/iterations/*",
    # Linter / validation output produced by dev/DEV_run_linters.py and
    # dev/DEV_blender_addon_compliance.py. These are gitignored generated
    # snapshots, not prose, and may contain serialized source diffs.
    "dev/linter_reports/*",
    # Generated addon compliance reports (text snapshots, not source).
    "addon/addon_compliance_report.txt",
    "notes/addon_compliance_report.txt",
}

# Characters that must never appear in source (with their unicode code points).

DISALLOWED: dict[str, str] = {
    "\u00a7": "SECTION SIGN",
    "\u00a9": "COPYRIGHT SIGN",
    "\u00b0": "DEGREE SIGN",
    "\u00b1": "PLUS-MINUS SIGN",
    "\u00b2": "SUPERSCRIPT TWO",
    "\u00b4": "ACUTE ACCENT (potential smart-quote variant)",
    "\u00b7": "MIDDLE DOT",
    "\u00d7": "MULTIPLICATION SIGN",
    "\u2010": "HYPHEN",
    "\u2013": "EN DASH",
    "\u2014": "EM DASH",
    "\u2018": "LEFT SINGLE QUOTATION MARK",
    "\u2019": "RIGHT SINGLE QUOTATION MARK",
    "\u201c": "LEFT DOUBLE QUOTATION MARK",
    "\u201d": "RIGHT DOUBLE QUOTATION MARK",
    "\u2022": "BULLET",
    "\u2026": "HORIZONTAL ELLIPSIS",
    "\u2190": "LEFT ARROW",
    "\u2192": "RIGHT ARROW",
    "\u2193": "DOWNWARDS ARROW",
    "\u21a9": "LEFT ARROW WITH HOOK",
    "\u21bb": "CLOCKWISE OPEN CIRCLE ARROW",
    "\u2208": "ELEMENT OF",
    "\u2248": "ALMOST EQUAL TO",
    "\u2460": "CIRCLED DIGIT ONE",
    "\u2461": "CIRCLED DIGIT TWO",
    "\u2462": "CIRCLED DIGIT THREE",
    "\u2463": "CIRCLED DIGIT FOUR",
    "\u2464": "CIRCLED DIGIT FIVE",
    "\u2465": "CIRCLED DIGIT SIX",
    "\u2500": "BOX DRAWINGS LIGHT HORIZONTAL",
    "\u2502": "BOX DRAWINGS LIGHT VERTICAL",
    "\u2514": "BOX DRAWINGS LIGHT UP AND RIGHT",
    "\u251c": "BOX DRAWINGS LIGHT VERTICAL AND RIGHT",
    "\u2588": "FULL BLOCK",
    "\u25a0": "BLACK SQUARE",
    "\u25b2": "BLACK UP-POINTING TRIANGLE",
    "\u25b6": "BLACK RIGHT-POINTING TRIANGLE",
    "\u25ba": "BLACK RIGHT-POINTING POINTER",
    "\u25bc": "BLACK DOWN-POINTING TRIANGLE",
    "\u25c4": "BLACK LEFT-POINTING POINTER",
    "\u25c6": "BLACK DIAMOND",
    "\u25cf": "BLACK CIRCLE",
    "\u2605": "BLACK STAR",
    "\u2610": "BALLOT BOX",
    "\u2611": "BALLOT BOX WITH CHECK",
    "\u26a0": "WARNING SIGN",
    "\u2705": "WHITE HEAVY CHECK MARK",
    "\u2713": "CHECK MARK",
    "\u2714": "HEAVY CHECK MARK",
    "\u2716": "HEAVY MULTIPLICATION X",
    "\u2717": "BALLOT X",
    "\u274c": "CROSS MARK",
    "\u279c": "HEAVY ROUND-TIPPED RIGHT ARROW",
    "\u27f6": "LONG RIGHT ARROW",
    "\u00a0": "NO-BREAK SPACE",
    "\u03c0": "GREEK SMALL LETTER PI",
    "\u2328": "KEYBOARD",
    "\u23ed": "BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR",
    "\u23ee": "BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR",
    "\u23f8": "DOUBLE VERTICAL BAR",
    "\ufe0f": "VARIATION SELECTOR-16",
    "\U0001f504": "CLOCKWISE RIGHTWARDS AND LEFTWARDS OPEN CIRCLE ARROWS",
    "\U0001f507": "SPEAKER WITH CANCELLATION STROKE",
    "\U0001f50a": "SPEAKER WITH THREE SOUND WAVES",
    "\U0001f4c1": "FILE FOLDER",
    "\U0001f4cb": "CLIPBOARD",
    "\U0001f3af": "DIRECT HIT",
    "\U0001f4cd": "ROUND PUSHPIN",
}

# Safe ASCII replacements used by --fix.

FIX_REPLACEMENTS: dict[str, str] = {
    "\u00a7": "(section)",
    "\u00a9": "(c)",
    "\u00b0": " deg",
    "\u00b1": "+/-",
    "\u00b2": "^2",
    "\u00b4": "'",
    "\u00b7": ".",
    "\u00d7": "x",
    "\u2010": "-",
    "\u2013": "-",
    "\u2014": "-",
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2022": "*",
    "\u2026": "...",
    "\u2190": "<-",
    "\u2192": "->",
    "\u2193": "v",
    "\u21a9": "<-",
    "\u21bb": "~>",
    "\u2208": "in",
    "\u2248": "~=",
    "\u2460": "(1)",
    "\u2461": "(2)",
    "\u2462": "(3)",
    "\u2463": "(4)",
    "\u2464": "(5)",
    "\u2465": "(6)",
    "\u2500": "-",
    "\u2502": "|",
    "\u2514": "\\",
    "\u251c": "|",
    "\u2588": "#",
    "\u25a0": "[#]",
    "\u25b2": "^",
    "\u25b6": ">",
    "\u25ba": ">",
    "\u25bc": "v",
    "\u25c4": "<",
    "\u25c6": "*",
    "\u25cf": "o",
    "\u2605": "*",
    "\u2610": "[ ]",
    "\u2611": "[x]",
    "\u26a0": "(!)",
    "\u2705": "[OK]",
    "\u2713": "[OK]",
    "\u2714": "[OK]",
    "\u2716": "[X]",
    "\u2717": "[X]",
    "\u274c": "[X]",
    "\u279c": "->",
    "\u27f6": "->",
    "\u00a0": " ",
    "\u03c0": "pi",
    "\u2328": "[kbd]",
    "\u23ed": ">>|",
    "\u23ee": "|<<",
    "\u23f8": "||",
    "\ufe0f": "",
    "\U0001f504": "",
    "\U0001f507": "[mute]",
    "\U0001f50a": "[sound]",
    "\U0001f4c1": "[folder]",
    "\U0001f4cb": "[list]",
    "\U0001f3af": "[target]",
    "\U0001f4cd": "[pin]",
}

# Also catch unicode escape sequences written as \uXXXX or \UXXXXXXXX in source.

ESCAPE_PATTERN = re.compile(r"\\u[0-9a-fA-F]{4}|\\U[0-9a-fA-F]{8}")

#endregion

#region model
# Data model: Violation and FileResult dataclasses
@dataclass
class Violation:
    rule_id: str
    line_num: int
    col: int
    char: str
    name: str
    snippet: str
    is_escape: bool = False


@dataclass
class FileResult:
    relpath: Path
    lines: int
    violations: list[Violation] = field(default_factory=list)

    @property
    def has_violations(self) -> bool:
        return len(self.violations) > 0

#endregion

#region scan
# File enumeration: skip rules, target traversal, file reading
def should_skip(relpath: Path) -> bool:
    """Return True if the file should be skipped."""
    posix = relpath.as_posix()
    parts = relpath.parts

    if any(part in SKIP_DIR_NAMES for part in parts):
        return True

    for pattern in SKIP_PATH_PATTERNS:
        if _glob_match(posix, pattern):
            return True

    return False

def _glob_match(path: str, pattern: str) -> bool:
    """Very simple glob matcher for * and ?."""
    regex = "^" + re.escape(pattern).replace(r"\*", ".*?").replace(r"\?", ".") + "$"
    return bool(re.match(regex, path))

def _expand_target(root: Path, target: str) -> list[Path]:
    """Resolve a target spec to concrete directories under root.

    Targets containing glob metacharacters (* or ?) are expanded against
    root; literal names are used as-is.
    """
    if any(ch in target for ch in "*?"):
        return sorted(p for p in root.glob(target) if p.is_dir())
    candidate = root / target
    return [candidate] if candidate.is_dir() else []

def iter_target_files(root: Path, targets: list[str]) -> Iterable[Path]:
    """Yield all audit-target files under the given target subdirectories,
    relative to root."""
    for target in targets:
        for target_dir in _expand_target(root, target):
            for p in target_dir.rglob("*"):
                if not p.is_file():
                    continue
                relpath = p.relative_to(root)
                if should_skip(relpath):
                    continue
                if relpath.suffix.lower() not in TEXT_EXTENSIONS:
                    continue
                yield relpath

def read_file_data(path: Path) -> tuple[str, list[str]] | None:
    """Return (text, lines_with_endings). None on failure."""
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8", errors="replace")
        return text, text.splitlines(keepends=True)
    except OSError:
        return None

#endregion

#region rules
# Detection rules: three-pass check (curated, escapes, catch-all) + snippet sanitizer
def check_file(relpath: Path, text: str, lines: list[str]) -> list[Violation]:
    """Check a single file for disallowed unicode symbols.

    Runs three passes per line:
      1. Curated DISALLOWED dict (named characters with known fix replacements)
      2. Unicode escape sequences \\uXXXX / \\UXXXXXXXX that map to non-ASCII
      3. Catch-all: any literal character with code point > U+007F not already
         caught by pass 1 (catches all emojis, CJK, Greek, etc.)
    """
    violations: list[Violation] = []

    for i, line in enumerate(lines, start=1):
        # Track columns already flagged by the curated list so the catch-all
        # does not double-report the same character.
        flagged_cols: set[int] = set()

        # 1) curated literal unicode characters
        for ch, name in DISALLOWED.items():
            idx = -1
            while True:
                idx = line.find(ch, idx + 1)
                if idx == -1:
                    break
                flagged_cols.add(idx)
                violations.append(Violation(
                    "disallowed_unicode_symbol",
                    i,
                    idx + 1,
                    ch,
                    name,
                    _snippet(line),
                    is_escape=False,
                ))

        # 2) unicode escape sequences \uXXXX or \UXXXXXXXX
        for m in ESCAPE_PATTERN.finditer(line):
            esc = m.group(0)
            try:
                cp = int(esc[2:], 16)
            except Exception:
                continue
            # Only flag escapes that map to non-ASCII code points
            if cp <= 0x7F:
                continue
            ch = chr(cp)
            name = DISALLOWED.get(ch) or unicodedata.name(ch, f"U+{cp:04X}")
            violations.append(Violation(
                "disallowed_unicode_escape",
                i,
                m.start() + 1,
                esc,
                name,
                _snippet(line),
                is_escape=True,
            ))

        # 3) catch-all: any literal non-ASCII character not already flagged
        for idx, ch in enumerate(line):
            if ord(ch) <= 0x7F:
                continue
            if idx in flagged_cols:
                continue
            name = unicodedata.name(ch, f"U+{ord(ch):04X}")
            violations.append(Violation(
                "non_ascii_character",
                i,
                idx + 1,
                ch,
                name,
                _snippet(line),
                is_escape=False,
            ))

    return violations

def _snippet(line: str, trim_to: int = 80) -> str:
    """Return a safe, ASCII-only, truncated snippet of a line.

    Non-ASCII characters are replaced with [U+XXXX] so the report itself
    stays ASCII-clean and can be displayed on any terminal encoding.
    """
    s = line.rstrip("\n").rstrip("\r")
    # Replace non-ASCII chars with [U+XXXX] for safe display
    s = "".join(
        ch if ord(ch) <= 0x7F else f"[U+{ord(ch):04X}]"
        for ch in s
    )
    if len(s) > trim_to:
        s = s[:trim_to] + "..."
    return s.replace("`", "'")

#endregion

#region fix
# Auto-fix: replace known chars, heuristically generate replacements for
# unknown non-ASCII, and optionally replace remaining with '?'

# Keyword-to-ASCII mapping used by _generate_replacement for math operators
# and other named symbols. Keys are matched as substrings of the unicode
# name (case-sensitive). Longer/more-specific keys are checked first.
_NAME_KEYWORD_MAP: list[tuple[str, str]] = [
    # --- set theory / logic ---
    ("FOR ALL", "all"),
    ("THERE DOES NOT EXIST", "nexists"),
    ("THERE EXISTS", "exists"),
    ("EMPTY SET", "{}"),
    ("NOT AN ELEMENT OF", "notin"),
    ("ELEMENT OF", "in"),
    ("CONTAINS AS MEMBER", "ni"),
    ("DOES NOT CONTAIN", "notni"),
    ("NOT A SUBSET OF", "notsubset"),
    ("NOT A SUPERSET OF", "notsuperset"),
    ("SUBSET OF OR EQUAL TO", "subseteq"),
    ("SUPERSET OF OR EQUAL TO", "superseteq"),
    ("SUBSET", "subset"),
    ("SUPERSET", "superset"),
    ("NEITHER A SUBSET", "notsubset"),
    ("NEITHER A SUPERSET", "notsuperset"),
    ("INTERSECTION", "intersect"),
    ("UNION", "union"),
    ("LOGICAL AND", "and"),
    ("LOGICAL OR", "or"),
    ("N-ARY LOGICAL AND", "and"),
    ("N-ARY LOGICAL OR", "or"),
    ("N-ARY INTERSECTION", "intersect"),
    ("N-ARY UNION", "union"),
    ("DOUBLE INTERSECTION", "intersect"),
    ("DOUBLE UNION", "union"),
    ("MULTISET UNION", "union"),
    ("MULTISET MULTIPLICATION", "msetmul"),
    ("MULTISET", "mset"),
    # --- calculus / operators ---
    ("PARTIAL DIFFERENTIAL", "d"),
    ("NABLA", "nabla"),
    ("N-ARY SUMMATION", "sum"),
    ("N-ARY PRODUCT", "prod"),
    ("SURFACE INTEGRAL", "sintegral"),
    ("VOLUME INTEGRAL", "vintegral"),
    ("CLOCKWISE CONTOUR INTEGRAL", "cwintegral"),
    ("ANTICLOCKWISE CONTOUR INTEGRAL", "ccwintegral"),
    ("CLOCKWISE INTEGRAL", "cwintegral"),
    ("CONTOUR INTEGRAL", "cintegral"),
    ("TRIPLE INTEGRAL", "iiintegral"),
    ("DOUBLE INTEGRAL", "iintegral"),
    ("INTEGRAL", "integral"),
    ("INTEGRAL EXTENSION", "integral"),
    ("TOP HALF INTEGRAL", "integral"),
    ("BOTTOM HALF INTEGRAL", "integral"),
    ("SQUARE ROOT", "sqrt"),
    ("CUBE ROOT", "cbrt"),
    ("FOURTH ROOT", "4thrt"),
    ("INFINITY", "inf"),
    ("PROPORTIONAL TO", "prop"),
    ("RATIO", ":"),
    ("PROPORTION", "::"),
    ("THEREFORE", "therefore"),
    ("BECAUSE", "because"),
    # --- comparison / equality ---
    ("NOT IDENTICAL TO", "!=="),
    ("IDENTICAL TO", "==="),
    ("NOT EQUAL TO", "!="),
    ("LESS-THAN OR EQUAL TO", "<="),
    ("GREATER-THAN OR EQUAL TO", ">="),
    ("LESS-THAN OR EQUIVALENT TO", "<~"),
    ("GREATER-THAN OR EQUIVALENT TO", ">~"),
    ("LESS-THAN OVER EQUAL TO", "<="),
    ("GREATER-THAN OVER EQUAL TO", ">="),
    ("MUCH LESS-THAN", "<<"),
    ("MUCH GREATER-THAN", ">>"),
    ("VERY MUCH LESS-THAN", "<<<"),
    ("VERY MUCH GREATER-THAN", ">>>"),
    ("NOT LESS-THAN", "!<"),
    ("NOT GREATER-THAN", "!>"),
    ("NOT ALMOST EQUAL TO", "!~="),
    ("ALMOST EQUAL OR EQUAL TO", "~="),
    ("APPROXIMATELY EQUAL TO", "~="),
    ("ASYMPTOTICALLY EQUAL TO", "~="),
    ("EQUIVALENT TO", "=="),
    ("NOT EQUIVALENT TO", "!=="),
    ("NOT TILDE", "!~"),
    ("TILDE OPERATOR", "~"),
    ("REVERSED TILDE", "~"),
    ("INVERTED LAZY S", "~"),
    ("TRIPLE TILDE", "~~~"),
    ("APPROACHES THE LIMIT", "->"),
    ("CORRESPONDS TO", "<->"),
    ("ESTIMATES", "~="),
    ("QUESTIONED EQUAL TO", "?="),
    ("EQUAL TO BY DEFINITION", ":="),
    ("COLON EQUALS", ":="),
    ("EQUALS COLON", "=:"),
    ("DELTA EQUAL TO", "delta="),
    ("STAR EQUALS", "*="),
    ("RING EQUAL TO", "o="),
    ("RING IN EQUAL TO", "o="),
    ("GEOMETRICALLY EQUAL TO", "=="),
    ("GEOMETRICALLY EQUIVALENT TO", "=="),
    ("DIFFERENCE BETWEEN", "-"),
    ("LESS-THAN", "<"),
    ("GREATER-THAN", ">"),
    ("EQUAL TO", "="),
    ("EQUAL AND PARALLEL TO", "=||"),
    # --- precedence / order ---
    ("DOES NOT PRECEDE OR EQUAL", "!<="),
    ("DOES NOT SUCCEED OR EQUAL", "!>="),
    ("PRECEDES OR EQUIVALENT TO", "<~"),
    ("SUCCEEDS OR EQUIVALENT TO", ">~"),
    ("PRECEDES OR EQUAL TO", "<="),
    ("SUCCEEDS OR EQUAL TO", ">="),
    ("DOES NOT PRECEDE", "!<"),
    ("DOES NOT SUCCEED", "!>"),
    ("PRECEDES UNDER RELATION", "<"),
    ("SUCCEEDS UNDER RELATION", ">"),
    ("PRECEDES", "<"),
    ("SUCCEEDS", ">"),
    # --- geometry ---
    ("RIGHT ANGLE WITH ARC", "rangle"),
    ("RIGHT ANGLE", "rangle"),
    ("MEASURED ANGLE", "mangle"),
    ("SPHERICAL ANGLE", "sangle"),
    ("ANGLE", "angle"),
    ("PERPENDICULAR", "perp"),
    ("UP TACK", "perp"),
    ("DOWN TACK", "top"),
    ("PARALLEL TO", "||"),
    ("NOT PARALLEL TO", "!||"),
    ("DIVIDES", "|"),
    ("DOES NOT DIVIDE", "!|"),
    ("RIGHT TRIANGLE", "rtri"),
    # --- operators ---
    ("MINUS-OR-PLUS SIGN", "-/+"),
    ("PLUS-MINUS SIGN", "+/-"),
    ("MINUS SIGN", "-"),
    ("DOT MINUS", "-"),
    ("DOT PLUS", "+"),
    ("MULTIPLICATION SIGN", "x"),
    ("DIVISION SIGN", "/"),
    ("ASTERISK OPERATOR", "*"),
    ("RING OPERATOR", "o"),
    ("DOT OPERATOR", "."),
    ("STAR OPERATOR", "*"),
    ("DIAMOND OPERATOR", "<>"),
    ("BOWTIE", "><"),
    ("DIVISION TIMES", "/x"),
    ("CIRCLED PLUS", "(+)"),
    ("CIRCLED MINUS", "(-)"),
    ("CIRCLED TIMES", "(x)"),
    ("CIRCLED DIVISION SLASH", "(/)"),
    ("CIRCLED DOT OPERATOR", "(.)"),
    ("CIRCLED RING OPERATOR", "(o)"),
    ("CIRCLED EQUALS", "(=)"),
    ("CIRCLED DASH", "(-)"),
    ("CIRCLED ASTERISK OPERATOR", "(*)"),
    ("SQUARED PLUS", "[+]"),
    ("SQUARED MINUS", "[-]"),
    ("SQUARED TIMES", "[x]"),
    ("SQUARED DOT OPERATOR", "[.]"),
    # --- turnstiles / proofs ---
    ("DOUBLE VERTICAL BAR DOUBLE RIGHT TURNSTILE", "||="),
    ("TRIPLE VERTICAL BAR RIGHT TURNSTILE", "|||-"),
    ("NEGATED DOUBLE VERTICAL BAR", "!||="),
    ("DOES NOT PROVE", "!|-"),
    ("DOES NOT FORCE", "!||-"),
    ("NOT TRUE", "!|="),
    ("RIGHT TACK", "|-"),
    ("LEFT TACK", "-|"),
    ("ASSERTION", "|-"),
    ("MODELS", "|="),
    ("TRUE", "|="),
    ("FORCES", "||-"),
    # --- logic gates ---
    ("XOR", "xor"),
    ("NAND", "nand"),
    ("NOR", "nor"),
    ("CURLY LOGICAL AND", "and"),
    ("CURLY LOGICAL OR", "or"),
    # --- groups / algebra ---
    ("NORMAL SUBGROUP OF OR EQUAL TO", "<="),
    ("CONTAINS AS NORMAL SUBGROUP OR EQUAL TO", ">="),
    ("NOT NORMAL SUBGROUP OF OR EQUAL TO", "!<="),
    ("DOES NOT CONTAIN AS NORMAL SUBGROUP OR EQUAL", "!>="),
    ("NOT NORMAL SUBGROUP OF", "!<"),
    ("DOES NOT CONTAIN AS NORMAL SUBGROUP", "!>"),
    ("NORMAL SUBGROUP OF", "<"),
    ("CONTAINS AS NORMAL SUBGROUP", ">"),
    ("LEFT SEMIDIRECT PRODUCT", "x|"),
    ("RIGHT SEMIDIRECT PRODUCT", "|x"),
    ("LEFT NORMAL FACTOR SEMIDIRECT PRODUCT", "x|"),
    ("RIGHT NORMAL FACTOR SEMIDIRECT PRODUCT", "|x"),
    ("MULTIMAP", "*>"),
    ("HERMITIAN CONJUGATE MATRIX", "H"),
    ("INTERCALATE", "X"),
    ("PITCHFORK", "|^"),
    # --- square image / original ---
    ("SQUARE IMAGE OF OR EQUAL TO", "<="),
    ("SQUARE ORIGINAL OF OR EQUAL TO", ">="),
    ("NOT SQUARE IMAGE OF OR EQUAL TO", "!<="),
    ("NOT SQUARE ORIGINAL OF OR EQUAL TO", "!>="),
    ("SQUARE IMAGE OF OR NOT EQUAL TO", "<!="),
    ("SQUARE ORIGINAL OF OR NOT EQUAL TO", ">!="),
    ("SQUARE IMAGE OF", "<"),
    ("SQUARE ORIGINAL OF", ">"),
    ("SQUARE CAP", "&"),
    ("SQUARE CUP", "|"),
    # --- ellipsis ---
    ("VERTICAL ELLIPSIS", ":"),
    ("MIDLINE HORIZONTAL ELLIPSIS", "..."),
    ("UP RIGHT DIAGONAL ELLIPSIS", "..."),
    ("DOWN RIGHT DIAGONAL ELLIPSIS", "..."),
    ("HORIZONTAL ELLIPSIS", "..."),
    # --- primes / daggers ---
    ("TRIPLE PRIME", "'''"),
    ("DOUBLE PRIME", "''"),
    ("PRIME", "'"),
    ("DOUBLE DAGGER", "++"),
    ("DAGGER", "+"),
    # --- punctuation ---
    ("SINGLE LEFT-POINTING ANGLE QUOTATION MARK", "<"),
    ("SINGLE RIGHT-POINTING ANGLE QUOTATION MARK", ">"),
    ("LEFT-POINTING ANGLE BRACKET", "<"),
    ("RIGHT-POINTING ANGLE BRACKET", ">"),
    ("DOUBLE LOW-9 QUOTATION MARK", '"'),
    ("SINGLE LOW-9 QUOTATION MARK", "'"),
    ("HORIZONTAL BAR", "-"),
    ("FIGURE DASH", "-"),
    ("NON-BREAKING HYPHEN", "-"),
    ("SOFT HYPHEN", ""),
    # --- subscripts / superscripts ---
    ("SUBSCRIPT ZERO", "_0"),
    ("SUBSCRIPT ONE", "_1"),
    ("SUBSCRIPT TWO", "_2"),
    ("SUBSCRIPT THREE", "_3"),
    ("SUBSCRIPT FOUR", "_4"),
    ("SUBSCRIPT FIVE", "_5"),
    ("SUBSCRIPT SIX", "_6"),
    ("SUBSCRIPT SEVEN", "_7"),
    ("SUBSCRIPT EIGHT", "_8"),
    ("SUBSCRIPT NINE", "_9"),
    ("SUPERSCRIPT ZERO", "^0"),
    ("SUPERSCRIPT ONE", "^1"),
    ("SUPERSCRIPT TWO", "^2"),
    ("SUPERSCRIPT THREE", "^3"),
    ("SUPERSCRIPT FOUR", "^4"),
    ("SUPERSCRIPT FIVE", "^5"),
    ("SUPERSCRIPT SIX", "^6"),
    ("SUPERSCRIPT SEVEN", "^7"),
    ("SUPERSCRIPT EIGHT", "^8"),
    ("SUPERSCRIPT NINE", "^9"),
    # --- units / letter-like symbols ---
    ("OHM SIGN", "ohm"),
    ("SCRIPT SMALL L", "l"),
    ("SCRIPT CAPITAL L", "L"),
    ("SCRIPT CAPITAL E", "E"),
    ("SCRIPT CAPITAL F", "F"),
    ("SCRIPT CAPITAL G", "G"),
    ("SCRIPT CAPITAL H", "H"),
    ("SCRIPT CAPITAL I", "I"),
    ("SCRIPT CAPITAL L", "L"),
    ("SCRIPT CAPITAL M", "M"),
    ("SCRIPT CAPITAL N", "N"),
    ("SCRIPT CAPITAL P", "P"),
    ("SCRIPT CAPITAL R", "R"),
    ("SCRIPT CAPITAL B", "B"),
    ("BLACK-LETTER CAPITAL I", "I"),
    ("BLACK-LETTER CAPITAL R", "R"),
    ("BLACK-LETTER CAPITAL Z", "Z"),
    ("BLACK-LETTER CAPITAL C", "C"),
    ("BLACK-LETTER CAPITAL H", "H"),
    ("DOUBLE-STRUCK CAPITAL C", "C"),
    ("DOUBLE-STRUCK CAPITAL N", "N"),
    ("DOUBLE-STRUCK CAPITAL Q", "Q"),
    ("DOUBLE-STRUCK CAPITAL R", "R"),
    ("DOUBLE-STRUCK CAPITAL Z", "Z"),
    ("DOUBLE-STRUCK CAPITAL P", "P"),
    ("DOUBLE-STRUCK CAPITAL H", "H"),
    ("DOUBLE-STRUCK SMALL N", "n"),
    ("DOUBLE-STRUCK SMALL p", "p"),
    ("DOUBLE-STRUCK SMALL z", "z"),
    # --- accents / modifiers ---
    ("MODIFIER LETTER CIRCUMFLEX ACCENT", "^"),
    ("SMALL TILDE", "~"),
    ("BREVE", "U"),
    ("DIAERESIS", ".."),
    ("DOUBLE ACUTE ACCENT", "''"),
    ("OGONEK", ""),
    ("MACRON", "-"),
    ("ACUTE ACCENT", "'"),
    ("GRAVE ACCENT", "`"),
    ("CARON", "v"),
    ("CEDILLA", ","),
    # --- Latin special ---
    ("LATIN SMALL LETTER DOTLESS I", "i"),
    ("LATIN CAPITAL LETTER ETH", "D"),
    ("LATIN SMALL LETTER ETH", "d"),
    ("LATIN CAPITAL LETTER THORN", "TH"),
    ("LATIN SMALL LETTER THORN", "th"),
    ("LATIN SMALL LETTER SHARP S", "ss"),
    ("LATIN CAPITAL LETTER AE", "AE"),
    ("LATIN SMALL LETTER AE", "ae"),
    ("LATIN CAPITAL LETTER O WITH STROKE", "O"),
    ("LATIN SMALL LETTER O WITH STROKE", "o"),
    ("LATIN CAPITAL LETTER L WITH STROKE", "L"),
    ("LATIN SMALL LETTER L WITH STROKE", "l"),
    ("LATIN CAPITAL LETTER D WITH STROKE", "D"),
    ("LATIN SMALL LETTER D WITH STROKE", "d"),
    # --- shapes ---
    ("WHITE CIRCLE", "o"),
    ("MEDIUM WHITE CIRCLE", "o"),
    ("LARGE CIRCLE", "o"),
    ("BLACK CIRCLE", "o"),
    ("WHITE SQUARE", "[]"),
    ("WHITE SQUARE WITH CENTRE VERTICAL LINE", "[|]"),
    ("WHITE SQUARE WITH ROUNDED CORNERS", "[]"),
    ("BLACK SQUARE", "[#]"),
    ("WHITE DIAMOND", "<>"),
    ("BLACK DIAMOND", "*"),
    ("LOZENGE", "<>"),
    ("SQUARE LOZENGE", "[]"),
    ("WHITE UP-POINTING TRIANGLE", "^"),
    ("BLACK UP-POINTING TRIANGLE", "^"),
    ("WHITE DOWN-POINTING TRIANGLE", "v"),
    ("BLACK DOWN-POINTING TRIANGLE", "v"),
    ("WHITE RIGHT-POINTING TRIANGLE", ">"),
    ("BLACK RIGHT-POINTING TRIANGLE", ">"),
    ("WHITE LEFT-POINTING TRIANGLE", "<"),
    ("BLACK LEFT-POINTING TRIANGLE", "<"),
    # --- misc technical ---
    ("REPLACEMENT CHARACTER", "?"),
    ("HOUSE", ""),
    ("WATCH", ""),
    ("HOURGLASS", ""),
    ("ENTER SYMBOL", "[enter]"),
    ("ALTERNATIVE KEY SYMBOL", "[alt]"),
    ("OPTION KEY", "[opt]"),
    ("INSERTION SYMBOL", "[ins]"),
    ("DELETE SYMBOL", "[del]"),
    ("ERASE TO THE RIGHT", "[del]"),
    ("ERASE TO THE LEFT", "[bs]"),
    ("X IN A RECTANGLE BOX", "[x]"),
    ("BELL SYMBOL", "[bell]"),
    ("PLACE OF INTEREST SIGN", "[poi]"),
    ("HELM SYMBOL", "[helm]"),
    ("UNDO SYMBOL", "[undo]"),
    ("CLEAR SCREEN SYMBOL", "[clr]"),
    ("PRINT SCREEN SYMBOL", "[prtsc]"),
    ("PREVIOUS PAGE", "[pgup]"),
    ("NEXT PAGE", "[pgdn]"),
    ("UP ARROWHEAD", "^"),
    ("DOWN ARROWHEAD", "v"),
    ("LEFT CEILING", "ceil"),
    ("RIGHT CEILING", "ceil"),
    ("LEFT FLOOR", "floor"),
    ("RIGHT FLOOR", "floor"),
    ("ARC", "("),
    ("SEGMENT", "("),
    ("SECTOR", "("),
    ("FROWN", ":("),
    ("SMILE", ":)"),
    ("DIAMETER SIGN", "dia"),
    ("ELECTRIC ARROW", "->"),
    ("PROJECTIVE", "proj"),
    ("PERSPECTIVE", "persp"),
    ("WAVY LINE", "~"),
    ("POSITION INDICATOR", "[pos]"),
    ("VIEWDATA SQUARE", "[]"),
    ("TURNED NOT SIGN", "!"),
    ("REVERSED NOT SIGN", "!"),
    ("NOT CHECK MARK", "[X]"),
    ("SHOULDERED OPEN BOX", "[]"),
    ("VERTICAL LINE WITH MIDDLE DOT", "|"),
    ("BROKEN CIRCLE WITH NORTHWEST ARROW", "[esc]"),
    ("CIRCLED HORIZONTAL BAR WITH NOTCH", "[?]"),
    ("CIRCLED TRIANGLE DOWN", "[v]"),
    ("BENZENE RING", "[benzene]"),
    ("CYLINDRICITY", "[cyl]"),
    ("ALL AROUND-PROFILE", "[allaround]"),
    ("SYMMETRY", "[sym]"),
    ("TOTAL RUNOUT", "[runout]"),
    ("DIMENSION ORIGIN", "[dim]"),
    ("CONICAL TAPER", "[taper]"),
    ("SLOPE", "[slope]"),
    ("COUNTERBORE", "[cbores]"),
    ("COUNTERSINK", "[csink]"),
    ("APL FUNCTIONAL SYMBOL QUAD", "[]"),
    ("APL FUNCTIONAL SYMBOL", "[apl]"),
    ("DIRECT CURRENT SYMBOL FORM TWO", "DC"),
    ("SOFTWARE-FUNCTION SYMBOL", "[fn]"),
    ("DECIMAL SEPARATOR KEY SYMBOL", "."),
    ("LEFT PARENTHESIS UPPER HOOK", "("),
    ("LEFT PARENTHESIS EXTENSION", "("),
    ("LEFT PARENTHESIS LOWER HOOK", "("),
    ("RIGHT PARENTHESIS UPPER HOOK", ")"),
    ("RIGHT PARENTHESIS EXTENSION", ")"),
    ("RIGHT PARENTHESIS LOWER HOOK", ")"),
    ("LEFT SQUARE BRACKET UPPER CORNER", "["),
    ("LEFT SQUARE BRACKET EXTENSION", "["),
    ("LEFT SQUARE BRACKET LOWER CORNER", "["),
    ("RIGHT SQUARE BRACKET UPPER CORNER", "]"),
    ("RIGHT SQUARE BRACKET EXTENSION", "]"),
    ("RIGHT SQUARE BRACKET LOWER CORNER", "]"),
    ("LEFT CURLY BRACKET UPPER HOOK", "{"),
    ("LEFT CURLY BRACKET MIDDLE PIECE", "{"),
    ("LEFT CURLY BRACKET LOWER HOOK", "{"),
    ("CURLY BRACKET EXTENSION", "|"),
    ("RIGHT CURLY BRACKET UPPER HOOK", "}"),
    ("RIGHT CURLY BRACKET MIDDLE PIECE", "}"),
    ("RIGHT CURLY BRACKET LOWER HOOK", "}"),
    ("INTEGRAL EXTENSION", "integral"),
    ("HORIZONTAL LINE EXTENSION", "-"),
    ("UPPER LEFT OR LOWER RIGHT CURLY BRACKET SECTION", "{"),
    ("UPPER RIGHT OR LOWER LEFT CURLY BRACKET SECTION", "}"),
    ("TOP LEFT CORNER", "+"),
    ("TOP RIGHT CORNER", "+"),
    ("BOTTOM LEFT CORNER", "+"),
    ("BOTTOM RIGHT CORNER", "+"),
    ("BOTTOM RIGHT CROP", "+"),
    ("BOTTOM LEFT CROP", "+"),
    ("TOP RIGHT CROP", "+"),
    ("TOP LEFT CROP", "+"),
    ("TELEPHONE RECORDER", ""),
    ("SQUARE LOZENGE", "[]"),
    # --- emoji (U+1F300+) ---
    ("ELECTRIC LIGHT BULB", ""),
    ("PARTY POPPER", ""),
    ("ROCKET", ""),
    ("WRENCH", ""),
    ("BAR CHART", ""),
    ("TEST TUBE", ""),
    ("SPARKLES", ""),
    ("LARGE ORANGE DIAMOND", "[diamond]"),
    ("LARGE BLUE DIAMOND", "[diamond]"),
    ("SMALL ORANGE DIAMOND", "[diamond]"),
    ("SMALL BLUE DIAMOND", "[diamond]"),
    ("CLOCKWISE RIGHTWARDS AND LEFTWARDS OPEN CIRCLE ARROWS", "[refresh]"),
    ("CLOCKWISE GAPPED CIRCLE ARROW", "[refresh]"),
    ("ANTICLOCKWISE GAPPED CIRCLE ARROWS", "[refresh]"),
    ("RIGHTWARDS ARROW WITH HOOK", "[reply]"),
    ("LEFTWARDS ARROW WITH HOOK", "[reply]"),
    ("BLACK RIGHTWARDS ARROW", "->"),
    ("HEAVY BLACK HEART", "[heart]"),
    ("WHITE HEART", "[heart]"),
    ("BLUE HEART", "[heart]"),
    ("GREEN HEART", "[heart]"),
    ("YELLOW HEART", "[heart]"),
    ("PURPLE HEART", "[heart]"),
    ("ORANGE HEART", "[heart]"),
    # --- misc emoji / symbols ---
    ("WHITE MEDIUM STAR", "*"),
    ("BLACK MEDIUM STAR", "*"),
    ("HIGH VOLTAGE SIGN", ""),
    ("PACKAGE", ""),
    ("PER MILLE SIGN", "%%"),
    ("PER TEN THOUSAND SIGN", "%%"),
    ("INTERROBANG", "?!"),
    ("MULTIPLICATION X", "x"),
    ("HEAVY MULTIPLICATION X", "x"),
    ("BALLOT X", "X"),
    ("EXCESS", "excess"),
    ("HOMOTHETIC", "homo"),
    ("EQUIANGULAR TO", "ang="),
    ("MEASURED BY", "measured by"),
    ("BETWEEN", "between"),
    ("ORIGINAL OF", "original of"),
    ("IMAGE OF", "image of"),
    ("Z NOTATION BAG MEMBERSHIP", "bag"),
    ("CONTAINS WITH LONG HORIZONTAL STROKE", "ni"),
    ("CONTAINS WITH VERTICAL BAR AT END", "ni"),
    ("SMALL CONTAINS WITH VERTICAL BAR", "ni"),
    ("CONTAINS WITH OVERBAR", "ni"),
    ("SMALL CONTAINS WITH OVERBAR", "ni"),
    ("SUMMATION TOP", "sum_top"),
    ("SUMMATION BOTTOM", "sum_bot"),
    ("TOP SQUARE BRACKET", "["),
    ("BOTTOM SQUARE BRACKET", "]"),
    ("BOTTOM SQUARE BRACKET OVER TOP SQUARE BRACKET", "[]"),
    ("RADICAL SYMBOL BOTTOM", "sqrt"),
    ("LEFT VERTICAL BOX LINE", "|"),
    ("RIGHT VERTICAL BOX LINE", "|"),
    ("HORIZONTAL SCAN LINE", "-"),
    ("DENTISTRY SYMBOL", "+"),
    ("SQUARE FOOT", "[sqft]"),
    ("RETURN SYMBOL", "[enter]"),
    ("EJECT SYMBOL", "[eject]"),
    ("VERTICAL LINE EXTENSION", "|"),
    ("METRICAL LONG OVER SHORT", "[long/short]"),
    ("METRICAL SHORT OVER LONG", "[short/long]"),
    ("METRICAL LONG OVER TWO SHORTS", "[long/2short]"),
    ("METRICAL TWO SHORTS OVER LONG", "[2short/long]"),
    ("METRICAL TWO SHORTS JOINED", "[2short]"),
    ("METRICAL TRISEME", "[tri]"),
    ("METRICAL TETRASEME", "[tetra]"),
    ("METRICAL PENTASEME", "[penta]"),
    ("EARTH GROUND", "[gnd]"),
    ("FUSE", "[fuse]"),
    ("TOP PARENTHESIS", "("),
    ("BOTTOM PARENTHESIS", ")"),
    ("TOP CURLY BRACKET", "{"),
    ("BOTTOM CURLY BRACKET", "}"),
    ("TOP TORTOISE SHELL BRACKET", "["),
    ("BOTTOM TORTOISE SHELL BRACKET", "]"),
    ("WHITE TRAPEZIUM", "[trap]"),
    ("STRAIGHTNESS", "[straight]"),
    ("FLATNESS", "[flat]"),
    ("AC CURRENT", "AC"),
    ("DECIMAL EXPONENT SYMBOL", "x10^"),
    ("ALARM CLOCK", "[alarm]"),
    ("TIMER CLOCK", "[timer]"),
    ("POWER SLEEP SYMBOL", "[sleep]"),
    ("POWER ON-OFF SYMBOL", "[power]"),
    ("POWER ON SYMBOL", "[power_on]"),
    ("POWER SYMBOL", "[power]"),
    ("OBSERVER EYE SYMBOL", "[eye]"),
    ("CONTINUOUS UNDERLINE SYMBOL", "_"),
    ("DISCONTINUOUS UNDERLINE SYMBOL", "_"),
    ("EMPHASIS SYMBOL", "_"),
    ("COMPOSITION SYMBOL", "[comp]"),
    ("MONOSTABLE SYMBOL", "[mono]"),
    ("HYSTERESIS SYMBOL", "[hyst]"),
    ("OPEN-CIRCUIT-OUTPUT", "[oc]"),
    ("PASSIVE-PULL-DOWN-OUTPUT", "[pd]"),
    ("PASSIVE-PULL-UP-OUTPUT", "[pu]"),
    # --- arrows (supplement) ---
    ("NORTH EAST ARROW", "NE"),
    ("SOUTH EAST ARROW", "SE"),
    ("NORTH WEST ARROW", "NW"),
    ("SOUTH WEST ARROW", "SW"),
    ("UPWARDS ARROW", "^"),
    ("LEFT RIGHT ARROW", "<->"),
    ("UP DOWN ARROW", "^v"),
    ("NORTH EAST WHITE ARROW", "NE"),
    ("SOUTH EAST WHITE ARROW", "SE"),
    ("NORTH WEST WHITE ARROW", "NW"),
    ("SOUTH WEST WHITE ARROW", "SW"),
    ("LEFTWARDS WHITE ARROW", "<-"),
    ("RIGHTWARDS WHITE ARROW", "->"),
    ("UPWARDS WHITE ARROW", "^"),
    ("DOWNWARDS WHITE ARROW", "v"),
    ("RIGHTWARDS DOUBLE ARROW", "=>"),
    ("LEFTWARDS DOUBLE ARROW", "<="),
    ("LEFT RIGHT DOUBLE ARROW", "<=>"),
    ("UPWARDS DOUBLE ARROW", "^^"),
    ("DOWNWARDS DOUBLE ARROW", "vv"),
    ("RIGHTWARDS ARROW FROM BAR", "|->"),
    ("LEFTWARDS ARROW FROM BAR", "<-|"),
    ("RIGHTWARDS ARROW WITH CORNER DOWNWARDS", "->"),
    ("RIGHTWARDS ARROW WITH TAIL", "->"),
    ("RIGHTWARDS ARROW WITH DOUBLE STROKE", "->"),
    ("LEFTWARDS ARROW WITH DOUBLE STROKE", "<-"),
    ("RIGHTWARDS WAVE ARROW", "~>"),
    ("LEFTWARDS WAVE ARROW", "<~"),
    ("RIGHTWARDS TWO HEADED ARROW", "->"),
    ("LEFTWARDS TWO HEADED ARROW", "<-"),
    ("RIGHTWARDS TRIPLE ARROW", ">>>"),
    ("LEFTWARDS TRIPLE ARROW", "<<<"),
    ("RIGHTWARDS SQUIGGLE ARROW", "~>"),
    ("LEFTWARDS SQUIGGLE ARROW", "<~"),
    ("RIGHTWARDS ARROW WITH VERTICAL STROKE", "->"),
    ("LEFTWARDS ARROW WITH VERTICAL STROKE", "<-"),
    ("RIGHTWARDS ARROW WITH DOUBLE VERTICAL STROKE", "->"),
    ("LEFTWARDS ARROW WITH DOUBLE VERTICAL STROKE", "<-"),
    ("RIGHTWARDS OPEN-HEADED ARROW", "->"),
    ("LEFTWARDS OPEN-HEADED ARROW", "<-"),
    ("UPWARDS OPEN-HEADED ARROW", "^"),
    ("DOWNWARDS OPEN-HEADED ARROW", "v"),
    ("LONG RIGHTWARDS ARROW", "->"),
    ("LONG LEFTWARDS ARROW", "<-"),
    ("LONG LEFT RIGHT ARROW", "<->"),
    ("LONG RIGHTWARDS DOUBLE ARROW", "=>"),
    ("LONG LEFTWARDS DOUBLE ARROW", "<="),
    ("LONG LEFT RIGHT DOUBLE ARROW", "<=>"),
]

# Greek letter name lookups for _generate_replacement.
_GREEK_LOWER = {
    0x03B1: "alpha", 0x03B2: "beta", 0x03B3: "gamma", 0x03B4: "delta",
    0x03B5: "epsilon", 0x03B6: "zeta", 0x03B7: "eta", 0x03B8: "theta",
    0x03B9: "iota", 0x03BA: "kappa", 0x03BB: "lambda", 0x03BC: "mu",
    0x03BD: "nu", 0x03BE: "xi", 0x03BF: "omicron", 0x03C0: "pi",
    0x03C1: "rho", 0x03C2: "sigma", 0x03C3: "sigma", 0x03C4: "tau",
    0x03C5: "upsilon", 0x03C6: "phi", 0x03C7: "chi", 0x03C8: "psi",
    0x03C9: "omega",
}
_GREEK_UPPER = {
    0x0391: "Alpha", 0x0392: "Beta", 0x0393: "Gamma", 0x0394: "Delta",
    0x0395: "Epsilon", 0x0396: "Zeta", 0x0397: "Eta", 0x0398: "Theta",
    0x0399: "Iota", 0x039A: "Kappa", 0x039B: "Lambda", 0x039C: "Mu",
    0x039D: "Nu", 0x039E: "Xi", 0x039F: "Omicron", 0x03A0: "Pi",
    0x03A1: "Rho", 0x03A3: "Sigma", 0x03A4: "Tau", 0x03A5: "Upsilon",
    0x03A6: "Phi", 0x03A7: "Chi", 0x03A8: "Psi", 0x03A9: "Omega",
}

# Coptic and some other letter-like blocks also map via name.
# Box-drawing characters: corners, tees, and crosses all become "+".
_BOX_CORNER_KEYWORDS = (
    "UP AND RIGHT", "UP AND LEFT", "DOWN AND RIGHT", "DOWN AND LEFT",
    "VERTICAL AND RIGHT", "VERTICAL AND LEFT", "VERTICAL AND HORIZONTAL",
    "DOWN AND HORIZONTAL", "UP AND HORIZONTAL",
    "UPPER LEFT OR LOWER RIGHT", "UPPER RIGHT OR LOWER LEFT",
)


def _generate_replacement(ch: str) -> str | None:
    """Heuristically generate a fitting ASCII replacement for a non-ASCII
    character. Returns None if no reasonable replacement can be produced.

    The heuristics, in priority order:
      1. NFKD decomposition to ASCII base letters (accents -> base)
      2. Greek letter code-point table (alpha, beta, Gamma, Omega, ...)
      3. Unicode-name keyword matching (math operators, shapes, arrows, ...)
      4. Box-drawing corner/tee/cross detection -> "+"
      5. Fallback: None (caller decides whether to use '?')
    """
    cp = ord(ch)

    # 1) NFKD decomposition: filter to ASCII parts. If non-empty, use it.
    #    Handles accented Latin (e + combining-acute -> e), ligatures
    #    (fi -> fi), circled digits (1 -> 1), etc. The combining marks
    #    are non-ASCII and are discarded, leaving the base letter.
    decomposed = unicodedata.normalize("NFKD", ch)
    ascii_parts = "".join(d for d in decomposed if ord(d) <= 0x7F)
    if ascii_parts:
        return ascii_parts

    # 2) Greek letters
    if cp in _GREEK_LOWER:
        return _GREEK_LOWER[cp]
    if cp in _GREEK_UPPER:
        return _GREEK_UPPER[cp]

    # 3) Unicode-name keyword matching
    name = unicodedata.name(ch, "")
    if name:
        for keyword, replacement in _NAME_KEYWORD_MAP:
            if keyword in name:
                return replacement

    # 4) Box-drawing corners, tees, and crosses -> "+"
    if name.startswith("BOX DRAWINGS") or name.startswith("LIGHT"):
        if any(kw in name for kw in _BOX_CORNER_KEYWORDS):
            return "+"
        if "HORIZONTAL" in name:
            return "-"
        if "VERTICAL" in name:
            return "|"
        if "DIAGONAL" in name:
            return "+"
        return "+"

    # 5) No reasonable replacement found
    return None


def fix_file(path: Path, fix_unknown: bool = False) -> bool:
    """Replace disallowed unicode symbols and escape sequences with safe ASCII.
    Returns True if the file was modified.

    Three replacement strategies, applied in order:
      1. Characters in FIX_REPLACEMENTS (explicit curated table)
      2. Characters with a heuristic replacement from _generate_replacement
         (Greek letters, math operators, accented Latin, shapes, etc.)
      3. When fix_unknown is True, any remaining non-ASCII char becomes '?'

    Escape sequences (\\uXXXX / \\UXXXXXXXX) are handled for all three
    strategies by resolving the code point and applying the same replacement.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False

    new_text = text

    # --- Pass 1: literal characters with known replacements ---
    for ch, repl in FIX_REPLACEMENTS.items():
        new_text = new_text.replace(ch, repl)

    # --- Pass 2: escape sequences for known replacements ---
    #    Process highest code points first so that supplementary-plane
    #    escapes (\U0001F4A1) are handled before BMP escapes that might
    #    be substrings of them.
    for ch, repl in sorted(FIX_REPLACEMENTS.items(), key=lambda kv: -ord(kv[0])):
        cp = ord(ch)
        if cp <= 0xFFFF:
            esc = f"\\u{cp:04x}"
        else:
            esc = f"\\U{cp:08x}"
        new_text = new_text.replace(esc, repl)
        if cp <= 0xFFFF:
            esc_upper = f"\\u{cp:04X}"
        else:
            esc_upper = f"\\U{cp:08X}"
        new_text = new_text.replace(esc_upper, repl)

    # --- Pass 3: heuristic replacements for remaining literal non-ASCII ---
    remaining_literals: dict[str, str] = {}
    for ch in new_text:
        if ord(ch) <= 0x7F:
            continue
        if ch in remaining_literals:
            continue
        if ch in FIX_REPLACEMENTS:
            continue  # already handled in pass 1
        gen = _generate_replacement(ch)
        if gen is not None:
            remaining_literals[ch] = gen
    for ch, repl in remaining_literals.items():
        new_text = new_text.replace(ch, repl)

    # --- Pass 4: heuristic replacements for remaining escape sequences ---
    #    Includes surrogate-pair detection: JSON encodes supplementary-plane
    #    characters as \udXXX\uXXXX pairs. Resolve the pair to the actual
    #    character before looking up a replacement.
    remaining_escapes: dict[str, str] = {}
    for m in ESCAPE_PATTERN.finditer(new_text):
        esc = m.group(0)
        if esc in remaining_escapes:
            continue
        try:
            cp = int(esc[2:], 16)
        except ValueError:
            continue
        if cp <= 0x7F:
            continue
        # Surrogate halves (U+D800-U+DFFF) are invalid standalone.
        # Check if the next escape sequence forms a surrogate pair.
        if 0xD800 <= cp <= 0xDBFF:
            # High surrogate; look for following low surrogate
            end = m.end()
            if end + 6 <= len(new_text) and new_text[end:end + 2] == "\\u":
                low_esc = new_text[end:end + 6]
                try:
                    low_cp = int(low_esc[2:], 16)
                except ValueError:
                    low_cp = -1
                if 0xDC00 <= low_cp <= 0xDFFF:
                    full_cp = 0x10000 + ((cp - 0xD800) << 10) + (low_cp - 0xDC00)
                    ch = chr(full_cp)
                    pair = esc + low_esc
                    if ch in FIX_REPLACEMENTS:
                        continue  # already handled in pass 2
                    gen = _generate_replacement(ch)
                    if gen is not None:
                        remaining_escapes[pair] = gen
                    continue
            # Lone high surrogate; no replacement possible
            continue
        if 0xDC00 <= cp <= 0xDFFF:
            # Lone low surrogate; skip (should have been caught as part of
            # a pair above)
            continue
        ch = chr(cp)
        if ch in FIX_REPLACEMENTS:
            continue  # already handled in pass 2
        gen = _generate_replacement(ch)
        if gen is not None:
            remaining_escapes[esc] = gen
    for esc, repl in remaining_escapes.items():
        new_text = new_text.replace(esc, repl)

    # --- Pass 5: catch-all '?' for anything still non-ASCII ---
    if fix_unknown:
        new_text = "".join(
            ch if ord(ch) <= 0x7F else "?"
            for ch in new_text
        )

    if new_text != text:
        path.write_text(new_text, encoding="utf-8")
        return True
    return False

#endregion

#region report
# Output generation: Markdown report rendering and JSON summary
def _safe_display(ch: str) -> str:
    """Return an ASCII-safe representation of a character for report display."""
    if ch.startswith("\\"):
        return ch  # already an escape sequence string like \uXXXX
    if ord(ch) <= 0x7F:
        return ch
    return f"U+{ord(ch):04X}"

def render_markdown(results: list[FileResult]) -> str:
    out: list[str] = []

    total_files = len(results)
    files_with_violations = sum(1 for r in results if r.has_violations)
    total_violations = sum(len(r.violations) for r in results)
    fixable_violations = sum(
        1 for r in results for v in r.violations
        if v.char in FIX_REPLACEMENTS
    )
    unfixable_violations = total_violations - fixable_violations

    # Aggregate by character + name so escape sequences get correct names
    char_counts: dict[str, int] = {}
    char_names: dict[str, str] = {}
    for r in results:
        for v in r.violations:
            char_counts[v.char] = char_counts.get(v.char, 0) + 1
            if v.char not in char_names:
                char_names[v.char] = v.name

    out.append("# ASCII-Clean Audit Report")
    out.append("")
    out.append(f"- **Repo root:** `{REPO_ROOT}`")
    out.append(f"- **Generated:** {datetime.datetime.now().isoformat()}")
    out.append("")

    out.append("## Summary")
    out.append("")
    out.append("| Metric | Count |")
    out.append("|---|---|")
    out.append(f"| Files scanned | {total_files} |")
    out.append(f"| Files with violations | {files_with_violations} |")
    out.append(f"| Total violations | {total_violations} |")
    out.append(f"| Fixable (known replacement) | {fixable_violations} |")
    out.append(f"| Unfixable (use --fix-unknown for '?') | {unfixable_violations} |")
    out.append("")

    out.append("## Violations by Symbol")
    out.append("")
    out.append("| Symbol | Name | Count | Fixable |")
    out.append("|---|---|---:|---|")
    for ch, count in sorted(char_counts.items(), key=lambda kv: -kv[1]):
        name = char_names.get(ch, "UNKNOWN")
        display = _safe_display(ch)
        fixable = "yes" if ch in FIX_REPLACEMENTS else "no"
        out.append(f"| `{display}` | {name} | {count} | {fixable} |")
    out.append("")

    out.append("## Details")
    out.append("")

    for r in sorted(results, key=lambda x: x.relpath.as_posix().lower()):
        if not r.has_violations:
            continue

        out.append(f"### `{r.relpath.as_posix()}` ({r.lines} lines)")
        out.append("")
        out.append("| Line | Col | Rule | Symbol | Name | Snippet |")
        out.append("|---:|---:|---|---|---|---|")
        for v in r.violations:
            kind = "escape" if v.is_escape else "literal"
            display = _safe_display(v.char)
            snippet = v.snippet.replace("|", "\\|")
            out.append(
                f"| {v.line_num} | {v.col} | {v.rule_id} | `{display}` ({kind}) | {v.name} | `{snippet}` |"
            )
        out.append("")

    if not any(r.has_violations for r in results):
        out.append("*No disallowed unicode symbols found.*")
        out.append("")

    return "\n".join(out) + "\n"

def build_summary(results: list[FileResult]) -> dict:
    total_files = len(results)
    files_with_violations = sum(1 for r in results if r.has_violations)
    total_violations = sum(len(r.violations) for r in results)

    char_counts: dict[str, int] = {}
    for r in results:
        for v in r.violations:
            char_counts[v.char] = char_counts.get(v.char, 0) + 1

    file_map: dict[str, list[dict]] = {}
    for r in results:
        if r.violations:
            file_map[r.relpath.as_posix()] = [
                {
                    "rule": v.rule_id,
                    "line": v.line_num,
                    "col": v.col,
                    "char": v.char,
                    "name": v.name,
                    "snippet": v.snippet,
                    "is_escape": v.is_escape,
                }
                for v in r.violations
            ]

    return {
        "generated": datetime.datetime.now().isoformat(),
        "total_files": total_files,
        "files_with_violations": files_with_violations,
        "total_violations": total_violations,
        "symbol_counts": char_counts,
        "violations_by_file": file_map,
    }

#endregion

#region iter
# Iteration folder helper: dated output directory resolution
def resolve_iteration_dir(base: Path, name: str | None) -> Path:
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    if name:
        candidate = base / name
    else:
        candidate = base / today
        if candidate.exists():
            i = 1
            while (base / f"{today}_{i}").exists():
                i += 1
            candidate = base / f"{today}_{i}"
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate

#endregion

#region cli
# CLI: argument parser definition
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", type=Path, default=None,
                   help="Output path (default: dev/ascii_clean_reports/ascii_clean_<YYYYMMDD_HHMMSS>.txt)")
    p.add_argument("--targets", nargs="+", default=DEFAULT_TARGETS,
                   help=f"Subdirectories to scan relative to repo root. Glob patterns supported "
                        f"(e.g. addon). Default: {DEFAULT_TARGETS}")
    p.add_argument("--iterations", action="store_true",
                   help="Write output to a dated iteration folder instead of --out")
    p.add_argument("--iterations-dir", type=Path, default=DEFAULT_ITERATIONS_DIR,
                   help=f"Base directory for dated iterations (default: {DEFAULT_ITERATIONS_DIR})")
    p.add_argument("--name", default=None,
                   help="Iteration folder name (default: today's date)")
    p.add_argument("--filter", default=None,
                   help="Only audit paths containing this substring (case-insensitive)")
    p.add_argument("--fix", action="store_true",
                   help="Replace disallowed symbols with safe ASCII equivalents")
    p.add_argument("--fix-unknown", action="store_true",
                   help="Also replace unknown non-ASCII chars (not in the fix table) with '?'. "
                        "Requires --fix --apply to take effect.")
    p.add_argument("--apply", action="store_true",
                   help="Actually perform --fix replacements. Without this, only prints planned actions.")
    return p.parse_args()

#endregion

#region main
# Entry point: scan/fix/write workflow and exit code
def main() -> int:
    args = parse_args()

    out_path = args.out if args.out else default_output_path()

    results: list[FileResult] = []
    targets_str = ", ".join(args.targets)
    print(f"[info] Scanning {REPO_ROOT} (targets: {targets_str}) ...")

    for relpath in iter_target_files(REPO_ROOT, args.targets):
        posix = relpath.as_posix()
        if args.filter and args.filter.lower() not in posix.lower():
            continue

        data = read_file_data(REPO_ROOT / relpath)
        if data is None:
            continue

        text, lines = data
        violations = check_file(relpath, text, lines)
        results.append(FileResult(relpath, len(lines), violations))

    print(f"[info] Scanned {len(results)} file(s).")

    # Fix mode
    if args.fix:
        fixable = [r for r in results if r.has_violations]
        print(f"[info] {len(fixable)} file(s) contain disallowed symbols.")
        if args.fix_unknown:
            print("[info] --fix-unknown: unknown non-ASCII chars will be replaced with '?'.")
        if not args.apply:
            print("[dry-run] Would fix the following files:")
            for r in fixable:
                print(f"  - {r.relpath.as_posix()} ({len(r.violations)} violation(s))")
            print("[dry-run] Re-run with --apply to perform the replacements.")
        else:
            fixed_count = 0
            print("[apply] Fixing files...")
            for r in fixable:
                full_path = REPO_ROOT / r.relpath
                if fix_file(full_path, fix_unknown=args.fix_unknown):
                    print(f"  [fixed] {r.relpath.as_posix()}")
                    fixed_count += 1
            print(f"[apply] {fixed_count} file(s) modified.")
            # Re-scan after fix
            print("[info] Re-scanning after fix...")
            results = []
            for relpath in iter_target_files(REPO_ROOT, args.targets):
                posix = relpath.as_posix()
                if args.filter and args.filter.lower() not in posix.lower():
                    continue
                data = read_file_data(REPO_ROOT / relpath)
                if data is None:
                    continue
                text, lines = data
                violations = check_file(relpath, text, lines)
                results.append(FileResult(relpath, len(lines), violations))
            print(f"[info] Re-scanned {len(results)} file(s).")

    md = render_markdown(results)
    summary = build_summary(results)

    if args.iterations:
        iter_dir = resolve_iteration_dir(args.iterations_dir, args.name)
        md_path = iter_dir / "ascii_clean_report.md"
        json_path = iter_dir / "summary.json"
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(md, encoding="utf-8")
        json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"[info] Wrote {md_path}")
        print(f"[info] Wrote {json_path}")
    else:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(md, encoding="utf-8")
        print(f"[info] Wrote {out_path}")

    total_violations = sum(len(r.violations) for r in results)
    if total_violations:
        print(f"[warn] {total_violations} disallowed symbol violation(s) found.")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

#endregion
