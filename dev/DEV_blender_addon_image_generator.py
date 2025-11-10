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
    - Finds cross-references between classes.
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
- Yellow: Interface methods (execute, draw, invoke, poll)
- Cyan: Cross-referenced methods

VERSION:: 20251107
"""

import os
import shutil
import re
import sys
import importlib.util
from typing import List, Dict, Optional
from PIL import Image, ImageDraw, ImageFont

# --- CONFIG ---
ADDON_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../addon'))
OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../dev_output'))
FONT_PATH = None  # Optionally set a custom font path
TITLE_HEIGHT = 80
BG_COLOR = (32, 32, 32)
TITLE_COLOR = (240, 240, 240)
CATEGORY_COLOR = (120, 180, 255)
NAME_COLOR = (255, 220, 120)

# --- UTILS ---
def discover_addon_files(addon_dir: str) -> List[str]:
    """Recursively find all .py addon files in the addon directory."""
    addon_files = []
    for root, dirs, files in os.walk(addon_dir):
        for file in files:
            if file.endswith('.py') and not file.startswith('__'):
                addon_files.append(os.path.join(root, file))
    return addon_files

def ensure_output_dir() -> None:
    """Create the OUTPUT_DIR if it does not already exist."""
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

def resolve_blender_executable() -> Optional[str]:
    """Resolve Blender executable path using BLENDER_EXE or PATH. Returns absolute path or None if not found."""
    env_path = os.environ.get('BLENDER_EXE')
    if env_path:
        print(f"BLENDER_EXE env var is set: {env_path}")
        if os.path.exists(env_path):
            print(f"Using Blender from BLENDER_EXE: {env_path}")
            return env_path
        else:
            print(f"BLENDER_EXE points to a non-existent path: {env_path}")
    # Try common names on PATH
    which_path = shutil.which('blender') or shutil.which('blender.exe')
    if which_path:
        print(f"Found Blender on PATH: {which_path}")
        return which_path
    print("Blender not found via BLENDER_EXE or PATH.")
    return None

import subprocess
import tempfile

def _make_blender_screenshot_script(addon_path: str, screenshot_path: str) -> str:
    """Generate a Blender Python script that loads the addon and takes a screenshot of the panel."""
    script = f"""
import bpy
import sys
import addon_utils
import os
# Add addon directory to sys.path
addon_dir = os.path.dirname(r'{addon_path}')
if addon_dir not in sys.path:
    sys.path.append(addon_dir)
# Enable the addon
addon_name = os.path.basename(r'{addon_path}')[:-3]
addon_utils.enable(addon_name)
# Set up a new layout (optional: customize for your UI)
for area in bpy.context.screen.areas:
    if area.type == 'VIEW_3D':
        override = bpy.context.copy()
        override['area'] = area
        bpy.ops.screen.screenshot(override, filepath=r'{screenshot_path}')
        break
"""
    return script

def get_blender_panel_screenshot(addon_path: str, output_dir: str) -> Optional[str]:
    """Load the addon in Blender and capture a screenshot of its panel. Returns path to screenshot or None."""
    blender_exe = resolve_blender_executable()
    if not blender_exe:
        print("Blender executable not found. Skipping panel screenshot and using placeholder.")
        return None
    else:
        print(f"Using Blender executable: {blender_exe}")
    screenshot_path = os.path.join(output_dir, os.path.splitext(os.path.basename(addon_path))[0] + '_panel.png')
    with tempfile.NamedTemporaryFile('w', delete=False, suffix='.py') as temp_script:
        temp_script.write(_make_blender_screenshot_script(addon_path, screenshot_path))
        temp_script_path = temp_script.name
    try:
        result = subprocess.run([
            blender_exe, '--background', '--factory-startup', '--python', temp_script_path
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        if os.path.exists(screenshot_path):
            return screenshot_path
        else:
            print(f"Blender screenshot failed: {result.stderr.decode()}")
            return None
    except Exception as e:
        print(f"Error running Blender for screenshot: {e}")
        return None
    finally:
        if os.path.exists(temp_script_path):
            os.remove(temp_script_path)

# --- CODE ANALYSIS WITH COMPLIANCE ---
import ast

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
        self.classes = []  # [{name, type, methods: [{name, line_count, is_interface, is_referenced}]}]
        self.class_references = {}  # {class_name: set of referenced class names}
        self.current_class = None
        
    def visit_ClassDef(self, node):
        # Determine class type
        class_type = 'other'
        for base in node.bases:
            base_name = get_full_name(base)
            if "Operator" in base_name:
                class_type = 'operator'
            elif "Panel" in base_name:
                class_type = 'panel'
            elif "PropertyGroup" in base_name:
                class_type = 'property_group'
        
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
                    'is_referenced': False  # Will be updated later
                }
                class_info['methods'].append(method_info)
        
        self.classes.append(class_info)
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = None
    
    def visit_FunctionDef(self, node):
        # Only track top-level functions (not methods)
        if self.current_class is None:
            is_compliant = any(node.name.startswith(prefix) or node.name == prefix 
                             for prefix in ALLOWED_GLOBAL_FUNCTIONS)
            self.global_functions.append((node.name, self._count_lines(node), is_compliant))
        self.generic_visit(node)
    
    def _count_lines(self, node):
        """Count lines of code in a node."""
        if hasattr(node, 'end_lineno') and hasattr(node, 'lineno'):
            return node.end_lineno - node.lineno + 1
        return 5  # Default estimate
    
    def analyze_references(self, tree):
        """Find cross-references between classes."""
        # look for class name mentions in other classes
        for class_info in self.classes:
            for other_class in self.classes:
                if class_info['name'] != other_class['name']:
                    # Check if other class is referenced in this class's methods
                    for method in class_info['methods']:
                        # Mark as potentially referenced 
                        pass

def analyze_addon_structure(addon_path: str) -> Dict:
    """Parse addon and return structure analysis."""
    with open(addon_path, 'r', encoding='utf-8') as f:
        source_code = f.read()
    
    tree = ast.parse(source_code, filename=addon_path)
    analyzer = CodeStructureAnalyzer()
    analyzer.visit(tree)
    analyzer.analyze_references(tree)
    
    return {
        'global_functions': analyzer.global_functions,
        'classes': analyzer.classes
    }

# --- TREEMAP VISUALIZATION ---
def generate_treemap_visualization(structure: Dict, width: int, height: int) -> Image.Image:
    """Generate treemap visualization of code structure."""
    img = Image.new('RGB', (width, height), (32, 32, 32))
    draw = ImageDraw.Draw(img)
    
    # Layout: smaller left column for global functions, more space for classes
    left_column_width = int(width * 0.10)  # 10% for global functions 
    right_area_width = width - left_column_width - 10  # 10px spacing
    
    # Draw global functions in left column
    y_offset = 5
    for func_name, line_count, is_compliant in structure['global_functions']:
        func_height = max(35, min(line_count * 3, 80))
        
        # Muted colors: darker green for compliant, darker red for non-compliant
        color = (50, 100, 50) if is_compliant else (140, 40, 40)
        
        draw.rectangle(
            [5, y_offset, left_column_width - 5, y_offset + func_height],
            fill=color,
            outline=(180, 180, 180),
            width=2
        )
        
        # Draw function name , always full name
        try:
            font = ImageFont.truetype("arial.ttf", 24)  # 
        except:
            font = ImageFont.load_default()
        
        # Always draw full name
        draw.text(
            (left_column_width // 2, y_offset + func_height // 2),
            func_name,
            fill=(240, 240, 240),
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
    """Draw classes as treemap using squarified algorithm."""
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
    if not classes or width < 20 or height < 20:
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
    # Muted, darker class type colors for better text visibility
    type_colors = {
        'operator': (45, 75, 120),      # Darker muted blue
        'panel': (90, 50, 120),         # Darker muted purple
        'property_group': (130, 85, 40), # Darker muted orange
        'other': (70, 70, 70)           # Dark gray
    }
    
    base_color = type_colors.get(class_info['type'], (70, 70, 70))
    
    # Draw class background
    draw.rectangle(
        [x, y, x + width, y + height],
        fill=base_color,
        outline=(180, 180, 180),
        width=2
    )
    
    # Draw class name at top
    try:
        font_class = ImageFont.truetype("arial.ttf", 28)  
        font_method = ImageFont.truetype("arial.ttf", 22)  
    except:
        font_class = ImageFont.load_default()
        font_method = ImageFont.load_default()
    
    # Class name - always show full name
    class_name = class_info['name']
    
    draw.text(
        (x + width // 2, y + 15),
        class_name,
        fill=(240, 240, 240),
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
        for method in class_info['methods']:
            method_height = max(18, int((method['line_count'] / total_method_size) * methods_height))
            
            if current_y + method_height > y + height:
                break
            
            # Method color based on type - muted colors
            if method['is_interface']:
                method_color = (80, 110, 60)  # Muted green for interface methods (execute, draw, etc)
            else:
                # Even darker shade of class color
                method_color = tuple(max(0, c - 25) for c in base_color)
            
            draw.rectangle(
                [x + 5, current_y, x + width - 5, current_y + method_height - 2],
                fill=method_color,
                outline=(150, 150, 150),
                width=1
            )
            
            # Draw method name - always show full name
            if method_height > 12 and width > 40:
                method_name = method['name']  
                
                draw.text(
                    (x + width // 2, current_y + method_height // 2),
                    method_name,
                    fill=(240, 240, 240),
                    font=font_method,
                    anchor='mm'
                )
            
            current_y += method_height

# --- IMAGE COMPOSITION ---
def render_title_image(metadata: Dict[str, str], width: int) -> Image.Image:
    """Render an image with the category and name as the title."""
    img = Image.new('RGBA', (width, TITLE_HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)
    font_size = 50  
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except:
        font = ImageFont.truetype(FONT_PATH, font_size) if FONT_PATH else ImageFont.load_default()
    category_text = f"[{metadata['category']}]"
    name_text = metadata['name'].replace('_', ' ').title()
    draw.text((20, 15), category_text, font=font, fill=CATEGORY_COLOR)
    draw.text((250, 15), name_text, font=font, fill=NAME_COLOR)
    return img

def extract_metadata_from_filename(filename: str) -> Dict[str, str]:
    """Extract category and name from the addon filename (e.g., z_blender_GEN_planet_procedural.py)."""
    base = os.path.basename(filename)
    match = re.match(r"z_blender_([A-Z]+)_([\w_]+)\.py", base)
    if match:
        category, name = match.groups()
        return {"category": category, "name": name}
    # fallback: try to extract something reasonable
    parts = base.replace('.py', '').split('_')
    return {"category": parts[2] if len(parts) > 2 else "UNKNOWN", "name": '_'.join(parts[3:]) if len(parts) > 3 else base}

def compose_final_image(metadata: Dict[str, str], panel_img_path: Optional[str], structure: Dict, output_path: str):
    """Compose the title, panel screenshot, and treemap visualization in 20:4 layout."""
    # 5:1 aspect ratio dimensions - ultra-wide format
    total_width = 2500
    total_height = 500
    
    # Layout sections
    content_height = total_height - TITLE_HEIGHT
    panel_width = 400  # Smaller panel width for ultra-wide format
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
            # Resize to fit if needed
            if panel_img.height > content_height:
                aspect = panel_img.width / panel_img.height
                panel_img = panel_img.resize((int(content_height * aspect), content_height), Image.Resampling.LANCZOS)
            out_img.paste(panel_img, (0, TITLE_HEIGHT))
        else:
            # Placeholder for panel
            placeholder = Image.new('RGB', (panel_width, content_height), (60, 60, 60))
            out_img.paste(placeholder, (0, TITLE_HEIGHT))
    except Exception as e:
        print(f"Could not load panel image: {e}")
        placeholder = Image.new('RGB', (panel_width, content_height), (60, 60, 60))
        out_img.paste(placeholder, (0, TITLE_HEIGHT))
    
    # Generate and paste treemap visualization
    treemap_img = generate_treemap_visualization(structure, treemap_width, content_height)
    out_img.paste(treemap_img, (panel_width, TITLE_HEIGHT))
    
    out_img.save(output_path)
    print(f"Saved composed image: {output_path}")
    return output_path

# --- MAIN PIPELINE ---
def main():
    ensure_output_dir()
    addon_files = discover_addon_files(ADDON_DIR)
    print(f"Discovered {len(addon_files)} addon files.")
    for addon_path in addon_files:
        metadata = extract_metadata_from_filename(addon_path)
        print(f"Processing: {metadata['category']} - {metadata['name']}")
        
        # Analyze code structure
        print(f"  Analyzing code structure...")
        structure = analyze_addon_structure(addon_path)
        print(f"  Found {len(structure['global_functions'])} global functions, {len(structure['classes'])} classes")
        
        # Get panel screenshot (optional)
        panel_img_path = get_blender_panel_screenshot(addon_path, OUTPUT_DIR)
        
        # Generate final image with treemap
        output_img_path = os.path.join(OUTPUT_DIR, f"{metadata['category']}_{metadata['name']}_overview.png")
        compose_final_image(metadata, panel_img_path, structure, output_img_path)
        print(f"Saved: {output_img_path}")

if __name__ == "__main__":
    main()