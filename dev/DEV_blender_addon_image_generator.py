"""
DEV Blender Addon Image Generator - Treemap Visualization Edition

Generates wide PNG images of the Code Treemap Visualzation of the Addons
useful to at glance review the structure for any anomalies or misplaced functions
based on favored blender addon coding practices.

Overview:
1. searches the `/addon/` directory for Python addon files.
2. Extracts the category and name from each addon's filename or code.
3. Code Analysis with Compliance Checking = Parses addon code using AST to extract classes, functions, and their relationships.
    - Identifies global functions (register/unregister vs non-compliant).
    - Detects blender interface functions (execute, draw, invoke, etc.).
4. Treemap Visualization =
    - Left column: Global functions (green for register/unregister, red for others).
    - Right side: Box-packed treemap of classes and their methods.
    - Color-coded by compliance and function type.
    - Size-proportional rectangles (larger functions = larger boxes).
5. Image Composition = Title bar with addon metadata.
6. Saves the final composed image as a PNG in the `/dev_output/` directory.

Color Scheme: dark muted colors for visibility of white text
- Green: register/unregister functions (compliant globals)
- Red: Non-compliant global functions
- Blue: Operator classes
- Purple: Panel classes
- Orange: Property Group classes
- Muted green: Interface methods (execute, draw, invoke, poll)

VERSION:: 20260822
"""

import os
import shutil
import re
import sys
import ast
import logging
import subprocess
import tempfile
import importlib.util
from typing import List, Dict, Optional
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# --- CONFIG ---
ADDON_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../addon'))
OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../dev_output'))
FONT_PATH = None  # Optionally set a custom font path
TITLE_HEIGHT = 80
BG_COLOR = (32, 32, 32)
TITLE_COLOR = (240, 240, 240)
CATEGORY_COLOR = (120, 180, 255)
NAME_COLOR = (255, 220, 120)

# Layout / treemap tunables
TOTAL_WIDTH = 2500
TOTAL_HEIGHT = 500
PANEL_WIDTH = 400
LEFT_COLUMN_RATIO = 0.10        # fraction of width reserved for global functions
FUNC_HEIGHT_MIN = 35
FUNC_HEIGHT_MAX = 80
FUNC_HEIGHT_PER_LINE = 3
CLASS_BOX_MIN_SIZE = 20         # px; below this an overflow marker is drawn
METHOD_HEIGHT_MIN = 18
METHOD_NAME_MIN_HEIGHT = 12
METHOD_NAME_MIN_WIDTH = 40
CLASS_NAME_FONT_SIZE = 28
METHOD_FONT_SIZE = 22
FUNC_FONT_SIZE = 24
TITLE_FONT_SIZE = 50
OVERFLOW_FONT_SIZE = 16
OUTLINE_COLOR = (180, 180, 180)
METHOD_OUTLINE_COLOR = (150, 150, 150)
TEXT_COLOR = (240, 240, 240)
OVERFLOW_TEXT_COLOR = (220, 200, 120)
OVERFLOW_BG = (40, 40, 40)
PANEL_PLACEHOLDER_COLOR = (60, 60, 60)
INTERFACE_METHOD_COLOR = (80, 110, 60)   # muted green
CLASS_TYPE_COLORS = {
    'operator': (45, 75, 120),           # darker muted blue
    'panel': (90, 50, 120),              # darker muted purple
    'property_group': (130, 85, 40),     # darker muted orange
    'other': (70, 70, 70),               # dark gray
}
CLASS_COLOR_DARKEN = 25                 # subtracted from base color for non-interface methods

# --- FONT CACHE ---
# Fonts are loaded once and reused across all rendering calls. Loading
# `arial.ttf` per-iteration (as the original code did) is needlessly expensive
# and swallowed Ctrl-C via bare `except:`.
_FONT_CACHE: Dict[int, ImageFont.ImageFont] = {}

def _get_font(size: int) -> ImageFont.ImageFont:
    """Return a cached TrueType font of the given size, falling back to PIL's
    default bitmap font if `arial.ttf` (and `FONT_PATH`) are unavailable."""
    if size in _FONT_CACHE:
        return _FONT_CACHE[size]
    font = None
    if FONT_PATH:
        try:
            font = ImageFont.truetype(FONT_PATH, size)
        except OSError:
            font = None
    if font is None:
        try:
            font = ImageFont.truetype("arial.ttf", size)
        except OSError:
            font = ImageFont.load_default()
    _FONT_CACHE[size] = font
    return font

# --- UTILS ---
def discover_addon_files(addon_dir: str) -> List[str]:
    """Recursively find all `z_blender_*.py` addon files in the addon directory.

    Non-addon Python files (utils, helpers, `__init__`, tests, etc.) are
    skipped so they don't get run through the full pipeline.
    """
    addon_files = []
    for root, dirs, files in os.walk(addon_dir):
        for file in files:
            if file.endswith('.py') and file.startswith('z_blender_'):
                addon_files.append(os.path.join(root, file))
    return addon_files

def ensure_output_dir() -> None:
    """Create the OUTPUT_DIR if it does not already exist."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

def resolve_blender_executable() -> Optional[str]:
    """Resolve Blender executable path using BLENDER_EXE or PATH. Returns absolute path or None if not found."""
    env_path = os.environ.get('BLENDER_EXE')
    if env_path:
        logger.info("BLENDER_EXE env var is set: %s", env_path)
        if os.path.exists(env_path):
            logger.info("Using Blender from BLENDER_EXE: %s", env_path)
            return env_path
        else:
            logger.warning("BLENDER_EXE points to a non-existent path: %s", env_path)
    # Try common names on PATH
    which_path = shutil.which('blender') or shutil.which('blender.exe')
    if which_path:
        logger.info("Found Blender on PATH: %s", which_path)
        return which_path
    logger.warning("Blender not found via BLENDER_EXE or PATH.")
    return None

def _make_blender_screenshot_script(addon_path: str, screenshot_path: str) -> str:
    """Generate a Blender Python script that loads the addon and takes a screenshot of the panel.

    Paths are injected via :func:`json.dumps` so they become valid Python
    string literals regardless of quotes or backslashes in the path (Windows
    paths in particular). The addon is loaded with ``importlib`` and explicitly
    registered, rather than ``addon_utils.enable`` (which only resolves addons
    in Blender's known search paths and won't find a single-file addon in an
    arbitrary folder). The screenshot uses ``bpy.context.temp_override``, the
    context-override idiom supported by Blender 3.x/4.x.
    """
    import json
    addon_path_lit = json.dumps(addon_path)
    addon_dir_lit = json.dumps(os.path.dirname(addon_path))
    screenshot_path_lit = json.dumps(screenshot_path)
    script = f"""
import bpy
import sys
import os
import importlib

addon_dir = {addon_dir_lit}
if addon_dir not in sys.path:
    sys.path.append(addon_dir)

addon_path = {addon_path_lit}
addon_name = os.path.splitext(os.path.basename(addon_path))[0]
mod = importlib.import_module(addon_name)
if hasattr(mod, "register"):
    try:
        mod.register()
    except Exception as e:
        print("addon register() failed: %s" % e)

screenshot_path = {screenshot_path_lit}
captured = False
for area in bpy.context.screen.areas:
    if area.type == 'VIEW_3D':
        try:
            with bpy.context.temp_override(area=area):
                bpy.ops.screen.screenshot(filepath=screenshot_path)
            captured = True
        except Exception as e:
            print("screenshot via temp_override failed: %s" % e)
        break
if not captured:
    # Fallback for very old Blender versions without temp_override.
    try:
        bpy.ops.screen.screenshot(filepath=screenshot_path)
    except Exception as e:
        print("screenshot fallback failed: %s" % e)
"""
    return script

def get_blender_panel_screenshot(addon_path: str, output_dir: str) -> Optional[str]:
    """Load the addon in Blender and capture a screenshot of its panel. Returns path to screenshot or None."""
    blender_exe = resolve_blender_executable()
    if not blender_exe:
        logger.info("Blender executable not found. Skipping panel screenshot and using placeholder.")
        return None
    else:
        logger.info("Using Blender executable: %s", blender_exe)
    screenshot_path = os.path.join(output_dir, os.path.splitext(os.path.basename(addon_path))[0] + '_panel.png')
    with tempfile.NamedTemporaryFile('w', delete=False, suffix='.py') as temp_script:
        temp_script.write(_make_blender_screenshot_script(addon_path, screenshot_path))
        temp_script_path = temp_script.name
    try:
        result = subprocess.run([
            blender_exe, '--background', '--factory-startup', '--python', temp_script_path
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60,
            text=True, encoding='utf-8', errors='replace')
        if os.path.exists(screenshot_path):
            return screenshot_path
        else:
            logger.warning("Blender screenshot failed. stderr: %s", result.stderr)
            if result.stdout:
                logger.debug("Blender stdout: %s", result.stdout)
            return None
    except Exception as e:
        logger.warning("Error running Blender for screenshot: %s", e)
        return None
    finally:
        if os.path.exists(temp_script_path):
            os.remove(temp_script_path)

# --- CODE ANALYSIS WITH COMPLIANCE ---

# Compliance constants
ALLOWED_GLOBAL_FUNCTIONS = {'register', 'unregister', 'menu_func_export', 'menu_func_import', 'menu_func'}
INTERFACE_METHODS = {'execute', 'draw', 'invoke', 'poll', 'check', 'modal', 'cancel'}
OPERATOR_PREFIX = '_OT_'
PANEL_PREFIX = '_PT_'
PROP_GROUP_PREFIX = '_PG_'

def get_full_name(node: ast.AST) -> str:
    """Recursively extract the full dotted name from an AST node."""
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        return get_full_name(node.value) + "." + node.attr
    return ""

class CodeStructureAnalyzer(ast.NodeVisitor):
    """Analyze Python addon code structure for visualization."""
    def __init__(self):
        self.global_functions = []  # [(name, line_count, is_compliant)]
        self.classes = []  # [{name, type, methods: [{name, line_count, is_interface}]}]
        self.current_class = None

    def visit_ClassDef(self, node):
        # Determine class type
        class_type = _classify_class(node)
        class_info = {
            'name': node.name,
            'type': class_type,
            'line_count': self._count_lines(node),
            'methods': []
        }

        # Analyze methods
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                method_info = {
                    'name': item.name,
                    'line_count': self._count_lines(item),
                    'is_interface': item.name in INTERFACE_METHODS,
                }
                class_info['methods'].append(method_info)

        self.classes.append(class_info)
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = None

    def visit_FunctionDef(self, node):
        # Only track top-level functions (not methods)
        if self.current_class is None:
            is_compliant = node.name in ALLOWED_GLOBAL_FUNCTIONS
            self.global_functions.append((node.name, self._count_lines(node), is_compliant))
        self.generic_visit(node)

    def _count_lines(self, node):
        """Count lines of code in a node. Requires Python 3.8+ (end_lineno)."""
        return node.end_lineno - node.lineno + 1

def _classify_class(node: ast.ClassDef) -> str:
    """Classify a class as operator/panel/property_group/other.

    Primary signal: the Blender naming convention prefixes `_OT_`, `_PT_`,
    `_PG_` in the class name. Secondary signal: base-class substring match
    (e.g. `bpy.types.Operator`).
    """
    if OPERATOR_PREFIX in node.name:
        return 'operator'
    if PANEL_PREFIX in node.name:
        return 'panel'
    if PROP_GROUP_PREFIX in node.name:
        return 'property_group'
    # Fall back to base-class inspection for non-conventionally-named classes.
    for base in node.bases:
        base_name = get_full_name(base)
        if "Operator" in base_name:
            return 'operator'
        if "Panel" in base_name:
            return 'panel'
        if "PropertyGroup" in base_name:
            return 'property_group'
    return 'other'

def analyze_addon_structure(addon_path: str) -> Dict:
    """Parse addon and return structure analysis.

    Returns a dict with keys ``global_functions``, ``classes`` and ``error``.
    ``error`` is None on success or a string describing why parsing failed
    (e.g. SyntaxError); in that case the function/class lists are empty so
    callers can still render a placeholder.
    """
    try:
        with open(addon_path, 'r', encoding='utf-8') as f:
            source_code = f.read()
        tree = ast.parse(source_code, filename=addon_path)
    except SyntaxError as e:
        return {
            'global_functions': [],
            'classes': [],
            'error': f"SyntaxError: {e.msg} (line {e.lineno})",
        }
    except OSError as e:
        return {
            'global_functions': [],
            'classes': [],
            'error': f"OSError: {e}",
        }

    analyzer = CodeStructureAnalyzer()
    analyzer.visit(tree)

    return {
        'global_functions': analyzer.global_functions,
        'classes': analyzer.classes,
        'error': None,
    }

# --- TREEMAP VISUALIZATION ---
def generate_treemap_visualization(structure: Dict, width: int, height: int) -> Image.Image:
    """Generate treemap visualization of code structure."""
    img = Image.new('RGB', (width, height), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Layout: smaller left column for global functions, more space for classes
    left_column_width = int(width * LEFT_COLUMN_RATIO)
    right_area_width = width - left_column_width - 10  # 10px spacing

    # Draw global functions in left column
    y_offset = 5
    for func_name, line_count, is_compliant in structure['global_functions']:
        func_height = max(FUNC_HEIGHT_MIN, min(line_count * FUNC_HEIGHT_PER_LINE, FUNC_HEIGHT_MAX))

        # Muted colors: darker green for compliant, darker red for non-compliant
        color = (50, 100, 50) if is_compliant else (140, 40, 40)

        draw.rectangle(
            [5, y_offset, left_column_width - 5, y_offset + func_height],
            fill=color,
            outline=OUTLINE_COLOR,
            width=2
        )

        # Draw function name , always full name
        font = _get_font(FUNC_FONT_SIZE)

        # Always draw full name
        draw.text(
            (left_column_width // 2, y_offset + func_height // 2),
            func_name,
            fill=TEXT_COLOR,
            font=font,
            anchor='mm'
        )

        y_offset += func_height + 5

    # Draw classes in right area using treemap
    classes_x = left_column_width + 10
    if structure['classes']:
        _draw_class_treemap(draw, structure['classes'], classes_x, 5, right_area_width, height - 10)

    return img

def _draw_class_treemap(draw, classes, x, y, width, height):
    """Draw classes as a treemap using a recursive slice-and-dice layout."""
    if not classes:
        return
    
    # Calculate total size (sum of all class line counts)
    total_size = sum(cls['line_count'] for cls in classes)
    if total_size == 0:
        return
    
    # Sort classes by size (largest first)
    sorted_classes = sorted(classes, key=lambda c: c['line_count'], reverse=True)
    
    # Use simple slice-and-dice for now
    _layout_classes_recursive(draw, sorted_classes, x, y, width, height, total_size, horizontal=True)

def _layout_classes_recursive(draw, classes, x, y, width, height, total_size, horizontal=True):
    """Recursively layout classes using slice-and-dice."""
    if not classes:
        return
    if width < CLASS_BOX_MIN_SIZE or height < CLASS_BOX_MIN_SIZE:
        # Sub-rectangle too small to render the remaining classes; draw an
        # overflow marker so the viewer knows classes were hidden here.
        if width >= 8 and height >= 8:
            draw.rectangle(
                [x, y, x + width - 1, y + height - 1],
                fill=OVERFLOW_BG,
                outline=METHOD_OUTLINE_COLOR,
                width=1
            )
            if width > 30 and height > 12:
                draw.text(
                    (x + width // 2, y + height // 2),
                    f"+{len(classes)}",
                    fill=OVERFLOW_TEXT_COLOR,
                    font=_get_font(OVERFLOW_FONT_SIZE),
                    anchor='mm'
                )
        return
    
    if len(classes) == 1:
        _draw_class_box(draw, classes[0], x, y, width, height)
        return
    
    # Split into two groups
    mid = len(classes) // 2
    group1 = classes[:mid]
    group2 = classes[mid:]
    
    size1 = sum(c['line_count'] for c in group1)
    size2 = sum(c['line_count'] for c in group2)
    
    if horizontal:
        # Split vertically (side by side)
        split_x = int((size1 / total_size) * width)
        _layout_classes_recursive(draw, group1, x, y, split_x, height, size1, not horizontal)
        _layout_classes_recursive(draw, group2, x + split_x, y, width - split_x, height, size2, not horizontal)
    else:
        # Split horizontally (top and bottom)
        split_y = int((size1 / total_size) * height)
        _layout_classes_recursive(draw, group1, x, y, width, split_y, size1, not horizontal)
        _layout_classes_recursive(draw, group2, x, y + split_y, width, height - split_y, size2, not horizontal)

def _draw_class_box(draw, class_info, x, y, width, height):
    """Draw a single class box with methods."""
    base_color = CLASS_TYPE_COLORS.get(class_info['type'], CLASS_TYPE_COLORS['other'])

    # Draw class background
    draw.rectangle(
        [x, y, x + width, y + height],
        fill=base_color,
        outline=OUTLINE_COLOR,
        width=2
    )

    # Draw class name at top
    font_class = _get_font(CLASS_NAME_FONT_SIZE)
    font_method = _get_font(METHOD_FONT_SIZE)

    # Class name - always show full name
    class_name = class_info['name']

    draw.text(
        (x + width // 2, y + 15),
        class_name,
        fill=TEXT_COLOR,
        font=font_class,
        anchor='mm'
    )

    # Draw methods below class name
    if class_info['methods'] and height > 40:
        methods_y = y + 30
        methods_height = height - 35

        # Calculate total method size
        total_method_size = sum(m['line_count'] for m in class_info['methods'])
        if total_method_size == 0:
            return

        # Draw methods as horizontal bars
        current_y = methods_y
        methods_drawn = 0
        for method in class_info['methods']:
            method_height = max(METHOD_HEIGHT_MIN, int((method['line_count'] / total_method_size) * methods_height))

            if current_y + method_height > y + height:
                # Remaining methods don't fit; render an overflow indicator
                # instead of silently dropping them.
                remaining = len(class_info['methods']) - methods_drawn
                if current_y < y + height and width > METHOD_NAME_MIN_WIDTH:
                    draw.rectangle(
                        [x + 5, current_y, x + width - 5, y + height - 1],
                        fill=OVERFLOW_BG,
                        outline=METHOD_OUTLINE_COLOR,
                        width=1
                    )
                    draw.text(
                        (x + width // 2, current_y + (y + height - current_y) // 2),
                        f"+{remaining} more",
                        fill=OVERFLOW_TEXT_COLOR,
                        font=font_method,
                        anchor='mm'
                    )
                break

            # Method color based on type - muted colors
            if method['is_interface']:
                method_color = INTERFACE_METHOD_COLOR  # Muted green for interface methods (execute, draw, etc)
            else:
                # Even darker shade of class color
                method_color = tuple(max(0, c - CLASS_COLOR_DARKEN) for c in base_color)

            draw.rectangle(
                [x + 5, current_y, x + width - 5, current_y + method_height - 2],
                fill=method_color,
                outline=METHOD_OUTLINE_COLOR,
                width=1
            )

            # Draw method name - always show full name
            if method_height > METHOD_NAME_MIN_HEIGHT and width > METHOD_NAME_MIN_WIDTH:
                method_name = method['name']

                draw.text(
                    (x + width // 2, current_y + method_height // 2),
                    method_name,
                    fill=TEXT_COLOR,
                    font=font_method,
                    anchor='mm'
                )

            current_y += method_height
            methods_drawn += 1

# --- IMAGE COMPOSITION ---
def render_title_image(metadata: Dict[str, str], width: int) -> Image.Image:
    """Render an image with the category and name as the title."""
    img = Image.new('RGB', (width, TITLE_HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)
    font = _get_font(TITLE_FONT_SIZE)
    category_text = f"[{metadata['category']}]"
    name_text = metadata['name'].replace('_', ' ').title()
    cat_x = 20
    draw.text((cat_x, 15), category_text, font=font, fill=CATEGORY_COLOR)
    # Offset the name by the actual rendered width of the category text so
    # long categories don't overlap the name and short ones don't leave a gap.
    name_x = cat_x + int(draw.textlength(category_text, font=font)) + 20
    draw.text((name_x, 15), name_text, font=font, fill=NAME_COLOR)
    return img

ADDON_FILENAME_RE = re.compile(r"z_blender_([A-Z0-9]+)_(.+)\.py$")

def extract_metadata_from_filename(filename: str) -> Optional[Dict[str, str]]:
    """Extract category and name from the addon filename.

    Expected pattern: ``z_blender_<CATEGORY>_<name>.py`` where CATEGORY is
    uppercase ASCII letters/digits (e.g. ``GEN``, ``MESH``, ``3D``).

    Returns ``{"category": ..., "name": ...}`` on a match, or ``None`` if the
    filename does not follow the convention (so callers can skip non-addon
    files instead of producing garbage metadata).
    """
    base = os.path.basename(filename)
    match = ADDON_FILENAME_RE.match(base)
    if match:
        category, name = match.groups()
        return {"category": category, "name": name}
    return None

def compose_final_image(metadata: Dict[str, str], panel_img_path: Optional[str], structure: Dict, output_path: str):
    """Compose the title, panel screenshot, and treemap visualization in 5:1 ultra-wide layout."""
    # 5:1 aspect ratio dimensions - ultra-wide format
    total_width = TOTAL_WIDTH
    total_height = TOTAL_HEIGHT

    # Layout sections
    content_height = total_height - TITLE_HEIGHT
    panel_width = PANEL_WIDTH
    treemap_width = total_width - panel_width
    
    # Create base image
    out_img = Image.new('RGB', (total_width, total_height), BG_COLOR)
    
    # Render title
    title_img = render_title_image(metadata, width=total_width)
    out_img.paste(title_img, (0, 0))
    
    # Load and paste panel screenshot
    try:
        if panel_img_path and os.path.exists(panel_img_path):
            panel_img = Image.open(panel_img_path).convert('RGB')
            # Fit the panel into the panel_width x content_height box while
            # preserving aspect ratio, then center-paste onto a placeholder
            # of exactly panel_width so the treemap offset is always correct.
            target_w, target_h = panel_width, content_height
            src_w, src_h = panel_img.width, panel_img.height
            scale = min(target_w / src_w, target_h / src_h)
            new_w = max(1, int(src_w * scale))
            new_h = max(1, int(src_h * scale))
            panel_img = panel_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            panel_slot = Image.new('RGB', (target_w, target_h), PANEL_PLACEHOLDER_COLOR)
            panel_slot.paste(panel_img, ((target_w - new_w) // 2, (target_h - new_h) // 2))
            out_img.paste(panel_slot, (0, TITLE_HEIGHT))
        else:
            # Placeholder for panel
            placeholder = Image.new('RGB', (panel_width, content_height), PANEL_PLACEHOLDER_COLOR)
            out_img.paste(placeholder, (0, TITLE_HEIGHT))
    except Exception as e:
        logger.warning("Could not load panel image: %s", e)
        placeholder = Image.new('RGB', (panel_width, content_height), PANEL_PLACEHOLDER_COLOR)
        out_img.paste(placeholder, (0, TITLE_HEIGHT))

    # Generate and paste treemap visualization
    treemap_img = generate_treemap_visualization(structure, treemap_width, content_height)
    out_img.paste(treemap_img, (panel_width, TITLE_HEIGHT))
    
    out_img.save(output_path)
    logger.info("Saved composed image: %s", output_path)
    return output_path

# --- MAIN PIPELINE ---
def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ensure_output_dir()
    addon_files = discover_addon_files(ADDON_DIR)
    logger.info("Discovered %d addon files.", len(addon_files))
    for addon_path in addon_files:
        metadata = extract_metadata_from_filename(addon_path)
        if metadata is None:
            logger.info("Skipping non-addon file: %s", os.path.basename(addon_path))
            continue
        addon_label = f"{metadata['category']} - {metadata['name']}"
        try:
            logger.info("Processing: %s", addon_label)

            # Analyze code structure
            logger.info("  Analyzing code structure...")
            structure = analyze_addon_structure(addon_path)
            if structure.get('error'):
                logger.warning("  Could not parse %s: %s", addon_label, structure['error'])
            else:
                logger.info("  Found %d global functions, %d classes",
                            len(structure['global_functions']), len(structure['classes']))

            # Get panel screenshot (optional)
            panel_img_path = get_blender_panel_screenshot(addon_path, OUTPUT_DIR)

            # Generate final image with treemap
            output_img_path = os.path.join(OUTPUT_DIR, f"{metadata['category']}_{metadata['name']}_overview.png")
            compose_final_image(metadata, panel_img_path, structure, output_img_path)
            logger.info("Saved: %s", output_img_path)
        except Exception as e:
            # One bad addon must not abort the whole batch.
            logger.exception("Failed to process %s: %s", addon_label, e)
            continue

if __name__ == "__main__":
    main()