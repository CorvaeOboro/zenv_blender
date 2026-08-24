#region DOC
"""
ZENV Blender Addon Docs HTML Generator
--------------------------------------
Scans z_blender_*.py addon files under addon/ and generates a static HTML
documentation site under docs/ , styled after the reference pages in
dev/ref (iframe sidebar + per-page content, dark theme).

For each addon file the generator:
  - AST-parses the bl_info dict for project metadata
    (name, blender, category, version, description, status, approved,
     sort_priority, group, group_prefix, group_order, addon_order, tags,
     description_short, description_medium, description_long,
     image_overview, addon_image, location)
  - AST-parses bpy.props.*Property assignments inside PropertyGroup classes
    into a parameter table (name, description, default, min, max, subtype,
    enum items)
  - AST-parses ZENV_OT_* Operator classes (bl_idname, bl_label, bl_options)
  - looks up the image_overview screenshot under docs/ and embeds it when found

Addons in wip/ , removed/ , backup/ subfolders, with approved == False, or
with status == 'deprecated' are skipped and do not appear in the sidebar
or docs.

Output layout (docs/addons/ subfolder, images referenced as ../<img>):
  docs/addon_index.html      overview page (sidebar + welcome content)
  docs/zenv_menu.html        sidebar menu, grouped by bl_info group
  docs/addons/<slug>.html    one page per addon, iframe sidebar -> ../zenv_menu.html

Refresh policy:
  default               generate only MISSING addon pages (skip existing),
                         always regenerate menu + index so the sidebar stays current
  --refresh <a> <b> ... force-regenerate the listed addon pages (match by file
                         name, slug, or bl_info name) and refresh menu + index
  --all                 force-regenerate every addon page and refresh menu + index
  --menu-only           only regenerate the sidebar menu + index, leave addon pages
  --dry-run             report what would be written, write nothing

Usage:
  python dev/DEV_addon_docs_html_generator.py
  python dev/DEV_addon_docs_html_generator.py --refresh TEX_bake_ambient_occlusion_multi
  python dev/DEV_addon_docs_html_generator.py --all
  python dev/DEV_addon_docs_html_generator.py --menu-only
  python dev/DEV_addon_docs_html_generator.py --dry-run

VERSION::20260821
"""
#endregion

#region IMPORTS
from __future__ import annotations

import argparse
import ast
import html
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
#endregion


#region CONST
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
ADDON_DIR = os.path.join(REPO_ROOT, "addon")
DOCS_DIR = os.path.join(REPO_ROOT, "docs")
ADDONS_DOCS_DIR = os.path.join(DOCS_DIR, "addons")
MENU_FILE = os.path.join(DOCS_DIR, "zenv_menu.html")
INDEX_FILE = os.path.join(DOCS_DIR, "addon_index.html")

ADDON_FILE_PREFIX = "z_blender_"

# bl_info keys we care about (lowercased).
BI_NAME = "name"
BI_BLENDER = "blender"
BI_CATEGORY = "category"
BI_VERSION = "version"
BI_DESCRIPTION = "description"
BI_STATUS = "status"
BI_APPROVED = "approved"
BI_SORT_PRIORITY = "sort_priority"
BI_GROUP = "group"
BI_GROUP_PREFIX = "group_prefix"
BI_GROUP_ORDER = "group_order"
BI_ADDON_ORDER = "addon_order"
BI_TAGS = "tags"
BI_DESC_SHORT = "description_short"
BI_DESC_MEDIUM = "description_medium"
BI_DESC_LONG = "description_long"
BI_IMAGE = "image_overview"
BI_ADDON_IMAGE = "addon_image"
BI_LOCATION = "location"

# bpy.props property factory call names -> friendly type labels.
PROP_TYPE_MAP = {
    "IntProperty": "int",
    "FloatProperty": "float",
    "BoolProperty": "bool",
    "StringProperty": "string",
    "EnumProperty": "enum",
    "FloatVectorProperty": "float vector",
    "IntVectorProperty": "int vector",
    "BoolVectorProperty": "bool vector",
    "PointerProperty": "pointer",
    "CollectionProperty": "collection",
}

# CSS pulled from dev/ref/illumorae_docs_html_generator.py (dark theme),
# retuned for the ZENV project palette.
PAGE_CSS = """:root { --bg:#1a1a1a; --surface:#2d2d2d; --border:#404040; --text:#e0e0e0; --muted:#b0b0b0; --accent:#4a7ba7; --link:#64b5f6; --code:#1e1e1e; }
* { box-sizing:border-box; }
html,body { margin:0; height:100%; font-family:'Segoe UI',Tahoma,Geneva,Verdana,sans-serif; background:var(--bg); color:var(--text); line-height:1.6; }
.page { display:flex; height:100vh; }
.sidebar { width:14%; min-width:200px; border-right:1px solid var(--border); background:var(--bg); }
.sidebar iframe { width:100%; height:100%; border:none; }
.content { flex:1; overflow-y:auto; }
header { background:linear-gradient(90deg,#0a1520 0%,#1a1a1a 100%); border-bottom:2px solid var(--accent); padding:1.2rem 1rem; text-align:center; }
header h1 { margin:0; font-size:2rem; color:#fff; }
header p { margin:0.5rem 0 0; color:var(--muted); }
.container { max-width:1000px; margin:0 auto; padding:2rem 1.5rem; }
h2 { color:#fff; border-bottom:1px solid var(--border); padding-bottom:0.5rem; margin-top:2.5rem; font-size:1.4rem; }
h3 { color:#fff; margin-top:1.5rem; font-size:1.1rem; }
a { color:var(--link); text-decoration:none; }
a:hover { text-decoration:underline; }
ul,ol { padding-left:1.4rem; }
li { margin-bottom:0.4rem; }
table { width:100%; border-collapse:collapse; margin:1rem 0; font-size:0.95rem; }
th,td { border:1px solid var(--border); padding:0.5rem 0.7rem; text-align:left; vertical-align:top; }
th { background:var(--surface); color:#fff; }
td { background:#222; }
code,pre { background:var(--code); border:1px solid var(--border); border-radius:4px; font-family:Consolas,Monaco,'Courier New',monospace; font-size:0.9rem; }
code { padding:0.15rem 0.35rem; }
pre { padding:0.8rem; overflow-x:auto; white-space:pre-wrap; }
.note { border-left:3px solid var(--accent); background:var(--surface); padding:0.8rem 1rem; margin:1rem 0; border-radius:0 6px 6px 0; }
.meta-grid { display:grid; grid-template-columns:160px 1fr; gap:0.4rem 1rem; margin:1rem 0; font-size:0.95rem; }
.meta-grid dt { color:var(--muted); }
.meta-grid dd { margin:0; }
.badge { display:inline-block; padding:0.1rem 0.5rem; border-radius:10px; font-size:0.75rem; border:1px solid var(--border); background:var(--surface); color:var(--muted); margin:0.1rem; }
.badge.status-working { color:#b5d65a; border-color:#5a8a3a; }
.badge.status-stable { color:#b5d65a; border-color:#5a8a3a; }
.badge.status-wip { color:#d6b55a; border-color:#a79a5a; }
.badge.status-deprecated { color:#ff6b6b; border-color:#a75a5a; }
img.node-shot { width:100%; border:1px solid var(--border); border-radius:4px; margin:1rem 0; }
.img-missing { border:1px dashed var(--border); background:var(--surface); color:var(--muted); padding:2rem; text-align:center; border-radius:4px; margin:1rem 0; }
footer { text-align:center; padding:1.2rem 1rem; color:var(--muted); font-size:0.9rem; border-top:1px solid var(--border); margin-top:3rem; }"""

MENU_CSS = """body { background-color:#1a1a1a; font-family:Verdana,Arial,Helvetica,sans-serif; color:#b0b0b0; margin:0; padding:0; }
a:link, a:visited { color:#4a7ba7; text-decoration:none; display:block; padding:2px 0; font-weight:normal; }
a:hover { color:#7ab5e8; }
a:active { color:#4a7ba7; }
.menu-section { margin-top:0.6rem; }
.menu-section h3 { color:#ffffff; font-size:0.85rem; text-transform:uppercase; margin:0 0 0.2rem 0; padding-bottom:0.15rem; border-bottom:1px solid #404040; }
.menu-section a { font-size:0.85rem; padding:2px 0; }
.external { margin-top:1rem; padding-top:0.6rem; border-top:1px solid #404040; }"""
#endregion


#region MODELS
@dataclass
class PropParam:
    """One bpy.props.*Property definition parsed from a PropertyGroup class."""
    attr: str
    prop_kind: str  # factory name, e.g. "IntProperty"
    type: str       # friendly label, e.g. "int"
    name: str = ""
    description: str = ""
    default: Any = None
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    subtype: str = ""
    precision: Optional[int] = None
    enum_items: List[Tuple[str, str, str]] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OperatorInfo:
    """One ZENV_OT_* Operator class parsed from the addon source."""
    class_name: str
    bl_idname: str = ""
    bl_label: str = ""
    bl_description: str = ""
    bl_options: List[str] = field(default_factory=list)


@dataclass
class AddonDoc:
    file_name: str
    file_path: str
    rel_subfolder: str = "main"  # "main" | "wip" | "removed"

    bl_info: Dict[str, Any] = field(default_factory=dict)

    properties: List[PropParam] = field(default_factory=list)
    operators: List[OperatorInfo] = field(default_factory=list)

    image_filename: Optional[str] = None
    image_exists: bool = False

    # Representative addon image (e.g. "zenv_blender_MESH_helix.png").
    # Resolved from bl_info["addon_image"]; used in cards/rows as the
    # primary thumbnail when the overview screenshot is missing.
    addon_image_filename: Optional[str] = None
    addon_image_exists: bool = False

    # derived
    page_filename: str = ""
    page_rel_from_docs: str = ""  # path relative to docs/ (for menu links)

    # ---- bl_info accessors (with sane fallbacks) ----
    @property
    def name(self) -> str:
        v = self.bl_info.get(BI_NAME)
        return str(v).strip() if v else self._fallback_name()

    @property
    def description(self) -> str:
        v = self.bl_info.get(BI_DESCRIPTION)
        return str(v).strip() if v else ""

    @property
    def description_short(self) -> str:
        v = self.bl_info.get(BI_DESC_SHORT)
        return str(v).strip() if v else ""

    @property
    def description_medium(self) -> str:
        v = self.bl_info.get(BI_DESC_MEDIUM)
        return str(v).strip() if v else ""

    @property
    def description_long(self) -> str:
        v = self.bl_info.get(BI_DESC_LONG)
        return str(v).strip() if v else ""

    @property
    def version(self) -> str:
        v = self.bl_info.get(BI_VERSION)
        return str(v).strip() if v else ""

    @property
    def status(self) -> str:
        v = self.bl_info.get(BI_STATUS)
        return str(v).strip().lower() if v else ""

    @property
    def approved(self) -> bool:
        v = self.bl_info.get(BI_APPROVED)
        # Treat missing as approved (matches DEV_generate_website.py behavior).
        return bool(v) if v is not None else True

    @property
    def sort_priority(self) -> int:
        v = self.bl_info.get(BI_SORT_PRIORITY)
        try:
            return int(v) if v is not None else 999
        except (TypeError, ValueError):
            return 999

    @property
    def group_order(self) -> int:
        v = self.bl_info.get(BI_GROUP_ORDER)
        try:
            return int(v) if v is not None else 999
        except (TypeError, ValueError):
            return 999

    @property
    def addon_order(self) -> int:
        v = self.bl_info.get(BI_ADDON_ORDER)
        try:
            return int(v) if v is not None else 999
        except (TypeError, ValueError):
            return 999

    @property
    def group(self) -> str:
        v = self.bl_info.get(BI_GROUP)
        if v:
            return str(v).strip()
        # Fallback to group_prefix title-cased.
        p = self.group_prefix
        return p.title() if p and p != "OTHER" else "Other"

    @property
    def group_prefix(self) -> str:
        v = self.bl_info.get(BI_GROUP_PREFIX)
        if v:
            return str(v).strip().upper()
        # Fallback: extract from filename z_blender_PREFIX_name.py
        stem = self.file_name[len(ADDON_FILE_PREFIX):]
        parts = stem.split("_")
        return parts[0].upper() if parts and parts[0] else "OTHER"

    @property
    def tags(self) -> List[str]:
        v = self.bl_info.get(BI_TAGS)
        if isinstance(v, (list, tuple)):
            return [str(t) for t in v]
        return []

    @property
    def location(self) -> str:
        v = self.bl_info.get(BI_LOCATION)
        return str(v).strip() if v else ""

    @property
    def category(self) -> str:
        v = self.bl_info.get(BI_CATEGORY)
        return str(v).strip() if v else ""

    @property
    def blender(self) -> str:
        v = self.bl_info.get(BI_BLENDER)
        if isinstance(v, (list, tuple)):
            return ".".join(str(x) for x in v)
        return str(v).strip() if v else ""

    @property
    def image_declared(self) -> Optional[str]:
        v = self.bl_info.get(BI_IMAGE)
        return str(v).strip() if v else None

    @property
    def addon_image_declared(self) -> Optional[str]:
        v = self.bl_info.get(BI_ADDON_IMAGE)
        return str(v).strip() if v else None

    def _fallback_name(self) -> str:
        stem = self.file_name[len(ADDON_FILE_PREFIX):]
        stem = os.path.splitext(stem)[0]
        # Turn "TEX_bake_ambient_occlusion_multi" into "TEX Bake Ambient Occlusion Multi".
        return " ".join(part.capitalize() for part in stem.split("_") if part)
#endregion


#region PARSE
def _read_text_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _literal_value(node: ast.AST) -> Any:
    """Best-effort literal extraction (handles constants, lists, tuples, unary minus)."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant):
        v = node.operand.value
        return -v if isinstance(v, (int, float)) else v
    if isinstance(node, ast.List):
        return [_literal_value(e) for e in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_literal_value(e) for e in node.elts)
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        # e.g. bpy.types.Scene -> "bpy.types.Scene"
        parts = []
        cur = node
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
        return ".".join(reversed(parts))
    return None


def _const_str(node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _extract_bl_info(tree: ast.Module) -> Dict[str, Any]:
    """Extract the bl_info dict via ast.literal_eval (safe for literals)."""
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "bl_info":
                try:
                    value = ast.literal_eval(node.value)
                    if isinstance(value, dict):
                        return value
                except (ValueError, SyntaxError):
                    return {}
    return {}


def _parse_property_call(call: ast.Call) -> Optional[PropParam]:
    """Parse a `bpy.props.XxxProperty(...)` or bare `XxxProperty(...)` call node."""
    func = call.func
    factory_name: Optional[str] = None
    if isinstance(func, ast.Attribute):
        factory_name = func.attr
    elif isinstance(func, ast.Name):
        factory_name = func.id
    if not factory_name or factory_name not in PROP_TYPE_MAP:
        return None

    kwargs: Dict[str, Any] = {}
    for kw in call.keywords:
        if kw.arg is None:
            continue
        kwargs[kw.arg] = _literal_value(kw.value)

    enum_items: List[Tuple[str, str, str]] = []
    items_val = kwargs.get("items")
    if isinstance(items_val, (list, tuple)):
        for item in items_val:
            if isinstance(item, (list, tuple)) and len(item) >= 3:
                enum_items.append((str(item[0]), str(item[1]), str(item[2])))

    return PropParam(
        attr="",  # filled in by the caller (the annotated assignment target)
        prop_kind=factory_name,
        type=PROP_TYPE_MAP[factory_name],
        name=str(kwargs.get("name") or ""),
        description=str(kwargs.get("description") or ""),
        default=kwargs.get("default"),
        min=kwargs.get("min"),
        max=kwargs.get("max"),
        step=kwargs.get("step"),
        subtype=str(kwargs.get("subtype") or ""),
        precision=kwargs.get("precision"),
        enum_items=enum_items,
        extra={k: v for k, v in kwargs.items()
               if k not in {"name", "description", "default", "min", "max",
                            "step", "subtype", "precision", "items"}},
    )


def _parse_property_groups(tree: ast.Module) -> List[PropParam]:
    """Parse all bpy.props.*Property annotated assignments inside PropertyGroup
    subclasses (and any class whose name contains 'PG' or 'Properties')."""
    params: List[PropParam] = []
    for stmt in tree.body:
        if not isinstance(stmt, ast.ClassDef):
            continue
        # Heuristic: PropertyGroup subclasses. We accept any class that looks
        # like a property container (base id contains PropertyGroup / PG / Properties)
        # to stay robust across the project's naming styles.
        base_ids = []
        for base in stmt.bases:
            if isinstance(base, ast.Name):
                base_ids.append(base.id)
            elif isinstance(base, ast.Attribute):
                base_ids.append(base.attr)
        is_pg = any("PropertyGroup" in b or b.endswith("PG") or "Properties" in b
                    for b in base_ids)
        # Also accept classes named like ZENV_PG_* even without a recognizable base.
        if not is_pg and not re.search(r"(^|_)PG_|Properties", stmt.name):
            continue

        for body_stmt in stmt.body:
            if not isinstance(body_stmt, ast.AnnAssign):
                continue
            ann_assign = body_stmt
            if not isinstance(ann_assign.target, ast.Name):
                continue
            # Blender's PropertyGroup convention is `attr: XxxProperty(...)`,
            # i.e. the factory call is the ANNOTATION (value is None). Fall back
            # to the value for the rarer `attr: type = XxxProperty(...)` form.
            call_node = ann_assign.annotation
            if not isinstance(call_node, ast.Call):
                call_node = ann_assign.value
            if not isinstance(call_node, ast.Call):
                continue
            prop = _parse_property_call(call_node)
            if prop is None:
                continue
            prop.attr = ann_assign.target.id
            params.append(prop)
    return params


def _parse_operators(tree: ast.Module) -> List[OperatorInfo]:
    """Parse ZENV_OT_* Operator classes for bl_idname / bl_label / bl_options."""
    ops: List[OperatorInfo] = []
    for stmt in tree.body:
        if not isinstance(stmt, ast.ClassDef):
            continue
        base_ids = []
        for base in stmt.bases:
            if isinstance(base, ast.Name):
                base_ids.append(base.id)
            elif isinstance(base, ast.Attribute):
                base_ids.append(base.attr)
        is_op = any("Operator" in b for b in base_ids)
        if not is_op and not stmt.name.startswith("ZENV_OT_"):
            continue

        info = OperatorInfo(class_name=stmt.name)
        doc = ast.get_docstring(stmt, clean=False)
        if doc:
            info.bl_description = doc.strip()
        for body_stmt in stmt.body:
            if not isinstance(body_stmt, ast.Assign):
                continue
            for target in body_stmt.targets:
                if not isinstance(target, ast.Name):
                    continue
                if target.id == "bl_idname":
                    info.bl_idname = _const_str(body_stmt.value) or ""
                elif target.id == "bl_label":
                    info.bl_label = _const_str(body_stmt.value) or ""
                elif target.id == "bl_options":
                    val = _literal_value(body_stmt.value)
                    if isinstance(val, (list, tuple, set)):
                        info.bl_options = [str(x) for x in val]
        ops.append(info)
    return ops


def _parse_addon_source(source_text: str) -> Tuple[
    Dict[str, Any], List[PropParam], List[OperatorInfo],
]:
    """Return (bl_info, properties, operators)."""
    tree = ast.parse(source_text)
    bl_info = _extract_bl_info(tree)
    properties = _parse_property_groups(tree)
    operators = _parse_operators(tree)
    return bl_info, properties, operators
#endregion


#region SCAN
def _rel_subfolder(file_path: str, addon_dir: str) -> str:
    """Classify an addon file as main / wip / removed by its subfolder."""
    rel = os.path.relpath(file_path, addon_dir).replace("\\", "/")
    parts = rel.split("/")
    if len(parts) >= 2:
        top = parts[0].lower()
        if top == "wip":
            return "wip"
        if top == "removed":
            return "removed"
        if top == "backup":
            return "backup"
    return "main"


def _image_lookup(declared: Optional[str], file_name: str) -> Tuple[Optional[str], bool]:
    """Resolve the overview image. Returns (filename_relative_to_docs, exists)."""
    if declared:
        candidate = os.path.join(DOCS_DIR, declared)
        if os.path.isfile(candidate):
            return declared, True
        return declared, False

    # Fallback: guess from the file stem.
    stem = os.path.splitext(file_name)[0]
    guesses = [
        f"{stem}.png",
        f"{stem}.jpg",
        f"{stem}.jpeg",
        f"{stem}_overview.png",
        f"{stem}_overview.jpg",
    ]
    for g in guesses:
        if os.path.isfile(os.path.join(DOCS_DIR, g)):
            return g, True
    return None, False


def _page_filename_for(addon: AddonDoc) -> str:
    # Slug from the file stem (without extension), sanitized.
    stem = os.path.splitext(addon.file_name)[0]
    slug = re.sub(r"[^A-Za-z0-9_\-]", "_", stem)
    return f"{slug}.html"


def scan_addons(addon_dir: str) -> List[AddonDoc]:
    """Walk addon_dir for z_blender_*.py files and parse each into an AddonDoc."""
    excluded_dir_names = {
        "backup", "backups", "_backup", "bak", "old", "archive", "archives",
        "__pycache__", ".git", ".svn", ".hg", ".idea", ".vscode", ".venv",
        "venv", ".mypy_cache", ".pytest_cache", "node_modules", "dist", "build",
        "removed",
    }

    py_files: List[str] = []
    for root, dirs, files in os.walk(addon_dir):
        dirs[:] = [
            d for d in dirs
            if d.casefold() not in {x.casefold() for x in excluded_dir_names}
            and not d.startswith(".")
            and not d.casefold().startswith("backup")
            and not d.casefold().endswith("_backup")
        ]
        for f in files:
            if f.endswith(".py") and f.startswith(ADDON_FILE_PREFIX):
                py_files.append(os.path.join(root, f))

    addons: List[AddonDoc] = []
    for path in sorted(py_files):
        file_name = os.path.basename(path)
        subfolder = _rel_subfolder(path, addon_dir)

        try:
            src = _read_text_file(path)
        except OSError:
            continue

        try:
            bl_info, properties, operators = _parse_addon_source(src)
        except SyntaxError as e:
            print(f"WARNING: skipping unparseable {file_name}: {e}", file=sys.stderr)
            continue

        addon = AddonDoc(
            file_name=file_name,
            file_path=path,
            rel_subfolder=subfolder,
            bl_info=bl_info,
            properties=properties,
            operators=operators,
        )

        addon.image_filename, addon.image_exists = _image_lookup(addon.image_declared, file_name)
        # Resolve the representative addon_image (e.g. "zenv_blender_MESH_helix.png").
        # Unlike image_overview, there is no filename-guess fallback - the
        # field must be explicitly declared to be used.
        if addon.addon_image_declared:
            candidate = os.path.join(DOCS_DIR, addon.addon_image_declared)
            addon.addon_image_filename = addon.addon_image_declared
            addon.addon_image_exists = os.path.isfile(candidate)
        addon.page_filename = _page_filename_for(addon)
        addon.page_rel_from_docs = f"addons/{addon.page_filename}"

        # Skip rules: wip/removed/backup subfolders, unapproved, deprecated.
        if subfolder in {"wip", "removed", "backup"}:
            continue
        if not addon.approved:
            continue
        if addon.status == "deprecated":
            continue
        # Skip files with no bl_info at all (broken/missing module).
        if not bl_info:
            continue

        addons.append(addon)

    return addons
#endregion


#region HTML
def _esc(text: Any) -> str:
    return html.escape(str(text) if text is not None else "")


def _format_value(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, (list, tuple)):
        return ", ".join(_format_value(x) for x in v)
    return _esc(v)


def _status_badge(status: str) -> str:
    s = status.strip().lower()
    if not s:
        return ""
    cls = "badge"
    if s.startswith("work"):
        cls = "badge status-working"
    elif s.startswith("stable"):
        cls = "badge status-stable"
    elif s.startswith("wip") or s.startswith("exp") or s.startswith("draft"):
        cls = "badge status-wip"
    elif s.startswith("depr") or s.startswith("break") or s.startswith("bad") or s.startswith("fail"):
        cls = "badge status-deprecated"
    return f'<span class="{cls}">{_esc(status)}</span>'


def _desc_long_html(text: str) -> str:
    """Render description_long as a <pre> block (it is usually a multi-line guide)."""
    if not text:
        return ""
    return f"<pre>{_esc(text)}</pre>"


def render_addon_page(addon: AddonDoc) -> str:
    title = addon.name
    short = addon.description_short

    meta_rows: List[str] = []
    meta_rows.append(f"<dt>Addon File</dt><dd><code>{_esc(addon.file_name)}</code></dd>")
    if addon.category:
        meta_rows.append(f"<dt>Category</dt><dd><code>{_esc(addon.category)}</code></dd>")
    if addon.group:
        meta_rows.append(f"<dt>Group</dt><dd>{_esc(addon.group)} (<code>{_esc(addon.group_prefix)}</code>)</dd>")
    if addon.version:
        meta_rows.append(f"<dt>Version</dt><dd><code>{_esc(addon.version)}</code></dd>")
    if addon.blender:
        meta_rows.append(f"<dt>Blender</dt><dd><code>{_esc(addon.blender)}</code></dd>")
    if addon.status:
        meta_rows.append(f"<dt>Status</dt><dd>{_status_badge(addon.status)}</dd>")
    meta_rows.append(f"<dt>Approved</dt><dd>{'yes' if addon.approved else 'no'}</dd>")
    meta_rows.append(f"<dt>Group Order</dt><dd><code>{addon.group_order}</code></dd>")
    meta_rows.append(f"<dt>Addon Order</dt><dd><code>{addon.addon_order}</code></dd>")
    if addon.location:
        meta_rows.append(f"<dt>Location</dt><dd><code>{_esc(addon.location)}</code></dd>")
    if addon.tags:
        tag_badges = " ".join(f'<span class="badge">{_esc(t)}</span>' for t in addon.tags)
        meta_rows.append(f"<dt>Tags</dt><dd>{tag_badges}</dd>")

    # Image block: prefer image_overview, fall back to addon_image.
    if addon.image_filename and addon.image_exists:
        img_block = (
            f'<img class="node-shot" src="../{_esc(addon.image_filename)}" '
            f'alt="{_esc(title)}">'
        )
    elif addon.addon_image_filename and addon.addon_image_exists:
        img_block = (
            f'<img class="node-shot" src="../{_esc(addon.addon_image_filename)}" '
            f'alt="{_esc(title)}">'
        )
    elif addon.image_filename:
        img_block = (
            f'<div class="img-missing">Screenshot declared as '
            f"<code>{_esc(addon.image_filename)}</code> but not found under docs/.</div>"
        )
    else:
        img_block = '<div class="img-missing">No screenshot declared (image_overview field missing).</div>'

    # Description block: short (one-liner) + base description + medium + long.
    desc_block = ""
    if short:
        desc_block += f'<p class="note">{_esc(short)}</p>'
    if addon.description and addon.description != short:
        desc_block += f"<p>{_esc(addon.description)}</p>"
    if addon.description_medium and addon.description_medium not in (short, addon.description):
        desc_block += f"<p>{_esc(addon.description_medium)}</p>"
    long_html = _desc_long_html(addon.description_long)

    # Properties table.
    props_html = ""
    if addon.properties:
        rows: List[str] = []
        for p in addon.properties:
            default = "" if p.default is None else _format_value(p.default)
            min_v = "" if p.min is None else _format_value(p.min)
            max_v = "" if p.max is None else _format_value(p.max)
            step_v = "" if p.step is None else _format_value(p.step)
            range_cell = ""
            if min_v or max_v:
                range_cell = f"{min_v} .. {max_v}"
                if step_v:
                    range_cell += f" (step {step_v})"
            subtype_cell = f'<span class="badge">{_esc(p.subtype)}</span>' if p.subtype else ""
            extra_bits = " ".join(
                f'<span class="badge">{_esc(k)}={_format_value(v)}</span>'
                for k, v in p.extra.items()
            )
            rows.append(
                "<tr>"
                f"<td><code>{_esc(p.attr)}</code></td>"
                f"<td>{_esc(p.name) or _esc(p.attr)}</td>"
                f"<td>{_esc(p.type)}</td>"
                f"<td>{default}</td>"
                f"<td>{range_cell}</td>"
                f"<td>{subtype_cell} {extra_bits}</td>"
                f"<td>{_esc(p.description)}</td>"
                "</tr>"
            )
        props_html = (
            "<h2>Properties</h2>\n<table>\n"
            "<tr><th>Attr</th><th>Label</th><th>Type</th><th>Default</th>"
            "<th>Range</th><th>Subtype / Options</th><th>Description</th></tr>\n"
            + "\n".join(rows)
            + "\n</table>"
        )

        # Enum items expansion (one row per enum value).
        enum_blocks: List[str] = []
        for p in addon.properties:
            if not p.enum_items:
                continue
            enum_rows = []
            for ident, label, desc in p.enum_items:
                enum_rows.append(
                    "<tr>"
                    f"<td><code>{_esc(ident)}</code></td>"
                    f"<td>{_esc(label)}</td>"
                    f"<td>{_esc(desc)}</td>"
                    "</tr>"
                )
            enum_blocks.append(
                f"<h3>Enum: <code>{_esc(p.attr)}</code> ({_esc(p.name) or _esc(p.attr)})</h3>\n"
                "<table>\n<tr><th>Identifier</th><th>Label</th><th>Description</th></tr>\n"
                + "\n".join(enum_rows)
                + "\n</table>"
            )
        if enum_blocks:
            props_html += "\n<h2>Enum Items</h2>\n" + "\n".join(enum_blocks)
    else:
        props_html = '<h2>Properties</h2><p class="note">No bpy.props.*Property definitions parsed.</p>'

    # Operators table.
    ops_html = ""
    if addon.operators:
        rows_out: List[str] = []
        for op in addon.operators:
            options = " ".join(f'<span class="badge">{_esc(o)}</span>' for o in op.bl_options)
            rows_out.append(
                "<tr>"
                f"<td><code>{_esc(op.class_name)}</code></td>"
                f"<td><code>{_esc(op.bl_idname)}</code></td>"
                f"<td>{_esc(op.bl_label)}</td>"
                f"<td>{options}</td>"
                f"<td>{_esc(op.bl_description)}</td>"
                "</tr>"
            )
        ops_html = (
            "<h2>Operators</h2>\n<table>\n"
            "<tr><th>Class</th><th>bl_idname</th><th>Label</th><th>Options</th><th>Description</th></tr>\n"
            + "\n".join(rows_out)
            + "\n</table>"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ZENV - {_esc(title)}</title>
<style>
{PAGE_CSS}
</style>
</head>
<body>
<div class="page">
    <div class="sidebar"><iframe src="../zenv_menu.html"></iframe></div>
    <div class="content">
<header>
    <h1>{_esc(title)}</h1>
    <p>{_esc(short)}</p>
</header>
<div class="container">

{img_block}

<h2>Metadata</h2>
<dl class="meta-grid">
{chr(10).join(meta_rows)}
</dl>

{desc_block}

{long_html}

{props_html}

{ops_html}

</div>
    </div>
</div>
</body>
</html>
"""


def render_menu(addons: List[AddonDoc]) -> str:
    # Group addons by bl_info group; sort groups by min group_order then name;
    # addons within a group by addon_order then name.
    groups: Dict[str, List[AddonDoc]] = {}
    for a in addons:
        groups.setdefault(a.group, []).append(a)

    def group_sort_key(g: str) -> Tuple[int, str]:
        members = groups[g]
        order = min((m.group_order for m in members), default=999)
        return (order, g.lower())

    sections: List[str] = []
    for group in sorted(groups.keys(), key=group_sort_key):
        members = sorted(groups[group], key=lambda a: (a.addon_order, a.name.lower()))
        links = "\n".join(
            f'<a href="addons/{_esc(a.page_filename)}" target="_parent">{_esc(a.name)}</a>'
            for a in members
        )
        sections.append(
            f'<div class="menu-section">\n<h3>{_esc(group)}</h3>\n{links}\n</div>'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>ZENV Menu</title>
<style>
{MENU_CSS}
</style>
</head>
<body>
<center>
<br>
<h2 style="color:#ffffff; margin:0; font-size:1.1rem;">ZENV BLENDER ADDONS</h2>
<a href="addon_index.html" target="_parent">Overview</a>
{chr(10).join(sections)}
</center>
</body>
</html>
"""


def render_index(addons: List[AddonDoc]) -> str:
    total = len(addons)
    with_image = sum(1 for a in addons if a.image_exists)
    groups = sorted({a.group for a in addons}, key=lambda g: (
        min((a.group_order for a in addons if a.group == g), default=999), g.lower()
    ))

    group_rows: List[str] = []
    for g in groups:
        members = sorted([a for a in addons if a.group == g], key=lambda a: (a.addon_order, a.name.lower()))
        links = " | ".join(
            f'<a href="addons/{_esc(a.page_filename)}">{_esc(a.name)}</a>' for a in members
        )
        group_rows.append(f"<tr><td><strong>{_esc(g)}</strong></td><td>{links}</td></tr>")

    # Card sections grouped by group.
    card_sections: List[str] = []
    for g in groups:
        members = sorted([a for a in addons if a.group == g], key=lambda a: (a.addon_order, a.name.lower()))
        cards: List[str] = []
        for a in members:
            if a.image_filename and a.image_exists:
                img_html = (
                    f'<img class="card-img" src="{_esc(a.image_filename)}" '
                    f'alt="{_esc(a.name)}">'
                )
            elif a.addon_image_filename and a.addon_image_exists:
                img_html = (
                    f'<img class="card-img" src="{_esc(a.addon_image_filename)}" '
                    f'alt="{_esc(a.name)}">'
                )
            else:
                img_html = '<div class="card-img-missing">no screenshot</div>'
            desc = a.description_short or ""
            cards.append(
                f'<a class="node-card" href="addons/{_esc(a.page_filename)}">'
                f'{img_html}'
                f'<div class="card-body">'
                f'<div class="card-title">{_esc(a.name)}</div>'
                f'<div class="card-desc">{_esc(desc)}</div>'
                f'</div>'
                f'</a>'
            )
        card_sections.append(
            f'<div class="card-group">\n'
            f'<h3>{_esc(g)}</h3>\n'
            f'<div class="card-grid">\n'
            f'{chr(10).join(cards)}\n'
            f'</div>\n'
            f'</div>'
        )

    # Per-row table: title on the left, image + description on the right.
    row_sections: List[str] = []
    for g in groups:
        members = sorted([a for a in addons if a.group == g], key=lambda a: (a.addon_order, a.name.lower()))
        rows_html: List[str] = []
        for a in members:
            if a.image_filename and a.image_exists:
                media_html = (
                    f'<img class="row-img" src="{_esc(a.image_filename)}" '
                    f'alt="{_esc(a.name)}">'
                )
            elif a.addon_image_filename and a.addon_image_exists:
                media_html = (
                    f'<img class="row-img" src="{_esc(a.addon_image_filename)}" '
                    f'alt="{_esc(a.name)}">'
                )
            else:
                media_html = '<div class="row-img-missing">no screenshot</div>'
            desc = a.description_short or ""
            rows_html.append(
                "<tr>"
                f'<td class="row-title"><a href="addons/{_esc(a.page_filename)}">{_esc(a.name)}</a></td>'
                f'<td class="row-media">{media_html}<div class="row-desc">{_esc(desc)}</div></td>'
                "</tr>"
            )
        row_sections.append(
            f'<div class="row-group">\n'
            f'<h3>{_esc(g)}</h3>\n'
            f'<table class="row-table">\n'
            f'{chr(10).join(rows_html)}\n'
            f'</table>\n'
            f'</div>'
        )

    index_css = """
.node-card { display:flex; flex-direction:column; background:var(--surface); border:1px solid var(--border); border-radius:6px; overflow:hidden; text-decoration:none; color:inherit; transition:border-color 0.15s, transform 0.15s; }
.node-card:hover { border-color:#4a7ba7; transform:translateY(-2px); }
.card-img { width:100%; height:140px; object-fit:cover; display:block; background:#1a1a1a; }
.card-img-missing { width:100%; height:140px; display:flex; align-items:center; justify-content:center; color:var(--muted); font-size:0.8rem; background:#1a1a1a; border-bottom:1px solid var(--border); }
.card-body { padding:0.6rem 0.8rem; }
.card-title { color:#4a7ba7; font-size:0.9rem; font-weight:600; margin-bottom:0.2rem; }
.card-desc { color:var(--muted); font-size:0.78rem; line-height:1.3; }
.card-group { margin-top:2rem; }
.card-group h3 { color:#ffffff; font-size:0.95rem; text-transform:uppercase; margin:0 0 0.8rem 0; padding-bottom:0.3rem; border-bottom:1px solid var(--border); }
.card-grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(220px, 1fr)); gap:0.8rem; }
.row-group { margin-top:2.5rem; }
.row-group h3 { color:#ffffff; font-size:0.95rem; text-transform:uppercase; margin:0 0 0.8rem 0; padding-bottom:0.3rem; border-bottom:1px solid var(--border); }
.row-table { width:100%; border-collapse:collapse; table-layout:fixed; }
.row-table td { border:1px solid var(--border); padding:0.8rem; vertical-align:middle; background:#222; }
.row-title { width:180px; text-align:center; vertical-align:middle; font-weight:600; }
.row-title a { color:#4a7ba7; text-decoration:none; }
.row-title a:hover { text-decoration:underline; }
.row-media { text-align:center; }
.row-img { display:block; margin:0 auto; max-width:1000px; width:100%; height:auto; border:1px solid var(--border); border-radius:4px; }
.row-img-missing { max-width:1000px; width:100%; margin:0 auto; border:1px dashed var(--border); background:var(--surface); color:var(--muted); padding:2rem; text-align:center; border-radius:4px; }
.row-desc { color:var(--muted); font-size:0.85rem; margin-top:0.5rem; text-align:center; }
.banner-img { max-width:100%; height:auto; max-height:200px; display:block; margin:0 auto; }
.header-links { margin-top:0.8rem; font-size:1rem; }
.header-links a { color:var(--link); text-decoration:none; font-weight:600; }
.header-links a:hover { text-decoration:underline; }
"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ZENV Blender Addons - Overview</title>
<style>
{PAGE_CSS}
{index_css}
</style>
</head>
<body>
<div class="page">
    <div class="sidebar"><iframe src="zenv_menu.html"></iframe></div>
    <div class="content">
<header>
    <img class="banner-img" src="zenv_blender_header.jpg" alt="ZENV Blender Addons">
    <div class="header-links">
        <a href="https://github.com/CorvaeOboro/zenv">GITHUB</a>
    </div>
</header>
<div class="container">

<p>{total} addons documented, {with_image} with screenshots.</p>

<table>
{chr(10).join(group_rows)}
</table>

{chr(10).join(card_sections)}

{chr(10).join(row_sections)}

</div>
    </div>
</div>
</body>
</html>
"""
#endregion


#region WRITE
def _write_file(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _match_refresh(addon: AddonDoc, tokens: List[str]) -> bool:
    tokens_low = {t.lower() for t in tokens}
    stem = os.path.splitext(addon.file_name)[0].lower()
    # Strip the z_blender_ prefix for a shorter matching form.
    stem_short = stem[len(ADDON_FILE_PREFIX):] if stem.startswith(ADDON_FILE_PREFIX) else stem
    slug_low = addon.page_filename[:-5].lower()
    candidates = {
        addon.file_name.lower(),
        stem,
        stem_short,
        slug_low,
        addon.name.lower(),
    }
    # Also allow substring matching (token contained in stem / slug / name).
    for token in tokens_low:
        if token in candidates:
            return True
        if token and (token in stem or token in slug_low or token in addon.name.lower()):
            return True
    return False
#endregion


#region CLI
def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate static HTML docs for ZENV Blender addons."
    )
    parser.add_argument(
        "addon_dir",
        nargs="?",
        default=ADDON_DIR,
        help="Addon directory containing z_blender_*.py files (default: <repo>/addon).",
    )
    parser.add_argument(
        "--refresh",
        nargs="*",
        default=None,
        metavar="ADDON",
        help="Force-regenerate the listed addon pages (match file name, stem, slug, or bl_info name).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Force-regenerate every addon page.",
    )
    parser.add_argument(
        "--menu-only",
        action="store_true",
        help="Only regenerate the sidebar menu and index, leave addon pages untouched.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be written without writing any files.",
    )
    args = parser.parse_args(argv)

    addon_dir = os.path.abspath(args.addon_dir)
    if not os.path.isdir(addon_dir):
        print(f"ERROR: addon directory not found: {addon_dir}", file=sys.stderr)
        return 2

    addons = scan_addons(addon_dir)
    if not addons:
        print("No z_blender_*.py addons found.", file=sys.stderr)
        return 1

    addons.sort(key=lambda a: (a.group_order, a.addon_order, a.name.lower()))

    refresh_tokens = list(args.refresh) if args.refresh else []
    force_all = bool(args.all)
    menu_only = bool(args.menu_only)
    dry = bool(args.dry_run)

    written: List[str] = []
    skipped: List[str] = []

    # Menu + index are always regenerated (they must reflect the current addon set).
    menu_html = render_menu(addons)
    index_html = render_index(addons)
    if dry:
        print(f"[dry-run] would write {os.path.relpath(MENU_FILE, REPO_ROOT)}")
        print(f"[dry-run] would write {os.path.relpath(INDEX_FILE, REPO_ROOT)}")
    else:
        _write_file(MENU_FILE, menu_html)
        _write_file(INDEX_FILE, index_html)
        written.append(os.path.relpath(MENU_FILE, REPO_ROOT))
        written.append(os.path.relpath(INDEX_FILE, REPO_ROOT))

    if not menu_only:
        for addon in addons:
            page_path = os.path.join(ADDONS_DOCS_DIR, addon.page_filename)
            rel = os.path.relpath(page_path, REPO_ROOT)
            exists = os.path.isfile(page_path)

            should_write = force_all
            if not should_write and refresh_tokens:
                should_write = _match_refresh(addon, refresh_tokens)
            if not should_write and not exists:
                should_write = True

            if not should_write:
                skipped.append(rel)
                continue

            if dry:
                print(f"[dry-run] would write {rel}")
                continue

            _write_file(page_path, render_addon_page(addon))
            written.append(rel)

    print(f"Addons scanned : {len(addons)}")
    print(f"Files written  : {len(written)}")
    if written:
        for w in written:
            print(f"  + {w}")
    if skipped:
        print(f"Files skipped  : {len(skipped)} (already exist; use --refresh or --all to update)")
        for s in skipped[:20]:
            print(f"  - {s}")
        if len(skipped) > 20:
            print(f"  ... and {len(skipped) - 20} more")
    return 0
#endregion


if __name__ == "__main__":
    raise SystemExit(main())
