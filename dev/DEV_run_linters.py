"""
Multi-Linter Runner for Blender Addons
-------------------------------------
This script runs multiple linters (Ruff, Flake8, Black, Mypy, Pylint) on Python files
and generates a consolidated report.

Usage:
    python DEV_run_linters.py [target_directory]
    
If no directory is provided, defaults to ../addon relative to this script.
"""

import os
import sys
import subprocess
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Set
from dataclasses import dataclass
import json

@dataclass
class LinterResult:
    linter_name: str
    output: str
    return_code: int
    error: Optional[str] = None

class MultiLinterRunner:
    def __init__(self, target_path: str):
        self.target_path = os.path.abspath(target_path)
        self.results: Dict[str, List[LinterResult]] = {}
        self.available_linters: Set[str] = set()
        self.missing_linters: Set[str] = set()
        
        # Ensure output directory exists
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.output_dir = os.path.join(script_dir, "linter_reports")
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Check which linters are available
        self._check_linter_availability()

    def _check_linter_availability(self):
        """Check which linters are installed and available."""
        linters = ['black', 'ruff', 'flake8', 'mypy', 'pylint']
        
        print("=" * 80)
        print("Checking linter availability...")
        print("=" * 80)
        
        for linter in linters:
            try:
                result = subprocess.run(
                    [sys.executable, "-m", linter, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    self.available_linters.add(linter)
                    version = result.stdout.strip().split('\n')[0]
                    print(f"[OK] {linter:10} - {version}")
                else:
                    self.missing_linters.add(linter)
                    print(f"[--] {linter:10} - Not available")
            except Exception:
                self.missing_linters.add(linter)
                print(f"[--] {linter:10} - Not available")
        
        print("=" * 80)
        
        if self.missing_linters:
            print(f"\nWARNING: {len(self.missing_linters)} linter(s) not installed: {', '.join(sorted(self.missing_linters))}")
            print(f"\nTo install missing linters, run:")
            print(f"  pip install -r requirements-dev.txt")
            print(f"\nOr install individually:")
            for linter in sorted(self.missing_linters):
                print(f"  pip install {linter}")
            print()
        
        if not self.available_linters:
            print("\nERROR: No linters are available!")
            print("Please install at least one linter to continue.")
            sys.exit(1)
        
        print(f"Running with {len(self.available_linters)} available linter(s): {', '.join(sorted(self.available_linters))}\n")

    def run_command(self, command: List[str], timeout: int = 60) -> Tuple[int, str, Optional[str]]:
        """Run a command and return its output."""
        try:
            process = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return process.returncode, process.stdout, process.stderr
        except subprocess.TimeoutExpired:
            return 1, "", f"Command timed out after {timeout} seconds"
        except Exception as e:
            return 1, "", str(e)

    def run_black(self, file_path: str) -> LinterResult:
        """Run Black formatter check."""
        cmd = [sys.executable, "-m", "black", "--check", "--diff", file_path]
        return_code, output, error = self.run_command(cmd)
        return LinterResult("black", output or error or "", return_code)

    def run_ruff(self, file_path: str) -> LinterResult:
        """Run Ruff linter."""
        cmd = [sys.executable, "-m", "ruff", "check", file_path]
        return_code, output, error = self.run_command(cmd)
        return LinterResult("ruff", output or error or "", return_code)

    def run_flake8(self, file_path: str) -> LinterResult:
        """Run Flake8 linter."""
        cmd = [sys.executable, "-m", "flake8", file_path]
        return_code, output, error = self.run_command(cmd)
        return LinterResult("flake8", output or error or "", return_code)

    def run_mypy(self, file_path: str) -> LinterResult:
        """Run Mypy type checker."""
        cmd = [sys.executable, "-m", "mypy", "--strict", file_path]
        return_code, output, error = self.run_command(cmd)
        return LinterResult("mypy", output or error or "", return_code)

    def run_pylint(self, file_path: str) -> LinterResult:
        """Run Pylint."""
        cmd = [sys.executable, "-m", "pylint", file_path]
        return_code, output, error = self.run_command(cmd)
        return LinterResult("pylint", output or error or "", return_code)

    def process_file(self, file_path: str):
        """Run all available linters on a single file."""
        self.results[file_path] = []
        
        # Show which file we're processing
        file_name = os.path.basename(file_path)
        print(f"\n  Processing: {file_name}")
        
        # Only run available linters
        linter_map = {
            'black': self.run_black,
            'ruff': self.run_ruff,
            'flake8': self.run_flake8,
            'mypy': self.run_mypy,
            'pylint': self.run_pylint
        }
        
        for linter_name, linter_func in linter_map.items():
            if linter_name in self.available_linters:
                print(f"    Running {linter_name}...", end='', flush=True)
                result = linter_func(file_path)
                status = "OK" if result.return_code == 0 else "ISSUES"
                print(f" {status}")
                self.results[file_path].append(result)
        
        # Generate individual report for this file immediately
        self._generate_individual_report(file_path, self.results[file_path])

    def _generate_individual_report(self, file_path: str, results: List[LinterResult]):
        """Generate a detailed individual report for a single file."""
        file_name = os.path.basename(file_path)
        base_name = os.path.splitext(file_name)[0]
        report_file = os.path.join(self.output_dir, f"{base_name}_linter_report.txt")
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write(f"Linter Report: {file_name}\n")
            f.write("=" * 80 + "\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"File: {file_path}\n")
            f.write("=" * 80 + "\n\n")
            
            for result in results:
                f.write(f"\n{'=' * 80}\n")
                f.write(f"{result.linter_name.upper()} ANALYSIS\n")
                f.write(f"{'=' * 80}\n\n")
                
                if result.error:
                    f.write(f"ERROR: {result.error}\n\n")
                elif result.return_code == 0:
                    f.write(f"No issues found by {result.linter_name}.\n\n")
                else:
                    f.write(f"Issues found:\n\n")
                    f.write(result.output + "\n")
                
                # Add explanations for common issues
                f.write(f"\n{'-' * 80}\n")
                f.write(f"What to fix ({result.linter_name}):\n")
                f.write(f"{'-' * 80}\n")
                
                if result.linter_name == 'black':
                    f.write("Black is a code formatter. Issues indicate formatting inconsistencies.\n")
                    f.write("- Run 'black <filename>' to auto-format the file\n")
                    f.write("- Or use 'black --check' to see what would change\n")
                elif result.linter_name == 'ruff':
                    f.write("Ruff checks for code quality and style issues.\n")
                    f.write("- Fix issues manually or run 'ruff check --fix <filename>'\n")
                    f.write("- Common issues: unused imports, undefined names, line length\n")
                elif result.linter_name == 'flake8':
                    f.write("Flake8 checks PEP 8 style guide compliance.\n")
                    f.write("- E### codes: PEP 8 errors (formatting, whitespace)\n")
                    f.write("- W### codes: PEP 8 warnings\n")
                    f.write("- F### codes: PyFlakes errors (undefined names, unused imports)\n")
                elif result.linter_name == 'mypy':
                    f.write("Mypy performs static type checking.\n")
                    f.write("- Add type hints to functions: def func(x: int) -> str:\n")
                    f.write("- Use 'from typing import' for complex types\n")
                    f.write("- Consider adding '# type: ignore' for unavoidable issues\n")
                elif result.linter_name == 'pylint':
                    f.write("Pylint performs comprehensive code analysis.\n")
                    f.write("- C#### codes: Convention violations\n")
                    f.write("- R#### codes: Refactoring suggestions\n")
                    f.write("- W#### codes: Warnings\n")
                    f.write("- E#### codes: Errors\n")
                    f.write("- Add docstrings, improve naming, reduce complexity\n")
                
                f.write("\n")
        
        print(f"    Report saved: {base_name}_linter_report.txt")

    def process_directory(self):
        """Process all Python files in the target directory."""
        file_count = 0
        for root, _, files in os.walk(self.target_path):
            for file in files:
                if file.endswith('.py'):
                    file_path = os.path.join(root, file)
                    file_count += 1
                    try:
                        self.process_file(file_path)
                    except Exception as e:
                        print(f"\n  WARNING: Error processing {os.path.basename(file_path)}: {str(e)}")
        
        print(f"\n  Completed processing {file_count} files total.")

    def generate_summary_database(self):
        """Generate a condensed summary database of all linter results."""
        print("\nGenerating summary database...")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Text summary
        summary_file = os.path.join(self.output_dir, f"linter_summary_{timestamp}.txt")
        
        # Count issues per file per linter
        summary_data = {}
        for file_path, results in self.results.items():
            file_name = os.path.basename(file_path)
            summary_data[file_name] = {}
            
            for result in results:
                issue_count = 0
                if result.return_code != 0 and result.output:
                    # Count lines in output as rough issue count
                    issue_count = len([line for line in result.output.split('\n') if line.strip()])
                
                summary_data[file_name][result.linter_name] = {
                    'status': 'PASS' if result.return_code == 0 else 'FAIL',
                    'issue_count': issue_count
                }
        
        # Write text summary
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("LINTER SUMMARY DATABASE\n")
            f.write("=" * 80 + "\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total Files: {len(self.results)}\n")
            f.write(f"Linters Used: {', '.join(sorted(self.available_linters))}\n")
            f.write("=" * 80 + "\n\n")
            
            # Summary table
            f.write(f"{'File':<50} {'Black':<8} {'Ruff':<8} {'Flake8':<8} {'Mypy':<8} {'Pylint':<8}\n")
            f.write("-" * 100 + "\n")
            
            for file_name in sorted(summary_data.keys()):
                file_data = summary_data[file_name]
                short_name = file_name[:47] + "..." if len(file_name) > 50 else file_name
                
                black_status = file_data.get('black', {}).get('status', 'N/A')
                ruff_status = file_data.get('ruff', {}).get('status', 'N/A')
                flake8_status = file_data.get('flake8', {}).get('status', 'N/A')
                mypy_status = file_data.get('mypy', {}).get('status', 'N/A')
                pylint_status = file_data.get('pylint', {}).get('status', 'N/A')
                
                f.write(f"{short_name:<50} {black_status:<8} {ruff_status:<8} {flake8_status:<8} {mypy_status:<8} {pylint_status:<8}\n")
            
            f.write("\n" + "=" * 80 + "\n")
            f.write("DETAILED ISSUE COUNTS\n")
            f.write("=" * 80 + "\n\n")
            
            for file_name in sorted(summary_data.keys()):
                file_data = summary_data[file_name]
                total_issues = sum(data.get('issue_count', 0) for data in file_data.values())
                
                if total_issues > 0:
                    f.write(f"\n{file_name}:\n")
                    for linter in sorted(file_data.keys()):
                        count = file_data[linter].get('issue_count', 0)
                        if count > 0:
                            f.write(f"  {linter}: ~{count} issues\n")
        
        # Also save as JSON for programmatic access
        json_file = os.path.join(self.output_dir, f"linter_summary_{timestamp}.json")
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(summary_data, f, indent=2)
        
        print(f"Summary database saved: {summary_file}")
        print(f"JSON database saved: {json_file}")
        return summary_file

def main():
    # Determine target path
    if len(sys.argv) > 1:
        target_path = sys.argv[1]
    else:
        # Default to ../addon relative to this script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        target_path = os.path.join(script_dir, "..", "addon")
        print(f"INFO: No target directory specified, using default: {target_path}\n")
    
    # Validate path exists
    if not os.path.exists(target_path):
        print(f"ERROR: Path '{target_path}' does not exist")
        print(f"\nUsage: python {os.path.basename(__file__)} [target_directory]")
        print(f"Example: python {os.path.basename(__file__)} ../addon")
        sys.exit(1)
    
    # Count Python files
    py_files = []
    for root, _, files in os.walk(target_path):
        for file in files:
            if file.endswith('.py'):
                py_files.append(os.path.join(root, file))
    
    print(f"Target directory: {os.path.abspath(target_path)}")
    print(f"Found {len(py_files)} Python file(s) to analyze\n")
    
    if not py_files:
        print("WARNING: No Python files found in target directory")
        sys.exit(0)
    
    # Run linters
    runner = MultiLinterRunner(target_path)
    print("=" * 80)
    print("Starting analysis...")
    print("=" * 80 + "\n")
    
    runner.process_directory()
    summary_file = runner.generate_summary_database()
    
    # Print summary
    print("\n" + "=" * 80)
    print("Linting complete!")
    print("=" * 80)
    print(f"Individual reports: {runner.output_dir}/<filename>_linter_report.txt")
    print(f"Summary database: {summary_file}")
    print(f"Analyzed {len(py_files)} file(s) with {len(runner.available_linters)} linter(s)")
    print()

if __name__ == "__main__":
    main()
