"""
Blender Addon Compliance Checker
-------------------------------
This tool checks Blender addon Python files for compliance with best practices and conventions.
It performs various checks including:
- Ensuring only register / unregister and menu functions are global for clean namespace 
- Checking for proper class organization ( operator , panel , property )
- Verifying required addon metadata
- Checking Naming conventions , Namespace uniqueness , Group prefix
"""

#region IMPORTS
import os
import ast
import sys
import re
import logging
from typing import List, Dict, Set, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
import datetime

# Import the known Blender icon set. This lives in a sibling module so the
# large icon table is kept out of the checker source. The import is guarded
# so the checker still works (with icon checking disabled) if the data file
# is missing - e.g. when copied standalone.
try:
    from DEV_blender_icons import VALID_BL_ICONS
except ImportError:
    VALID_BL_ICONS = None  # type: ignore[assignment]
#endregion

#region CONFIG
__all__ = [
    "BlenderAddonChecker",
    "ComplianceIssue",
    "IssueLevel",
    "check_directory",
    "write_report_to_file",
    "get_full_name",
]

logger = logging.getLogger(__name__)

PROJECT_PREFIX = "ZENV"  # used as category prefix and side panel group
ADDON_PREFIX = "z_blender"  # filename prefix , using "blender" for distinction between other python files

# Class type prefixes
OPERATOR_PREFIX = "_OT_"   # For operator classes
PANEL_PREFIX = "_PT_"      # For panel classes
PROP_GROUP_PREFIX = "_PG_"  # For property group classes

# Required operator options
REQUIRED_BL_OPTIONS = {'REGISTER', 'UNDO'}

# Required bl_info keys
REQUIRED_BL_INFO_KEYS = {'name', 'author', 'version', 'blender', 'location', 'description', 'category'}

# Directories to ignore during compliance checks
IGNORED_DIRECTORIES = {'backup', 'removed'}

# Allowed global functions
MENU_FUNC_PREFIXES = {'menu_func'}
ALLOWED_GLOBAL_FUNCTIONS = {'register', 'unregister'} | MENU_FUNC_PREFIXES
#endregion

#region DATAMODL
class IssueLevel(Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"

@dataclass
class ComplianceIssue:
    level: IssueLevel
    message: str
    line: int
    file: str
#endregion

#region AST_HELP
def get_full_name(node: ast.AST) -> str:
    """Recursively extract the full dotted name from an AST node."""
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        return get_full_name(node.value) + "." + node.attr
    return ""

def has_return_statement(func_node: ast.AST) -> bool:
    """Return True if `func_node` (a FunctionDef) has a return statement in its own
    body, ignoring returns inside nested function/class definitions."""
    for child in ast.iter_child_nodes(func_node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(child, ast.Return):
            return True
        for descendant in ast.iter_child_nodes(child):
            if _contains_return(descendant):
                return True
    return False

def _contains_return(node: ast.AST) -> bool:
    """Recursively check for a Return, stopping at nested function/class boundaries."""
    if isinstance(node, ast.Return):
        return True
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return False
    for child in ast.iter_child_nodes(node):
        if _contains_return(child):
            return True
    return False

def classify_base(base_node: ast.AST) -> Optional[str]:
    """Classify a class base node by its final component.
    Returns 'Operator', 'Panel', 'PropertyGroup', or None.
    Uses the final dotted component so 'bpy.types.Operator' matches but
    'MyCustomOperatorMixin' does not."""
    full = get_full_name(base_node)
    if not full:
        return None
    last = full.rsplit('.', 1)[-1]
    if last == 'Operator':
        return 'Operator'
    if last == 'Panel':
        return 'Panel'
    if last == 'PropertyGroup':
        return 'PropertyGroup'
    return None
#endregion

#region CHECKER
class BlenderAddonChecker:
    """Per-file compliance checker. Parses a Blender addon .py file with the
    AST module and records issues against the project's naming/metadata
    conventions. Safe to reuse across files (state is reset in load_file)."""

    #region INIT
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.issues: List[ComplianceIssue] = []
        self.tree = None
        self.global_functions: Set[str] = set()
        # Track class info: (class_name, bl_idname, bl_label)
        self.class_names: List[Tuple[str, Optional[str], Optional[str]]] = []

    def add_issue(self, level: IssueLevel, line: int, message: str):
        """Helper method to add an issue with consistent formatting."""
        self.issues.append(ComplianceIssue(
            level,
            message,
            line,
            self.file_path
        ))
    #endregion

    #region LOAD
    def load_file(self) -> bool:
        """Load and parse the Python file. Resets accumulated state so the
        checker can be safely reused across files."""
        # Reset state from any previous run
        self.issues.clear()
        self.global_functions.clear()
        self.class_names.clear()
        self.tree = None
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.tree = ast.parse(content)
            return True
        except (SyntaxError, OSError, UnicodeDecodeError) as e:
            logger.debug("Failed to parse %s: %s", self.file_path, e, exc_info=True)
            self.add_issue(
                IssueLevel.ERROR,
                0,
                f"Failed to parse file: {type(e).__name__}: {e}"
            )
            return False
    #endregion

    #region CHECKS
    def check_bl_info(self):
        """Check if bl_info dictionary is present and properly formatted."""
        found_bl_info = False
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == 'bl_info':
                        found_bl_info = True
                        if not isinstance(node.value, ast.Dict):
                            self.issues.append(ComplianceIssue(
                                IssueLevel.ERROR,
                                "bl_info must be a dictionary",
                                node.lineno,
                                self.file_path
                            ))
                        else:
                            # Check required bl_info keys
                            found_keys = set()
                            for key in node.value.keys:
                                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                                    found_keys.add(key.value)
                            
                            missing_keys = REQUIRED_BL_INFO_KEYS - found_keys
                            if missing_keys:
                                self.issues.append(ComplianceIssue(
                                    IssueLevel.WARNING,
                                    f"Missing recommended bl_info keys: {', '.join(missing_keys)}",
                                    node.lineno,
                                    self.file_path
                                ))
        
        if not found_bl_info:
            self.issues.append(ComplianceIssue(
                IssueLevel.ERROR,
                "Missing bl_info dictionary (required for Blender addons)",
                0,
                self.file_path
            ))

    def check_global_functions(self):
        """Check for global functions. Only register/unregister (and allowed menu functions) should be global."""
        self.global_functions.clear()  # Reset the set before checking
        for node in self.tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Add all global functions to the set
                self.global_functions.add(node.name)
                # async def at module level is not supported by Blender's loader
                if isinstance(node, ast.AsyncFunctionDef):
                    self.add_issue(
                        IssueLevel.ERROR,
                        node.lineno,
                        f"Global async function '{node.name}' is not supported by Blender's addon loader"
                    )
                    continue
                # Skip register and unregister functions
                if node.name in ['register', 'unregister']:
                    continue
                # Skip menu registration functions if they start with allowed prefixes
                if any(node.name.startswith(prefix) for prefix in MENU_FUNC_PREFIXES):
                    continue
                # All other global functions are flagged
                self.add_issue(
                    IssueLevel.ERROR,
                    node.lineno,
                    f"Global function '{node.name}' found. Only register/unregister (and allowed menu functions) should be global"
                )

    def check_register_unregister(self):
        """Check if register and unregister functions are properly implemented."""
        has_register = False
        has_unregister = False

        # First check if they exist at module level (sync defs only - Blender
        # requires register/unregister to be regular functions).
        for node in self.tree.body:
            if isinstance(node, ast.FunctionDef):
                if node.name == 'register':
                    has_register = True
                elif node.name == 'unregister':
                    has_unregister = True
        
        if not has_register:
            self.issues.append(ComplianceIssue(
                IssueLevel.ERROR,
                "Missing register() function",
                0,
                self.file_path
            ))
        
        if not has_unregister:
            self.issues.append(ComplianceIssue(
                IssueLevel.ERROR,
                "Missing unregister() function",
                0,
                self.file_path
            ))

    def check_class_naming(self):
        """Check if classes follow Blender naming conventions and collect naming info."""
        # Get addon type from filename (e.g., 'TEX' from z_blender_TEX_remap.py)
        filename = os.path.basename(self.file_path)
        addon_type = None
        match = re.match(rf'{re.escape(ADDON_PREFIX)}_([A-Z]+)_', filename)
        if match:
            addon_type = match.group(1)  # e.g., 'TEX', 'GEN'

        for node in ast.walk(self.tree):
            if isinstance(node, ast.ClassDef):
                # Store class name for later analysis: [class_name, bl_idname, bl_label]
                class_info = [node.name, None, None]
                
                # Determine class type using exact final-component matching
                is_operator = False
                is_panel = False
                is_property_group = False

                for base in node.bases:
                    cls = classify_base(base)
                    if cls == 'Operator':
                        is_operator = True
                    elif cls == 'Panel':
                        is_panel = True
                    elif cls == 'PropertyGroup':
                        is_property_group = True

                # Check class prefix based on type
                if is_operator:
                    if not node.name.startswith(f"{PROJECT_PREFIX}{OPERATOR_PREFIX}"):
                        self.add_issue(
                            IssueLevel.ERROR,
                            node.lineno,
                            f"Operator class '{node.name}' must start with {PROJECT_PREFIX}{OPERATOR_PREFIX}"
                        )
                elif is_panel:
                    if not node.name.startswith(f"{PROJECT_PREFIX}{PANEL_PREFIX}"):
                        self.add_issue(
                            IssueLevel.ERROR,
                            node.lineno,
                            f"Panel class '{node.name}' must start with {PROJECT_PREFIX}{PANEL_PREFIX}"
                        )
                elif is_property_group:
                    if not node.name.startswith(f"{PROJECT_PREFIX}{PROP_GROUP_PREFIX}"):
                        self.add_issue(
                            IssueLevel.ERROR,
                            node.lineno,
                            f"Property Group class '{node.name}' must start with {PROJECT_PREFIX}{PROP_GROUP_PREFIX}"
                        )

                # Collect class attributes (bl_idname, bl_label) for later analysis.
                # Value-format checks (prefix, bl_category) are handled in
                # check_operator_requirements / check_panel_requirements to avoid
                # duplicate reports.
                for child in node.body:
                    if isinstance(child, ast.Assign):
                        for target in child.targets:
                            if isinstance(target, ast.Name):
                                if target.id == 'bl_idname':
                                    if isinstance(child.value, ast.Constant):
                                        class_info[1] = child.value.value
                                elif target.id == 'bl_label':
                                    if isinstance(child.value, ast.Constant):
                                        bl_label = child.value.value
                                        class_info[2] = bl_label

                                        # For panels, check if bl_label starts with addon type
                                        if is_panel and addon_type:
                                            if not bl_label.startswith(addon_type):
                                                self.add_issue(
                                                    IssueLevel.ERROR,
                                                    child.lineno,
                                                    f"Panel bl_label '{bl_label}' must start with '{addon_type}'"
                                                )

                # Store the class info if it has a bl_idname or bl_label
                if class_info[1] or class_info[2]:
                    self.class_names.append(tuple(class_info))

    def check_operator_requirements(self):
        """Check if operators have required attributes and methods."""
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ClassDef):
                # Check if this is an operator class
                is_operator = False
                for base in node.bases:
                    if classify_base(base) == 'Operator':
                        is_operator = True
                        break

                if is_operator:
                    # Required attributes
                    found_bl_idname = False
                    found_bl_label = False
                    found_bl_options = False
                    has_execute = False
                    has_docstring = bool(ast.get_docstring(node))
                    
                    for child in node.body:
                        if isinstance(child, ast.Assign):
                            for target in child.targets:
                                if isinstance(target, ast.Name):
                                    if target.id == 'bl_idname':
                                        found_bl_idname = True
                                        if isinstance(child.value, ast.Constant):
                                            bl_idname = child.value.value
                                            if bl_idname.startswith('object.'):
                                                self.add_issue(
                                                    IssueLevel.ERROR,
                                                    child.lineno,
                                                    f"Operator bl_idname '{bl_idname}' must use '{PROJECT_PREFIX.lower()}.' prefix instead of 'object.'"
                                                )
                                            elif not bl_idname.startswith(f'{PROJECT_PREFIX.lower()}.'):
                                                self.add_issue(
                                                    IssueLevel.ERROR,
                                                    child.lineno,
                                                    f"Operator bl_idname '{bl_idname}' must start with '{PROJECT_PREFIX.lower()}.'"
                                                )
                                    elif target.id == 'bl_label':
                                        found_bl_label = True
                                    elif target.id == 'bl_options':
                                        found_bl_options = True
                                        if isinstance(child.value, ast.Set):
                                            bl_options_set = {elt.value for elt in child.value.elts
                                                              if isinstance(elt, ast.Constant) and isinstance(elt.value, str)}
                                            missing_options = REQUIRED_BL_OPTIONS - bl_options_set
                                            if missing_options:
                                                self.add_issue(
                                                    IssueLevel.ERROR,
                                                    child.lineno,
                                                    f"Operator missing required bl_options: {', '.join(missing_options)}"
                                                )
                        elif isinstance(child, ast.FunctionDef):
                            if child.name == 'execute':
                                has_execute = True
                                if not has_return_statement(child):
                                    self.add_issue(
                                        IssueLevel.ERROR,
                                        child.lineno,
                                        "Operator execute() method must have a return statement"
                                    )
                    
                    if not found_bl_idname:
                        self.add_issue(
                            IssueLevel.ERROR,
                            node.lineno,
                            f"Operator class '{node.name}' missing bl_idname"
                        )
                    if not found_bl_label:
                        self.add_issue(
                            IssueLevel.ERROR,
                            node.lineno,
                            f"Operator class '{node.name}' missing bl_label"
                        )
                    if not found_bl_options:
                        self.add_issue(
                            IssueLevel.ERROR,
                            node.lineno,
                            f"Operator class '{node.name}' missing bl_options"
                        )
                    if not has_execute:
                        self.add_issue(
                            IssueLevel.ERROR,
                            node.lineno,
                            f"Operator class '{node.name}' missing execute() method"
                        )
                    if not has_docstring:
                        self.add_issue(
                            IssueLevel.WARNING,
                            node.lineno,
                            f"Operator class '{node.name}' missing docstring"
                        )

    def check_panel_requirements(self):
        """Check if panels have required attributes."""
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ClassDef):
                # Check if this is a panel class
                is_panel = False
                for base in node.bases:
                    if classify_base(base) == 'Panel':
                        is_panel = True
                        break

                if is_panel:
                    found_bl_idname = False
                    found_bl_label = False
                    found_bl_space_type = False
                    found_bl_region_type = False
                    found_bl_category = False
                    has_draw = False
                    has_docstring = bool(ast.get_docstring(node))
                    
                    for child in node.body:
                        if isinstance(child, ast.Assign):
                            for target in child.targets:
                                if isinstance(target, ast.Name):
                                    if target.id == 'bl_idname':
                                        found_bl_idname = True
                                        if isinstance(child.value, ast.Constant):
                                            bl_idname = child.value.value
                                            if not bl_idname.startswith(f'{PROJECT_PREFIX}_PT_'):
                                                self.add_issue(
                                                    IssueLevel.ERROR,
                                                    child.lineno,
                                                    f"Panel bl_idname '{bl_idname}' must start with '{PROJECT_PREFIX}_PT_'"
                                                )
                                    elif target.id == 'bl_label':
                                        found_bl_label = True
                                    elif target.id == 'bl_space_type':
                                        found_bl_space_type = True
                                    elif target.id == 'bl_region_type':
                                        found_bl_region_type = True
                                    elif target.id == 'bl_category':
                                        found_bl_category = True
                                        if isinstance(child.value, ast.Constant):
                                            bl_category = child.value.value
                                            if bl_category != PROJECT_PREFIX:
                                                self.add_issue(
                                                    IssueLevel.ERROR,
                                                    child.lineno,
                                                    f"Panel bl_category must be '{PROJECT_PREFIX}', found '{bl_category}'"
                                                )
                        elif isinstance(child, ast.FunctionDef):
                            if child.name == 'draw':
                                has_draw = True
                    
                    if not has_docstring:
                        self.add_issue(
                            IssueLevel.WARNING,
                            node.lineno,
                            f"Panel class '{node.name}' missing docstring"
                        )
                    
                    if not found_bl_idname:
                        self.add_issue(
                            IssueLevel.ERROR,
                            node.lineno,
                            f"Panel '{node.name}' missing bl_idname"
                        )
                    
                    if not found_bl_label:
                        self.add_issue(
                            IssueLevel.ERROR,
                            node.lineno,
                            f"Panel '{node.name}' missing bl_label"
                        )
                    
                    if not found_bl_space_type:
                        self.add_issue(
                            IssueLevel.ERROR,
                            node.lineno,
                            f"Panel '{node.name}' missing bl_space_type"
                        )
                    
                    if not found_bl_region_type:
                        self.add_issue(
                            IssueLevel.ERROR,
                            node.lineno,
                            f"Panel '{node.name}' missing bl_region_type"
                        )
                    
                    if not found_bl_category:
                        self.add_issue(
                            IssueLevel.ERROR,
                            node.lineno,
                            f"Panel '{node.name}' missing bl_category"
                        )
                        
                    if not has_draw:
                        self.add_issue(
                            IssueLevel.ERROR,
                            node.lineno,
                            f"Panel '{node.name}' missing draw() method"
                        )

    def check_property_definitions(self):
        """Check property definitions for best practices."""
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        if isinstance(node.value, ast.Call):
                            func_name = get_full_name(node.value.func)
                            # Match both bare StringProperty(...) and bpy.props.StringProperty(...)
                            if func_name.endswith('Property'):
                                has_name = False
                                has_description = False
                                for keyword in node.value.keywords:
                                    if keyword.arg == 'name':
                                        has_name = True
                                    elif keyword.arg == 'description':
                                        has_description = True

                                if not has_name:
                                    self.add_issue(
                                        IssueLevel.WARNING,
                                        node.lineno,
                                        f"Property '{target.id}' missing 'name' parameter"
                                    )

                                if not has_description:
                                    self.add_issue(
                                        IssueLevel.WARNING,
                                        node.lineno,
                                        f"Property '{target.id}' missing 'description' parameter"
                                    )

    def check_import_style(self):
        """Check import statements for style and organization."""
        for node in self.tree.body:
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name == '*':
                        self.issues.append(ComplianceIssue(
                            IssueLevel.WARNING,
                            f"Avoid wildcard imports from {node.module}",
                            node.lineno,
                            self.file_path
                        ))
                        break

    def check_icons(self):
        """Check that all ``icon='...'`` keyword arguments reference valid
        Blender UI icon identifiers. Catches typos / removed icons before
        they crash the panel at draw time. Silently skipped if the icon
        table (``DEV_blender_icons.VALID_BL_ICONS``) is unavailable."""
        if VALID_BL_ICONS is None:
            return
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if keyword.arg != 'icon':
                    continue
                # Only check string-literal icons; dynamic expressions
                # (variables, function calls) are out of static-analysis
                # scope and are silently skipped.
                if not isinstance(keyword.value, ast.Constant):
                    continue
                if not isinstance(keyword.value.value, str):
                    continue
                icon_name = keyword.value.value
                if icon_name == 'NONE':
                    continue  # 'NONE' is the default and always valid
                if icon_name not in VALID_BL_ICONS:
                    self.add_issue(
                        IssueLevel.ERROR,
                        keyword.value.lineno,
                        f"Invalid icon '{icon_name}' - not a recognized Blender UI icon. "
                        f"See DEV_blender_icons.py for the full list of valid names"
                    )
    #endregion

    #region RUN
    def run_all_checks(self) -> bool:
        """Load the file and run all compliance checks. Returns True if file loaded successfully."""
        if not self.load_file():
            return False

        self.check_bl_info()
        self.check_global_functions()
        self.check_register_unregister()
        self.check_class_naming()
        self.check_operator_requirements()
        self.check_panel_requirements()
        self.check_property_definitions()
        self.check_import_style()
        self.check_icons()
        return True
    #endregion
#endregion

#region SCAN
def check_directory(directory: str) -> int:
    """Check all addon .py files in a directory for compliance.
    Returns the number of files with errors (0 means clean)."""
    if not os.path.exists(directory):
        print(f"Directory not found: {directory}")
        return 1

    report_lines = []
    all_class_info = []
    total_files = 0
    bl_idname_map = {}  # Maps bl_idname to (file_path, class_name) for duplicate checking
    duplicate_bl_idnames: Set[str] = set()
    # Track which files had errors / warnings for accurate summary stats
    files_with_errors: Set[str] = set()
    files_with_warnings: Set[str] = set()

    for root, dirs, files in os.walk(directory):
        # Skip ignored directories
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRECTORIES]

        for file in files:
            # Only scan addon files (matching the addon filename prefix) so that
            # helper modules, __init__.py, and this checker itself are not flagged.
            if file.endswith('.py') and file.startswith(f"{ADDON_PREFIX}_"):
                total_files += 1
                file_path = os.path.join(root, file)
                checker = BlenderAddonChecker(file_path)

                if checker.run_all_checks():
                    # Check for duplicate bl_idname values
                    for class_name, bl_idname, bl_label in checker.class_names:
                        if bl_idname:
                            if bl_idname in bl_idname_map:
                                prev_file, prev_class = bl_idname_map[bl_idname]
                                report_lines.append(os.path.basename(file_path))
                                report_lines.append(f"  ERROR: Line 0: Duplicate bl_idname '{bl_idname}' in class '{class_name}' conflicts with '{prev_class}' in file '{os.path.basename(prev_file)}'")
                                report_lines.append("")
                                duplicate_bl_idnames.add(bl_idname)
                                files_with_errors.add(os.path.basename(file_path))
                            else:
                                bl_idname_map[bl_idname] = (file_path, class_name)

                    if checker.issues:
                        report_lines.append(os.path.basename(file_path))
                        for issue in checker.issues:
                            report_lines.append(f"  {issue.level.value}: Line {issue.line}: {issue.message}")
                            if issue.level == IssueLevel.ERROR:
                                files_with_errors.add(os.path.basename(file_path))
                            elif issue.level == IssueLevel.WARNING:
                                files_with_warnings.add(os.path.basename(file_path))
                        report_lines.append("")

                    # Collect class information
                    all_class_info.extend(checker.class_names)

    # Add duplicate bl_idname section to report
    output_file = os.path.join(directory, "addon_compliance_report.txt")
    write_report_to_file(report_lines, output_file, total_files, all_class_info,
                         files_with_errors, files_with_warnings, duplicate_bl_idnames)
    print(f"Report written to {output_file}")
    return len(files_with_errors)
#endregion

#region REPORT
def write_report_to_file(report_lines: List[str], output_file: str, total_files: int = 0,
                         class_info: List[Tuple[str, str, str]] = None,
                         files_with_errors: Set[str] = None,
                         files_with_warnings: Set[str] = None,
                         duplicate_bl_idnames: Set[str] = None):
    """Write the report lines to a file with improved formatting."""
    if files_with_errors is None:
        files_with_errors = set()
    if files_with_warnings is None:
        files_with_warnings = set()
    if class_info is None:
        class_info = []
    if duplicate_bl_idnames is None:
        duplicate_bl_idnames = set()

    with open(output_file, 'w', encoding='utf-8') as f:
        # Write header
        f.write("Blender Addon Compliance Report\n")
        f.write("========================================\n")
        f.write(f"Generated on: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("========================================\n\n")

        # Write summary
        f.write("Summary\n")
        f.write("----------------------------------------\n")
        error_files = len(files_with_errors)
        warning_files = len(files_with_warnings - files_with_errors)
        passed_files = total_files - (error_files + warning_files)

        f.write(f"Total Files Reviewed: {total_files}\n")
        f.write(f"Files with No Issues: {passed_files}\n")
        f.write(f"Files with Errors: {error_files}\n")
        f.write(f"Files with Warnings: {warning_files}\n\n")

        # Write issues if any exist
        if report_lines:
            f.write("Issues by File\n")
            f.write("========================================\n\n")
            current_file = None
            for line in report_lines:
                if not line.strip():
                    continue
                if not line.startswith(('  ERROR:', '  WARNING:')):
                    # This is a file name
                    current_file = line
                    f.write(f"\nFile: {current_file}\n")
                    f.write("-" * (len(current_file) + 6) + "\n\n")
                else:
                    f.write(line + "\n")
            f.write("\n")

        # Write class information if available
        if class_info:
            # Write duplicate bl_idname section if any found
            # (duplicate set is computed once in check_directory and passed in)
            if duplicate_bl_idnames:
                f.write("\nDuplicate bl_idname Values\n")
                f.write("========================================\n")
                for idname in sorted(duplicate_bl_idnames):
                    f.write(f"\nbl_idname: {idname}\n")
                    f.write("Used in:\n")
                    for name, id_, label in class_info:
                        if id_ == idname:
                            f.write(f"  - Class: {name}\n")
                f.write("\n")

            f.write("\nClass Information Summary\n")
            f.write("========================================\n")
            f.write("\nOperator Classes:\n")
            f.write("----------------------------------------\n")
            for name, idname, label in class_info:
                if "_OT_" in name:
                    f.write(f"Class: {name}\n")
                    f.write(f"  bl_idname: {idname or 'Not specified'}\n")
                    f.write(f"  bl_label: {label or 'Not specified'}\n")
                    if idname in duplicate_bl_idnames:
                        f.write("  WARNING: Duplicate bl_idname\n")
                    f.write("\n")
            
            f.write("\nPanel Classes:\n")
            f.write("----------------------------------------\n")
            for name, idname, label in class_info:
                if "_PT_" in name:
                    f.write(f"Class: {name}\n")
                    f.write(f"  bl_idname: {idname or 'Not specified'}\n")
                    f.write(f"  bl_label: {label or 'Not specified'}\n")
                    if idname in duplicate_bl_idnames:
                        f.write("  WARNING: Duplicate bl_idname\n")
                    f.write("\n")
            
            f.write("\nProperty Group Classes:\n")
            f.write("----------------------------------------\n")
            for name, idname, label in class_info:
                if "_PG_" in name:
                    f.write(f"Class: {name}\n")
                    if idname:
                        f.write(f"  bl_idname: {idname}\n")
                        if idname in duplicate_bl_idnames:
                            f.write("  WARNING: Duplicate bl_idname\n")
                    if label:
                        f.write(f"  bl_label: {label}\n")
                    f.write("\n")
#endregion

#region CLI
if __name__ == "__main__":
    if len(sys.argv) > 1:
        directory = sys.argv[1]
        if os.path.isdir(directory):
            error_count = check_directory(directory)
            # Exit non-zero if any files had errors (suitable for CI / pre-commit).
            sys.exit(1 if error_count else 0)
        else:
            print(f"Error: {directory} is not a valid directory")
            sys.exit(2)
    else:
        print("Please provide a directory path as an argument")
        sys.exit(2)
#endregion
