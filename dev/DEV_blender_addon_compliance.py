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
MENU_FUNC_PREFIXES = {'menu_func_export', 'menu_func_import', 'menu_func'}
ALLOWED_GLOBAL_FUNCTIONS = {'register', 'unregister'} | MENU_FUNC_PREFIXES

import os
import ast
import sys
from typing import List, Dict, Set, Tuple
from dataclasses import dataclass
from enum import Enum
import datetime

def get_full_name(node: ast.AST) -> str:
    """Recursively extract the full dotted name from an AST node."""
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        return get_full_name(node.value) + "." + node.attr
    return ""

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

class BlenderAddonChecker:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.issues: List[ComplianceIssue] = []
        self.tree = None
        self.global_functions: Set[str] = set()
        self.allowed_global_functions = ALLOWED_GLOBAL_FUNCTIONS
        self.required_bl_options = REQUIRED_BL_OPTIONS
        # Track class and node names
        self.class_names: List[Tuple[str, str, str]] = []  # (class_name, bl_idname, bl_label)
        self.node_names: List[Tuple[str, str]] = []  # (class_name, bl_label)

    def add_issue(self, level: IssueLevel, line: int, message: str):
        """Helper method to add an issue with consistent formatting."""
        self.issues.append(ComplianceIssue(
            level,
            message,
            line,
            self.file_path
        ))

    def load_file(self) -> bool:
        """Load and parse the Python file."""
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.tree = ast.parse(content)
            return True
        except Exception as e:
            self.issues.append(ComplianceIssue(
                IssueLevel.ERROR,
                f"Failed to parse file: {str(e)}",
                0,
                self.file_path
            ))
            return False

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
                                if isinstance(key, ast.Str):
                                    found_keys.add(key.s)
                            
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
            if isinstance(node, ast.FunctionDef):
                # Add all global functions to the set
                self.global_functions.add(node.name)
                # Skip register and unregister functions
                if node.name in ['register', 'unregister']:
                    continue
                # Skip menu registration functions if they start with allowed prefixes
                if any(node.name.startswith(prefix) for prefix in MENU_FUNC_PREFIXES):
                    continue
                # All other global functions are flagged
                self.issues.append(ComplianceIssue(
                    IssueLevel.ERROR,
                    f"Global function '{node.name}' found. Only register/unregister (and allowed menu functions) should be global",
                    node.lineno,
                    self.file_path
                ))

    def check_register_unregister(self):
        """Check if register and unregister functions are properly implemented."""
        has_register = False
        has_unregister = False
        
        # First check if they exist at module level
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
        if filename.startswith(f"{ADDON_PREFIX}_"):
            parts = filename.split('_')
            if len(parts) >= 3:
                addon_type = parts[2]  # Get the type part (e.g., 'TEX', 'GEN', etc.)

        for node in ast.walk(self.tree):
            if isinstance(node, ast.ClassDef):
                # Store class name for later analysis: [class_name, bl_idname, bl_label]
                class_info = [node.name, None, None]
                
                # Determine class type using full dotted name extraction
                is_operator = False
                is_panel = False
                is_property_group = False
                
                for base in node.bases:
                    base_name = get_full_name(base)
                    if "Operator" in base_name:
                        is_operator = True
                    elif "Panel" in base_name:
                        is_panel = True
                    elif "PropertyGroup" in base_name:
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

                # Check class attributes for bl_idname, bl_label, etc.
                for child in node.body:
                    if isinstance(child, ast.Assign):
                        for target in child.targets:
                            if isinstance(target, ast.Name):
                                if target.id == 'bl_idname':
                                    if isinstance(child.value, ast.Constant):
                                        bl_idname = child.value.value
                                        class_info[1] = bl_idname
                                        
                                        # Check bl_idname format
                                        if is_operator:
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
                                        elif is_panel:
                                            if not bl_idname.startswith(f'{PROJECT_PREFIX}_PT_'):
                                                self.add_issue(
                                                    IssueLevel.ERROR,
                                                    child.lineno,
                                                    f"Panel bl_idname '{bl_idname}' must start with '{PROJECT_PREFIX}_PT_'"
                                                )
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
                                elif target.id == 'bl_category':
                                    if isinstance(child.value, ast.Constant):
                                        bl_category = child.value.value
                                        
                                        # For panels, check if bl_category matches PROJECT_PREFIX
                                        if is_panel and bl_category != PROJECT_PREFIX:
                                            self.add_issue(
                                                IssueLevel.ERROR,
                                                child.lineno,
                                                f"Panel bl_category must be '{PROJECT_PREFIX}', found '{bl_category}'"
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
                    base_name = get_full_name(base)
                    if "Operator" in base_name:
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
                                            bl_options_set = {elt.s for elt in child.value.elts if isinstance(elt, ast.Str)}
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
                                def has_return_statement(node):
                                    if isinstance(node, ast.Return):
                                        return True
                                    for child_node in ast.iter_child_nodes(node):
                                        if has_return_statement(child_node):
                                            return True
                                    return False
                                
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
                    base_name = get_full_name(base)
                    if "Panel" in base_name:
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
                            if isinstance(node.value.func, ast.Name):
                                if node.value.func.id.endswith('Property'):
                                    has_name = False
                                    has_description = False
                                    for keyword in node.value.keywords:
                                        if keyword.arg == 'name':
                                            has_name = True
                                        elif keyword.arg == 'description':
                                            has_description = True
                                    
                                    if not has_name:
                                        self.issues.append(ComplianceIssue(
                                            IssueLevel.WARNING,
                                            f"Property '{target.id}' missing 'name' parameter",
                                            node.lineno,
                                            self.file_path
                                        ))
                                    
                                    if not has_description:
                                        self.issues.append(ComplianceIssue(
                                            IssueLevel.WARNING,
                                            f"Property '{target.id}' missing 'description' parameter",
                                            node.lineno,
                                            self.file_path
                                        ))

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

    def run_all_checks(self):
        """Run all compliance checks."""
        if not self.load_file():
            return
        
        self.check_bl_info()
        self.check_global_functions()
        self.check_register_unregister()
        self.check_class_naming()
        self.check_operator_requirements()
        self.check_panel_requirements()
        self.check_property_definitions()
        self.check_import_style()

    def print_report(self):
        """Generate a formatted report of all issues."""
        report_lines = []
        
        if not self.issues:
            report_lines.append(f"\n✅ No issues found in {os.path.basename(self.file_path)}")
            return report_lines

        report_lines.append(f"\nReport for {os.path.basename(self.file_path)}:")
        report_lines.append("-" * 80)
        
        for level in IssueLevel:
            level_issues = [issue for issue in self.issues if issue.level == level]
            if level_issues:
                report_lines.append(f"\n{level.value}S:")
                for issue in level_issues:
                    report_lines.append(f"  Line {issue.line}: {issue.message}")
        
        return report_lines

def check_directory(directory: str):
    """Check all .py files in a directory for addon compliance."""
    if not os.path.exists(directory):
        print(f"Directory not found: {directory}")
        return

    report_lines = []
    all_class_info = []
    total_files = 0
    bl_idname_map = {}  # Maps bl_idname to (file_path, class_name) for duplicate checking

    for root, dirs, files in os.walk(directory):
        # Skip ignored directories
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRECTORIES]
        
        for file in files:
            if file.endswith('.py'):
                total_files += 1
                file_path = os.path.join(root, file)
                checker = BlenderAddonChecker(file_path)
                
                if checker.load_file():
                    checker.check_bl_info()
                    checker.check_global_functions()
                    checker.check_register_unregister()
                    checker.check_class_naming()
                    
                    # Check for duplicate bl_idname values
                    for class_name, bl_idname, bl_label in checker.class_names:
                        if bl_idname:
                            if bl_idname in bl_idname_map:
                                prev_file, prev_class = bl_idname_map[bl_idname]
                                report_lines.append(os.path.basename(file_path))
                                report_lines.append(f"  ERROR: Line 0: Duplicate bl_idname '{bl_idname}' in class '{class_name}' conflicts with '{prev_class}' in file '{os.path.basename(prev_file)}'")
                                report_lines.append("")
                            else:
                                bl_idname_map[bl_idname] = (file_path, class_name)
                    
                    if checker.issues:
                        report_lines.append(os.path.basename(file_path))
                        for issue in checker.issues:
                            report_lines.append(f"  {issue.level.value}: Line {issue.line}: {issue.message}")
                        report_lines.append("")
                    
                    # Collect class information
                    all_class_info.extend(checker.class_names)

    # Add duplicate bl_idname section to report
    output_file = os.path.join(directory, "addon_compliance_report.txt")
    write_report_to_file(report_lines, output_file, total_files, all_class_info)
    print(f"Report written to {output_file}")

def write_report_to_file(report_lines: List[str], output_file: str, total_files: int = 0, class_info: List[Tuple[str, str, str]] = None):
    """Write the report lines to a file with improved formatting."""
    with open(output_file, 'w', encoding='utf-8') as f:
        # Write header
        f.write("Blender Addon Compliance Report\n")
        f.write("========================================\n")
        f.write(f"Generated on: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("========================================\n\n")

        # Write summary
        f.write("Summary\n")
        f.write("----------------------------------------\n")
        error_files = len(set(line.split(':')[0] for line in report_lines if "ERROR:" in line))
        warning_files = len(set(line.split(':')[0] for line in report_lines if "WARNING:" in line))
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
        if class_info and class_info:
            # First collect all bl_idnames to check for duplicates
            bl_idname_map = {}
            duplicate_bl_idnames = set()
            for name, idname, label in class_info:
                if idname:
                    if idname in bl_idname_map:
                        duplicate_bl_idnames.add(idname)
                    bl_idname_map[idname] = name

            # Write duplicate bl_idname section if any found
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

if __name__ == "__main__":
    if len(sys.argv) > 1:
        directory = sys.argv[1]
        if os.path.isdir(directory):
            check_directory(directory)
        else:
            print(f"Error: {directory} is not a valid directory")
    else:
        print("Please provide a directory path as an argument")
