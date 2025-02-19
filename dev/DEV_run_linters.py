"""
Multi-Linter Runner for Blender Addons
-------------------------------------
This script runs multiple linters (Ruff, Flake8, Black, Mypy, Pylint) on Python files
and generates a consolidated report.
"""

import os
import sys
import subprocess
from datetime import datetime
from typing import List, Dict, Optional, Tuple
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
        
        # Ensure output directory exists
        self.output_dir = os.path.join(os.path.dirname(self.target_path), "linter_reports")
        os.makedirs(self.output_dir, exist_ok=True)

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
        """Run all linters on a single file."""
        self.results[file_path] = []
        
        # Run each linter
        linters = [
            self.run_black,
            self.run_ruff,
            self.run_flake8,
            self.run_mypy,
            self.run_pylint
        ]
        
        for linter in linters:
            result = linter(file_path)
            self.results[file_path].append(result)

    def process_directory(self):
        """Process all Python files in the target directory."""
        for root, _, files in os.walk(self.target_path):
            for file in files:
                if file.endswith('.py'):
                    file_path = os.path.join(root, file)
                    print(f"Processing: {file_path}")  # Debug print
                    try:
                        self.process_file(file_path)
                    except Exception as e:
                        print(f"Error processing {file_path}: {str(e)}")

    def generate_report(self):
        """Generate a detailed report of all linter results."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = os.path.join(self.output_dir, f"linter_report_{timestamp}.txt")
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("Multi-Linter Report\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")

            for file_path, results in self.results.items():
                f.write(f"\nFile: {os.path.relpath(file_path, self.target_path)}\n")
                f.write("-" * 80 + "\n")

                for result in results:
                    f.write(f"\n{result.linter_name.upper()}\n")
                    f.write("-" * len(result.linter_name) + "\n")
                    
                    if result.error:
                        f.write(f"Error: {result.error}\n")
                    elif result.output:
                        f.write(result.output + "\n")
                    else:
                        f.write("No issues found.\n")

        print(f"Report generated: {report_file}")
        return report_file

def main():
    if len(sys.argv) != 2:
        print("Usage: python run_linters.py <target_directory>")
        sys.exit(1)

    target_path = sys.argv[1]
    if not os.path.exists(target_path):
        print(f"Error: Path '{target_path}' does not exist")
        sys.exit(1)

    runner = MultiLinterRunner(target_path)
    runner.process_directory()
    report_file = runner.generate_report()
    
    # Print summary
    print("\nLinting complete!")
    print(f"Report saved to: {report_file}")

if __name__ == "__main__":
    main()
