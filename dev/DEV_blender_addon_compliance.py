"""
Blender Addon Compliance Checker
-------------------------------
This script checks Blender addon Python files for compliance with best practices and conventions.
It performs various checks including:
- Ensuring only register/unregister and menu functions are global
- Checking for proper class organization
- Verifying required addon metadata
- Checking Naming conventions
"""

PROJECT_PREFIX = "ZENV"
ADDON_PREFIX = "z_blender"

# Class type prefixes
OPERATOR_PREFIX = "_OT_"  # For operator classes
PANEL_PREFIX = "_PT_"     # For panel classes
PROP_GROUP_PREFIX = "_PG_"  # For property group classes

# Menu function prefixes
MENU_FUNC_PREFIXES = {'menu_func_export', 'menu_func_import', 'menu_func'}

# Required operator options
REQUIRED_BL_OPTIONS = {'REGISTER', 'UNDO'}

# Required bl_info keys
REQUIRED_BL_INFO_KEYS = {'name', 'author', 'version', 'blender', 'location', 'description', 'category'}

# Allowed global functions
ALLOWED_GLOBAL_FUNCTIONS = {'register', 'unregister'} | MENU_FUNC_PREFIXES

import os
import ast
import sys
from typing import List, Dict, Set, Tuple
from dataclasses import dataclass
from enum import Enum
import datetime

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
        self.class_names: List[Tuple[str, str]] = []  # (class_name, bl_idname)
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
        """Check for global functions. Only register/unregister should be global."""
        self.global_functions.clear()  # Reset the set before checking
        for node in self.tree.body:
            if isinstance(node, ast.FunctionDef):
                # Add all global functions to the set
                self.global_functions.add(node.name)
                # Skip register and unregister functions
                if node.name in ['register', 'unregister']:
                    continue
                # Skip menu registration functions
                if node.name in MENU_FUNC_PREFIXES:
                    continue
                # All other global functions are flagged
                self.issues.append(ComplianceIssue(
                    IssueLevel.ERROR,
                    f"Global function '{node.name}' found. Only register/unregister should be global",
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
                # Store class name for later analysis
                class_info = [node.name, None, None]  # [class_name, bl_idname, bl_label]
                
                # Check if this is a Panel class
                is_panel = False
                for base in node.bases:
                    if isinstance(base, ast.Name) and base.id.endswith('Panel'):
                        is_panel = True
                        break

                # Check class prefix
                if not node.name.startswith(PROJECT_PREFIX):
                    self.add_issue(
                        IssueLevel.WARNING,
                        node.lineno,
                        f"Class '{node.name}' should start with {PROJECT_PREFIX}_ prefix for project consistency"
                    )

                # Check class attributes
                for child in node.body:
                    if isinstance(child, ast.Assign):
                        for target in child.targets:
                            if isinstance(target, ast.Name):
                                if target.id == 'bl_idname':
                                    if isinstance(child.value, ast.Constant):
                                        bl_idname = child.value.value
                                        class_info[1] = bl_idname
                                        
                                        # Check bl_idname prefix for operators
                                        if OPERATOR_PREFIX in node.name and not bl_idname.startswith(f'{PROJECT_PREFIX.lower()}.'):
                                            self.add_issue(
                                                IssueLevel.ERROR,
                                                child.lineno,
                                                f"Operator bl_idname '{bl_idname}' must start with '{PROJECT_PREFIX.lower()}.' prefix"
                                            )
                                elif target.id == 'bl_label':
                                    if isinstance(child.value, ast.Constant):
                                        bl_label = child.value.value
                                        class_info[2] = bl_label
                                        
                                        # For panels, check if bl_label starts with addon type
                                        if is_panel and addon_type:
                                            if not bl_label.startswith(f"{addon_type} "):
                                                self.add_issue(
                                                    IssueLevel.ERROR,
                                                    child.lineno,
                                                    f"Panel bl_label '{bl_label}' must start with '{addon_type} ' prefix"
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
                # Store the class info
                self.class_names.append(tuple(class_info))
                
                # Check prefix conventions
                if any(node.name.startswith(prefix) for prefix in ['OBJECT_', 'MESH_', 'MATERIAL_']):
                    if not node.name.startswith(('OBJECT_OT_', 'MESH_OT_', 'MATERIAL_OT_')):
                        self.add_issue(
                            IssueLevel.WARNING,
                            node.lineno,
                            f"Class '{node.name}' might need _OT_ in name for operator"
                        )
                
                # Check ZENV prefix consistency
                if not node.name.startswith(f'{PROJECT_PREFIX}_'):
                    self.add_issue(
                        IssueLevel.WARNING,
                        node.lineno,
                        f"Class '{node.name}' should start with {PROJECT_PREFIX}_ prefix for project consistency"
                    )

    def check_operator_requirements(self):
        """Check if operators have required attributes and methods."""
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ClassDef):
                # Check if this is an operator class
                if any(base.id == 'Operator' for base in node.bases if isinstance(base, ast.Name)):
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
                                    elif target.id == 'bl_label':
                                        found_bl_label = True
                                    elif target.id == 'bl_options':
                                        found_bl_options = True
                                        # Check if REGISTER and UNDO are in bl_options
                                        if isinstance(child.value, ast.Set):
                                            options = {elt.s for elt in child.value.elts if isinstance(elt, ast.Str)}
                                            missing_options = REQUIRED_BL_OPTIONS - options
                                            if missing_options:
                                                self.issues.append(ComplianceIssue(
                                                    IssueLevel.WARNING,
                                                    f"Operator missing recommended bl_options: {', '.join(missing_options)}",
                                                    child.lineno,
                                                    self.file_path
                                                ))
                        elif isinstance(child, ast.FunctionDef):
                            if child.name == 'execute':
                                has_execute = True
                                # Check execute return value
                                for stmt in child.body:
                                    if isinstance(stmt, ast.Return):
                                        if not (isinstance(stmt.value, (ast.Dict, ast.Set))):
                                            self.issues.append(ComplianceIssue(
                                                IssueLevel.ERROR,
                                                "execute() must return a set with status (e.g., {'FINISHED'})",
                                                stmt.lineno,
                                                self.file_path
                                            ))
                    
                    if not has_docstring:
                        self.issues.append(ComplianceIssue(
                            IssueLevel.WARNING,
                            f"Operator class '{node.name}' missing docstring",
                            node.lineno,
                            self.file_path
                        ))
                    
                    if not found_bl_idname:
                        self.issues.append(ComplianceIssue(
                            IssueLevel.ERROR,
                            f"Operator '{node.name}' missing bl_idname",
                            node.lineno,
                            self.file_path
                        ))
                    
                    if not found_bl_label:
                        self.issues.append(ComplianceIssue(
                            IssueLevel.ERROR,
                            f"Operator '{node.name}' missing bl_label",
                            node.lineno,
                            self.file_path
                        ))
                        
                    if not has_execute:
                        self.issues.append(ComplianceIssue(
                            IssueLevel.ERROR,
                            f"Operator '{node.name}' missing execute() method",
                            node.lineno,
                            self.file_path
                        ))

    def check_panel_requirements(self):
        """Check if panels have required attributes."""
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ClassDef):
                # Check if this is a panel class
                if any(base.id == 'Panel' for base in node.bases if isinstance(base, ast.Name)):
                    # Required attributes
                    found_bl_label = False
                    found_space_type = False
                    found_region_type = False
                    has_draw = False
                    has_docstring = bool(ast.get_docstring(node))
                    
                    for child in node.body:
                        if isinstance(child, ast.Assign):
                            for target in child.targets:
                                if isinstance(target, ast.Name):
                                    if target.id == 'bl_label':
                                        found_bl_label = True
                                    elif target.id == 'bl_space_type':
                                        found_space_type = True
                                    elif target.id == 'bl_region_type':
                                        found_region_type = True
                        elif isinstance(child, ast.FunctionDef):
                            if child.name == 'draw':
                                has_draw = True
                                # Check if draw method has context parameter
                                if not child.args.args or child.args.args[1].arg != 'context':
                                    self.issues.append(ComplianceIssue(
                                        IssueLevel.ERROR,
                                        "draw() method must have context parameter",
                                        child.lineno,
                                        self.file_path
                                    ))
                    
                    if not has_docstring:
                        self.issues.append(ComplianceIssue(
                            IssueLevel.WARNING,
                            f"Panel class '{node.name}' missing docstring",
                            node.lineno,
                            self.file_path
                        ))
                    
                    if not found_bl_label:
                        self.issues.append(ComplianceIssue(
                            IssueLevel.ERROR,
                            f"Panel '{node.name}' missing bl_label",
                            node.lineno,
                            self.file_path
                        ))
                    
                    if not found_space_type:
                        self.issues.append(ComplianceIssue(
                            IssueLevel.ERROR,
                            f"Panel '{node.name}' missing bl_space_type",
                            node.lineno,
                            self.file_path
                        ))
                        
                    if not found_region_type:
                        self.issues.append(ComplianceIssue(
                            IssueLevel.ERROR,
                            f"Panel '{node.name}' missing bl_region_type",
                            node.lineno,
                            self.file_path
                        ))
                        
                    if not has_draw:
                        self.issues.append(ComplianceIssue(
                            IssueLevel.ERROR,
                            f"Panel '{node.name}' missing draw() method",
                            node.lineno,
                            self.file_path
                        ))

    def check_property_definitions(self):
        """Check property definitions for best practices."""
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        if isinstance(node.value, ast.Call):
                            if isinstance(node.value.func, ast.Name):
                                if node.value.func.id.endswith('Property'):
                                    # Check if property has name and description
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
                # Check for wildcard imports
                if node.names[0].name == '*':
                    self.issues.append(ComplianceIssue(
                        IssueLevel.WARNING,
                        f"Avoid wildcard imports from {node.module}",
                        node.lineno,
                        self.file_path
                    ))

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

def check_directory(directory: str) -> List[str]:
    """Check all .py files in a directory for addon compliance."""
    all_report_lines = []
    all_report_lines.append(f"Blender Addon Compliance Report")
    all_report_lines.append("=" * 40)
    all_report_lines.append(f"Generated on: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    all_report_lines.append(f"Checking directory: {directory}")
    all_report_lines.append("=" * 40 + "\n")
    
    # Collect all class names across files
    all_class_names = []
    bl_idname_map = {}  # Map bl_idname to list of (class_name, file_path) tuples
    
    # First pass: collect all names
    for root, dirs, files in os.walk(directory):
        # Skip backup and removed directories
        dirs[:] = [d for d in dirs if d.lower() not in {'backup', 'removed'}]
        
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                checker = BlenderAddonChecker(file_path)
                checker.load_file()
                checker.check_class_naming()
                
                rel_path = os.path.relpath(file_path, directory)
                for class_name, bl_idname, bl_label in checker.class_names:
                    all_class_names.append((class_name, bl_idname, bl_label, rel_path))
                    if bl_idname:
                        if bl_idname not in bl_idname_map:
                            bl_idname_map[bl_idname] = []
                        bl_idname_map[bl_idname].append((class_name, rel_path))
    
    # Add naming convention summary to report
    all_report_lines.append("\nNaming Convention Summary")
    all_report_lines.append("=" * 40)
    
    # Group classes by type
    class_types = {
        'Operator': [],
        'Panel': [],
        'PropertyGroup': [],
        'Other': []
    }
    
    for class_name, bl_idname, bl_label, file_path in all_class_names:
        if OPERATOR_PREFIX in class_name:
            class_types['Operator'].append((class_name, bl_idname, bl_label, file_path))
        elif PANEL_PREFIX in class_name:
            class_types['Panel'].append((class_name, bl_idname, bl_label, file_path))
        elif PROP_GROUP_PREFIX in class_name:
            class_types['PropertyGroup'].append((class_name, bl_idname, bl_label, file_path))
        else:
            class_types['Other'].append((class_name, bl_idname, bl_label, file_path))
    
    # Report classes by type
    for type_name, classes in class_types.items():
        if classes:
            all_report_lines.append(f"\n{type_name} Classes:")
            all_report_lines.append("-" * 40)
            for class_name, bl_idname, bl_label, file_path in sorted(classes):
                info = [f"  {class_name}"]
                if bl_idname:
                    info.append(f"(bl_idname: {bl_idname})")
                if bl_label:
                    info.append(f"(bl_label: {bl_label})")
                info.append(f"[{file_path}]")
                all_report_lines.append(" ".join(info))
    
    # Check for duplicate bl_idnames
    duplicates = {k: v for k, v in bl_idname_map.items() if len(v) > 1}
    if duplicates:
        all_report_lines.append("\nDuplicate bl_idname Identifiers Found:")
        all_report_lines.append("-" * 40)
        for bl_idname, classes in duplicates.items():
            all_report_lines.append(f"\n  bl_idname: {bl_idname}")
            for class_name, file_path in classes:
                all_report_lines.append(f"    - {class_name} in {file_path}")
    
    # Now run the regular compliance checks
    total_files = 0
    files_with_errors = 0
    files_with_warnings = 0
    total_errors = 0
    total_warnings = 0
    
    for root, dirs, files in os.walk(directory):
        # Remove skipped directories
        dirs[:] = [d for d in dirs if d.lower() not in {'backup', 'removed'}]
        
        for file in files:
            if file.endswith('.py'):
                total_files += 1
                file_path = os.path.join(root, file)
                
                # Get relative path from base directory
                rel_path = os.path.relpath(file_path, directory)
                
                checker = BlenderAddonChecker(file_path)
                checker.run_all_checks()
                
                # Count issues
                errors = len([i for i in checker.issues if i.level == IssueLevel.ERROR])
                warnings = len([i for i in checker.issues if i.level == IssueLevel.WARNING])
                if errors > 0:
                    files_with_errors += 1
                    total_errors += errors
                if warnings > 0:
                    files_with_warnings += 1
                    total_warnings += warnings
                
                # Add relative path to report
                if not checker.issues:
                    all_report_lines.append(f"\n✅ No issues found in {rel_path}")
                else:
                    all_report_lines.append(f"\nReport for {rel_path}:")
                    all_report_lines.append("-" * 80)
                    
                    # Group issues by level
                    for level in IssueLevel:
                        level_issues = [issue for issue in checker.issues if issue.level == level]
                        if level_issues:
                            all_report_lines.append(f"\n{level.value}S:")
                            for issue in level_issues:
                                all_report_lines.append(f"  Line {issue.line}: {issue.message}")
    
    # Add summary at the end
    all_report_lines.append("\n" + "=" * 40)
    all_report_lines.append("SUMMARY")
    all_report_lines.append("-" * 40)
    all_report_lines.append(f"Total files checked: {total_files}")
    all_report_lines.append(f"Files with errors: {files_with_errors}")
    all_report_lines.append(f"Files with warnings: {files_with_warnings}")
    all_report_lines.append(f"Total errors found: {total_errors}")
    all_report_lines.append(f"Total warnings found: {total_warnings}")
    
    return all_report_lines

def write_report_to_file(report_lines: List[str], output_file: str):
    """Write the report lines to a file."""
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report_lines))
        print(f"Report written to: {output_file}")

if __name__ == "__main__":
    # Check if directory is provided as argument
    if len(sys.argv) > 1:
        directory = sys.argv[1]
    else:
        # Default to the addon directory relative to this script
        directory = os.path.join(os.path.dirname(os.path.dirname(__file__)), "addon")
    
    if not os.path.exists(directory):
        print(f"Error: Directory {directory} does not exist")
        sys.exit(1)
    
    # Generate the report
    report_lines = check_directory(directory)
    
    # Write to file
    output_file = os.path.join(os.path.dirname(__file__), "addon_compliance_report.txt")
    write_report_to_file(report_lines, output_file)
