#region DOC
"""
Blender Addon Metadata Validator

the project is using bl_info dict in the addons .py files
to hold additional information that is used by other tools
to generate dashbaord , documentation and webpage from the data

Extended bl_info Properties:
- status: "wip" | "working" | "stable" | "deprecated"
- approved: true | false
- sort_priority: string number for README ordering (legacy, superseded by addon_order)
- group: category grouping (e.g., "texture", "mesh", "generator")
- group_prefix: category prefix (e.g., "TEX", "MESH", "GEN")
- group_order: integer for ordering groups in docs/website/readme (spaced by 10)
- addon_order: integer for ordering addons within a group (spaced by 10)
- tags: list of searchable keywords
- description_short: concise one-liner for README
- description_medium: technical explanation for addon description
- description_long: detailed workflow guide for website
- image_overview: path to overview image for docs
- addon_image: representative image filename for the addon (e.g., "zenv_blender_MESH_helix.png")

style guide preferences:
- VERSION in "YYYYMMDD" format (e.g., "20251107")
- group_order and addon_order spaced by 10 (10, 20, 30...) so new
  groups/addons can be inserted between existing ones without renumbering

VERSION: 20260822
"""
#endregion

#region IMPORTS
import os
import sys
import ast
import re
from datetime import datetime
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
#endregion

#region DATAMODEL
# Dataclasses that hold parsed metadata and accumulated validation issues.
# These are the core data structures shared between the validator engine
# and the report generators.

@dataclass
class ValidationIssue:
    """Represents a validation issue found in bl_info."""
    severity: str  # "error", "warning", "info"
    field: str
    message: str

@dataclass
class AddonMetadata:
    """Parsed and validated addon metadata."""
    file_path: str
    file_name: str
    bl_info: Dict[str, Any]
    issues: List[ValidationIssue] = field(default_factory=list)
    folder_category: str = "main"  # "main", "wip", or "removed"

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == "error" for issue in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(issue.severity == "warning" for issue in self.issues)
#endregion


class AddonMetadataValidator:
    """Validates extended bl_info metadata across all addons."""

    #region CONFIG
    # Class-level constants defining the validation ruleset:
    # which fields are required, which are deprecated/legacy, which
    # status values are valid, and which directories to skip during scan.

    # Required standard bl_info fields
    REQUIRED_STANDARD_FIELDS = {
        "name", "blender", "category", "version", "description"
    }

    # Required extended fields for ZENV Project.
    # NOTE: `sort_priority` is intentionally NOT here - it is legacy and
    # superseded by `addon_order` (see LEGACY_FIELDS below).
    REQUIRED_EXTENDED_FIELDS = {
        "status", "approved", "group", "group_prefix",
        "group_order", "addon_order",
        "tags", "description_short", "description_medium", "description_long",
        "image_overview", "addon_image"
    }

    # Deprecated fields that should be removed
    DEPRECATED_FIELDS = {"author"}

    # Legacy fields superseded by newer ones. Presence triggers an info-level
    # notice encouraging migration; absence is NOT an error or warning.
    LEGACY_FIELDS = {"sort_priority"}

    # Valid status values
    VALID_STATUS_VALUES = {"wip", "working", "stable", "deprecated"}

    EXCLUDED_DIR_NAMES = {
        "backup",
        "backups",
        "_backup",
        "bak",
        "old",
        "archive",
        "archives",
        "__pycache__",
        ".git",
        ".svn",
        ".hg",
        ".idea",
        ".vscode",
        ".venv",
        "venv",
        ".mypy_cache",
        ".pytest_cache",
        "node_modules",
        "dist",
        "build",
    }
    #endregion

    #region INIT
    def __init__(self, addon_dir: str):
        self.addon_dir = os.path.abspath(addon_dir)
        self.addons: List[AddonMetadata] = []
    #endregion

    #region PARSE
    # Extract the bl_info dictionary from a Python source file using AST.
    # Only module-level assignments are considered - nested locals with
    # the same name are ignored. Distinct error paths handle I/O, encoding,
    # syntax, and non-literal-value failures.

    def extract_bl_info(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Extract bl_info dictionary from a Python file using AST."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source = f.read()
        except OSError as e:
            print(f"  ERROR: Could not read {os.path.basename(file_path)}: {e}")
            return None
        except UnicodeDecodeError as e:
            print(f"  ERROR: {os.path.basename(file_path)} is not valid UTF-8: {e}")
            return None

        try:
            tree = ast.parse(source, filename=file_path)
        except SyntaxError as e:
            print(f"  ERROR: Syntax error in {os.path.basename(file_path)}: {e}")
            return None

        # bl_info is always a module-level assignment; iterate only top-level
        # statements rather than walking the whole tree (which would also
        # descend into function/class bodies and could match a same-named
        # local variable).
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "bl_info":
                        try:
                            # Convert AST dict to Python dict
                            return ast.literal_eval(node.value)
                        except (ValueError, TypeError, SyntaxError) as e:
                            print(f"  ERROR: bl_info in {os.path.basename(file_path)} is not a literal dict: {e}")
                            return None

        return None
    #endregion

    #region VALIDATE
    # Core validation engine: check a parsed bl_info dict against the
    # ruleset defined in CONFIG. Produces a list of ValidationIssue entries
    # with severity error / warning / info. This is the heart of the module.

    def validate_version_format(self, version: Any) -> bool:
        """Check if version is in YYYYMMDD format."""
        if not isinstance(version, str):
            return False

        # Must be exactly 8 digits
        if not re.match(r'^\d{8}$', version):
            return False

        # Must be a valid date
        try:
            datetime.strptime(version, '%Y%m%d')
            return True
        except ValueError:
            return False

    def validate_addon(self, file_path: str) -> AddonMetadata:
        """Validate a single addon file."""
        file_name = os.path.basename(file_path)
        bl_info = self.extract_bl_info(file_path)

        # Determine folder category
        folder_category = "main"
        normalized_path = file_path.replace('\\', '/')
        if '/wip/' in normalized_path:
            folder_category = "wip"
        elif '/removed/' in normalized_path:
            folder_category = "removed"

        metadata = AddonMetadata(
            file_path=file_path,
            file_name=file_name,
            bl_info=bl_info or {},
            folder_category=folder_category
        )

        if not bl_info:
            metadata.issues.append(ValidationIssue(
                severity="error",
                field="bl_info",
                message="No bl_info dictionary found in file"
            ))
            return metadata

        #region V_DEPREC
        # Deprecated fields that must be removed entirely.
        for field in sorted(self.DEPRECATED_FIELDS):
            if field in bl_info:
                metadata.issues.append(ValidationIssue(
                    severity="error",
                    field=field,
                    message=f"Deprecated field '{field}' must be removed"
                ))
        #endregion

        #region V_STDREQ
        # Required standard Blender bl_info fields - missing any is an error.
        for field in sorted(self.REQUIRED_STANDARD_FIELDS):
            if field not in bl_info:
                metadata.issues.append(ValidationIssue(
                    severity="error",
                    field=field,
                    message=f"Required standard field '{field}' is missing"
                ))
        #endregion

        #region V_VERSION
        # Version must be a string in YYYYMMDD format (ZENV convention,
        # overriding Blender's default tuple shape).
        if "version" in bl_info:
            if not self.validate_version_format(bl_info["version"]):
                metadata.issues.append(ValidationIssue(
                    severity="error",
                    field="version",
                    message=f"Version must be in YYYYMMDD format (e.g., '20251107'), got: {bl_info['version']}"
                ))
        #endregion

        #region V_EXTREQ
        # Required extended ZENV fields - missing any is a warning
        # (the addon still works in Blender, but downstream tooling
        # like the dashboard/docs generators will be incomplete).
        for field in sorted(self.REQUIRED_EXTENDED_FIELDS):
            if field not in bl_info:
                metadata.issues.append(ValidationIssue(
                    severity="warning",
                    field=field,
                    message=f"Extended field '{field}' is missing (required for Project)"
                ))
        #endregion

        #region V_LEGACY
        # Legacy fields superseded by newer ones. Presence is informational
        # (encourage migration); absence is fine. Type-check only when present.
        for field in sorted(self.LEGACY_FIELDS):
            if field in bl_info:
                value = bl_info[field]
                if not isinstance(value, str):
                    metadata.issues.append(ValidationIssue(
                        severity="warning",
                        field=field,
                        message=f"Legacy field '{field}' should be string, got: {type(value).__name__}"
                    ))
                else:
                    metadata.issues.append(ValidationIssue(
                        severity="info",
                        field=field,
                        message=f"Legacy field '{field}' is present; superseded by 'addon_order' and may be removed"
                    ))
        #endregion

        #region V_TYPES
        # Type and value constraints on individual fields:
        # status enum, approved bool, order ints (with bool guard),
        # tags list/tuple, group_prefix <-> filename consistency,
        # and addon_image string check.
        if "status" in bl_info:
            if bl_info["status"] not in self.VALID_STATUS_VALUES:
                metadata.issues.append(ValidationIssue(
                    severity="error",
                    field="status",
                    message=f"Invalid status '{bl_info['status']}'. Must be one of: {', '.join(sorted(self.VALID_STATUS_VALUES))}"
                ))

        if "approved" in bl_info:
            if not isinstance(bl_info["approved"], bool):
                metadata.issues.append(ValidationIssue(
                    severity="error",
                    field="approved",
                    message=f"Field 'approved' must be boolean (True/False), got: {type(bl_info['approved']).__name__}"
                ))

        # Validate group_order / addon_order are integers
        for order_field in ("group_order", "addon_order"):
            if order_field in bl_info:
                v = bl_info[order_field]
                if not isinstance(v, int) or isinstance(v, bool):
                    metadata.issues.append(ValidationIssue(
                        severity="warning",
                        field=order_field,
                        message=f"Field '{order_field}' should be int, got: {type(v).__name__}"
                    ))

        if "tags" in bl_info:
            if not isinstance(bl_info["tags"], (list, tuple)):
                metadata.issues.append(ValidationIssue(
                    severity="error",
                    field="tags",
                    message=f"Field 'tags' must be list or tuple, got: {type(bl_info['tags']).__name__}"
                ))

        # Validate group_prefix matches file naming
        if "group_prefix" in bl_info:
            prefix = bl_info["group_prefix"]
            if not file_name.startswith(f"z_blender_{prefix}_"):
                metadata.issues.append(ValidationIssue(
                    severity="warning",
                    field="group_prefix",
                    message=f"group_prefix '{prefix}' doesn't match filename prefix"
                ))

        # Validate addon_image is a string when present
        if "addon_image" in bl_info:
            if not isinstance(bl_info["addon_image"], str):
                metadata.issues.append(ValidationIssue(
                    severity="warning",
                    field="addon_image",
                    message=f"Field 'addon_image' should be string, got: {type(bl_info['addon_image']).__name__}"
                ))
        #endregion

        return metadata
    #endregion

    #region SCAN
    # Walk the addon directory, discover z_blender_*.py files (pruning
    # backup/VCS/cache dirs), and run validate_addon on each. Results
    # are stored in self.addons for later report generation.

    def scan_directory(self):
        """Scan addon directory and validate all Python files."""
        print("=" * 80)
        print("Scanning addon directory for metadata validation...")
        print("=" * 80)
        print(f"Directory: {self.addon_dir}\n")

        self.addons = []
        excluded_dir_names = {d.casefold() for d in self.EXCLUDED_DIR_NAMES}

        py_files = []
        for root, dirs, files in os.walk(self.addon_dir):
            dirs[:] = [
                d for d in dirs
                if d.casefold() not in excluded_dir_names
                and not d.startswith('.')
                and not d.casefold().startswith('backup')
                and not d.casefold().endswith('_backup')
            ]

            for file in files:
                if file.endswith('.py') and file.startswith('z_blender_'):
                    py_files.append(os.path.join(root, file))

        print(f"Found {len(py_files)} addon file(s)\n")

        for file_path in sorted(py_files):
            file_name = os.path.basename(file_path)
            print(f"Validating: {file_name}...", end=' ')

            metadata = self.validate_addon(file_path)
            self.addons.append(metadata)

            if metadata.has_errors:
                print("ERRORS")
            elif metadata.has_warnings:
                print("WARNINGS")
            else:
                print("OK")
    #endregion

    #region REPORT
    # Output layer: write a detailed text report to disk and print a
    # console summary. These are the "UI" of the tool - they consume
    # the validated self.addons list but perform no validation themselves.

    def generate_report(self, output_file: str):
        """Generate detailed validation report."""
        print(f"\nGenerating validation report...")

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("BLENDER ADDON METADATA VALIDATION REPORT\n")
            f.write("=" * 80 + "\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total Addons: {len(self.addons)}\n")

            error_count = sum(1 for a in self.addons if a.has_errors)
            warning_count = sum(1 for a in self.addons if a.has_warnings)
            # Addons with both errors and warnings must not be double-subtracted;
            # an addon is "OK" only if it has neither.
            ok_count = sum(1 for a in self.addons if not a.has_errors and not a.has_warnings)

            f.write(f"Status: {ok_count} OK, {warning_count} Warnings, {error_count} Errors\n")
            f.write("=" * 80 + "\n\n")

            # Write guidelines
            f.write("EXTENDED METADATA GUIDELINES\n")
            f.write("-" * 80 + "\n\n")
            f.write("Required Standard Fields:\n")
            for field in sorted(self.REQUIRED_STANDARD_FIELDS):
                f.write(f"  - {field}\n")
            f.write("\nRequired Extended Fields (ZENV Project):\n")
            for field in sorted(self.REQUIRED_EXTENDED_FIELDS):
                f.write(f"  - {field}\n")
            f.write("\nDeprecated Fields (Must Remove):\n")
            for field in sorted(self.DEPRECATED_FIELDS):
                f.write(f"  - {field}\n")
            f.write("\nLegacy Fields (Superseded - info notice when present):\n")
            for field in sorted(self.LEGACY_FIELDS):
                f.write(f"  - {field}\n")
            f.write("\nValid Status Values:\n")
            for status in sorted(self.VALID_STATUS_VALUES):
                f.write(f"  - {status}\n")
            f.write("\nVersion Format: YYYYMMDD (e.g., '20251107')\n")
            f.write("\n" + "=" * 80 + "\n\n")

            # Detailed results per addon
            f.write("VALIDATION RESULTS\n")
            f.write("=" * 80 + "\n\n")

            for addon in sorted(self.addons, key=lambda a: a.file_name):
                f.write(f"\n{addon.file_name}\n")
                f.write("-" * 80 + "\n")

                if not addon.issues:
                    f.write("Status: OK - All validations passed\n")
                else:
                    # Group by severity
                    errors = [i for i in addon.issues if i.severity == "error"]
                    warnings = [i for i in addon.issues if i.severity == "warning"]
                    infos = [i for i in addon.issues if i.severity == "info"]

                    if errors:
                        f.write(f"\nERRORS ({len(errors)}):\n")
                        for issue in errors:
                            f.write(f"  [{issue.field}] {issue.message}\n")

                    if warnings:
                        f.write(f"\nWARNINGS ({len(warnings)}):\n")
                        for issue in warnings:
                            f.write(f"  [{issue.field}] {issue.message}\n")

                    if infos:
                        f.write(f"\nINFO ({len(infos)}):\n")
                        for issue in infos:
                            f.write(f"  [{issue.field}] {issue.message}\n")

                # Show current bl_info for reference
                if addon.bl_info:
                    f.write(f"\nCurrent bl_info:\n")
                    for key in sorted(addon.bl_info.keys()):
                        value = addon.bl_info[key]
                        if isinstance(value, str) and len(value) > 60:
                            value = value[:57] + "..."
                        f.write(f"  {key}: {repr(value)}\n")

        print(f"Report saved: {output_file}")
        return output_file

    def generate_summary(self):
        """Print summary statistics to console."""
        print("\n" + "=" * 80)
        print("VALIDATION SUMMARY")
        print("=" * 80)

        total = len(self.addons)
        errors = sum(1 for a in self.addons if a.has_errors)
        warnings = sum(1 for a in self.addons if a.has_warnings)
        # An addon is "OK" only if it has neither errors nor warnings;
        # using total - errors - warnings would double-count addons with both.
        ok = sum(1 for a in self.addons if not a.has_errors and not a.has_warnings)

        print(f"Total Addons: {total}")
        print(f"  OK:       {ok}")
        print(f"  Warnings: {warnings}")
        print(f"  Errors:   {errors}")

        if errors > 0:
            print(f"\nAddons with errors:")
            for addon in self.addons:
                if addon.has_errors:
                    error_count = len([i for i in addon.issues if i.severity == "error"])
                    print(f"  - {addon.file_name} ({error_count} error(s))")

        print()
    #endregion


#region CLI
# Command-line entry point: parse argv, run the validator, write the
# report, print the summary, and exit non-zero if any addon has errors
# (so CI / pre-commit hooks can detect validation failure).

def main():
    # Determine target path
    if len(sys.argv) > 1:
        addon_dir = sys.argv[1]
    else:
        # Default to ../addon relative to this script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        addon_dir = os.path.join(script_dir, "..", "addon")
        print(f"INFO: No directory specified, using default: {addon_dir}\n")

    if not os.path.exists(addon_dir):
        print(f"ERROR: Directory '{addon_dir}' does not exist")
        sys.exit(1)

    # Run validation
    validator = AddonMetadataValidator(addon_dir)
    validator.scan_directory()

    # Generate report
    script_dir = os.path.dirname(os.path.abspath(__file__))
    report_file = os.path.join(script_dir, "addon_metadata_validation_report.txt")
    validator.generate_report(report_file)

    # Show summary
    validator.generate_summary()

    # Exit non-zero if any addon has errors so CI / pre-commit hooks can
    # detect validation failure. Warnings alone do not fail the run.
    if any(a.has_errors for a in validator.addons):
        sys.exit(1)

if __name__ == "__main__":
    main()
#endregion
