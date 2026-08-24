"""
Multi-Linter Runner for Blender Addons
-------------------------------------
This script runs multiple linters (Ruff, Flake8, Black, Mypy, Pylint) on Python files
and generates a consolidated report.

Usage:
    python DEV_run_linters.py [target_directory]
    
If no directory is provided, defaults to ../addon relative to this script.

Mypy configuration:
    Mypy is invoked WITHOUT --strict. On a Blender addon repo that imports
    bpy/bmesh/mathutils (which ship no type stubs), --strict produces hundreds
    of missing-import errors that drown out real type issues. Configure
    strictness and ``ignore_missing_imports`` for ``bpy.*`` etc. in the
    project's ``mypy.ini`` or ``pyproject.toml`` instead; this runner will
    pick up that config automatically.

Output retention:
    Per-file reports (``<base_name>_linter_report.txt``) are overwritten on
    each run. Timestamped summary files (``linter_summary_<ts>.txt`` /
    ``.json``) are NOT overwritten and accumulate over time. There is no
    automatic retention policy; periodically clear ``linter_reports/`` or
    add it to ``.gitignore``. The timestamp includes the PID so two
    concurrent runs in the same second do not clobber each other.
"""

#region SETUP
# Imports and module-level setup.
from __future__ import annotations

import logging
import os
import re
import sys
import subprocess
from datetime import datetime
from dataclasses import dataclass
import json

# Module logger for diagnostic warnings/errors. Progress and final-summary
# output stays as print() since it is the script's primary user-facing CLI
# output; routing those through logging would change the UX and default
# formatting. Warnings/errors here can be redirected or silenced
# independently by configuring this logger.
log = logging.getLogger(__name__)
#endregion


#region DATACLASS
# Result record produced by a single linter on a single file.
@dataclass
class LinterResult:
    linter_name: str
    output: str
    return_code: int
    error: str | None = None
#endregion


#region EXCEPT
# Custom exception so __init__ can signal "no linters installed" without
# calling sys.exit (keeps the class testable).
class NoLintersAvailableError(RuntimeError):
    """Raised when no configured linters are installed on the system.

    Raised by :meth:`MultiLinterRunner._check_linter_availability` instead of
    calling ``sys.exit`` so the class stays testable. CLI entry points are
    expected to catch this and translate it into a non-zero exit code.
    """
#endregion


class MultiLinterRunner:
    """Discovers, runs, and reports on multiple linters over a directory."""

    #region CONFIG
    # Class-level configuration: the single source of truth for which
    # linters exist, their CLI args, timeouts, help text, and issue-parsing
    # regexes. All downstream methods iterate these dicts so adding a linter
    # is a one-line change.

    # name -> extra CLI args (file path is appended after a ``--`` separator
    # so filenames starting with ``-`` are safe). The module invoked is
    # ``python -m <name>`` so the key doubles as the module name.
    LINTER_CONFIG: dict[str, list[str]] = {
        "black":  ["--check", "--diff"],
        "ruff":   ["check"],
        "flake8": [],
        # Mypy args come from the project's mypy config (mypy.ini /
        # pyproject.toml). We deliberately do NOT pass --strict here: on a
        # Blender addon repo that imports bpy/bmesh/mathutils (which ship no
        # type stubs), --strict produces hundreds of missing-import errors
        # that drown out real type issues. Configure strictness in the
        # project's mypy config instead, with ignore_missing_imports for
        # bpy.* etc.
        "mypy":   [],
        "pylint": [],
    }

    # Per-linter timeout in seconds. Mypy/Pylint can be slow on large files,
    # so they get a longer budget than the formatters.
    LINTER_TIMEOUTS: dict[str, int] = {
        "black":  60,
        "ruff":   60,
        "flake8": 60,
        "mypy":   180,
        "pylint": 180,
    }

    # Static "what to fix" guidance per linter. Only written to a file's
    # report when that linter actually produced issues or an error, to avoid
    # repeating the same boilerplate in every clean report.
    LINTER_HELP: dict[str, str] = {
        "black": (
            "Black is a code formatter. Issues indicate formatting inconsistencies.\n"
            "- Run 'black <filename>' to auto-format the file\n"
            "- Or use 'black --check' to see what would change\n"
        ),
        "ruff": (
            "Ruff checks for code quality and style issues.\n"
            "- Fix issues manually or run 'ruff check --fix <filename>'\n"
            "- Common issues: unused imports, undefined names, line length\n"
        ),
        "flake8": (
            "Flake8 checks PEP 8 style guide compliance.\n"
            "- E### codes: PEP 8 errors (formatting, whitespace)\n"
            "- W### codes: PEP 8 warnings\n"
            "- F### codes: PyFlakes errors (undefined names, unused imports)\n"
        ),
        "mypy": (
            "Mypy performs static type checking.\n"
            "- Add type hints to functions: def func(x: int) -> str:\n"
            "- Use 'from typing import' for complex types\n"
            "- Consider adding '# type: ignore' for unavoidable issues\n"
        ),
        "pylint": (
            "Pylint performs comprehensive code analysis.\n"
            "- C#### codes: Convention violations\n"
            "- R#### codes: Refactoring suggestions\n"
            "- W#### codes: Warnings\n"
            "- E#### codes: Errors\n"
            "- Add docstrings, improve naming, reduce complexity\n"
        ),
    }

    # Per-linter issue-counting strategies. Each pattern matches a single
    # reported issue in the linter's default text output. A count of 0 means
    # "no issues parsed" (the linter may still have exited non-zero for other
    # reasons, e.g. an env error handled separately). These are intentionally
    # conservative: better to under-count slightly than to count banners,
    # summary lines, or diff headers as issues.
    ISSUE_PATTERNS: dict[str, re.Pattern[str]] = {
        # black --diff: count unified-diff hunk headers.
        "black":  re.compile(r"^@@", re.MULTILINE),
        # ruff/flake8: "path:line:col: CODE message"
        "ruff":   re.compile(r"^.*?:\d+:\d+: [A-Z]\d+ ", re.MULTILINE),
        "flake8": re.compile(r"^.*?:\d+:\d+: [A-Z]\d+ ", re.MULTILINE),
        # mypy: "path:line: error: ..." (also warning/note, but errors are
        # what matter for a count).
        "mypy":   re.compile(r"^.*?:\d+: (error|note|warning): ", re.MULTILINE),
        # pylint: "module:line: C0xxx: message" - skip the
        # "************* Module" banner lines.
        "pylint": re.compile(r"^.*?:\d+: [CRWE]\d{4}: ", re.MULTILINE),
    }
    #endregion

    #region INIT
    # Constructor and linter-availability probe.

    def __init__(self, target_path: str):
        self.target_path = os.path.abspath(target_path)
        self.results: dict[str, list[LinterResult]] = {}
        self.available_linters: set[str] = set()
        self.missing_linters: set[str] = set()
        
        # Ensure output directory exists
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.output_dir = os.path.join(script_dir, "linter_reports")
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Check which linters are available
        self._check_linter_availability()

    def _check_linter_availability(self) -> None:
        """Check which linters are installed and available.

        Raises :class:`NoLintersAvailableError` if none of the configured
        linters are installed.
        """
        linters = list(self.LINTER_CONFIG.keys())
        
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
            log.warning("%d linter(s) not installed: %s", len(self.missing_linters), ", ".join(sorted(self.missing_linters)))
            print(f"\nTo install missing linters, run:")
            print(f"  pip install -r requirements-dev.txt")
            print(f"\nOr install individually:")
            for linter in sorted(self.missing_linters):
                print(f"  pip install {linter}")
            print()
        
        if not self.available_linters:
            log.error("No linters are available!")
            print("Please install at least one linter to continue.")
            raise NoLintersAvailableError(
                "No configured linters are installed. "
                f"Missing: {', '.join(sorted(self.missing_linters))}"
            )
        
        print(f"Running with {len(self.available_linters)} available linter(s): {', '.join(sorted(self.available_linters))}\n")
    #endregion

    #region RUN
    # Core execution: run a subprocess and translate it into a LinterResult.
    # Env failures (timeout, missing executable) are kept separate from real
    # linter output via the ``error`` field.

    def run_command(
        self, command: list[str], timeout: int = 60
    ) -> tuple[int, str, str | None, str | None]:
        """Run a command and return its output.

        Returns a 4-tuple ``(return_code, stdout, stderr, env_error)``:

        * ``return_code`` - process exit code, or ``1`` if the process could
          not be run at all.
        * ``stdout`` - captured standard output (empty on env error).
        * ``stderr`` - captured standard error (empty on env error).
        * ``env_error`` - ``None`` for a normal run (regardless of exit code);
          a human-readable string when the command could not be run because of
          a timeout, missing executable, or other OS-level failure. Callers
          should treat a non-None ``env_error`` as "the linter did not actually
          run" and surface it via :attr:`LinterResult.error` rather than as
          linter output.
        """
        try:
            process = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return process.returncode, process.stdout, process.stderr, None
        except subprocess.TimeoutExpired:
            return 1, "", None, f"Command timed out after {timeout}s: {' '.join(command)}"
        except OSError as e:
            # FileNotFoundError (missing interpreter/linter), PermissionError, etc.
            return 1, "", None, f"Could not run command: {e!r}"

    def _run_linter(self, name: str, file_path: str) -> LinterResult:
        """Run a single configured linter on ``file_path``.

        Distinguishes environment failures (timeout, missing executable) from
        real linter output: env failures populate :attr:`LinterResult.error`
        with a non-``None`` value and leave ``output`` empty, so the report
        generator can render them as errors rather than as findings.
        """
        extra_args = self.LINTER_CONFIG.get(name, [])
        timeout = self.LINTER_TIMEOUTS.get(name, 60)
        cmd = [sys.executable, "-m", name, *extra_args, "--", file_path]
        return_code, stdout, stderr, env_error = self.run_command(cmd, timeout=timeout)

        if env_error is not None:
            # The linter never actually ran.
            return LinterResult(name, "", return_code, error=env_error)

        # Most linters print findings to stdout; some (e.g. flake8) use stderr.
        # Concatenate both so nothing is silently dropped, preserving stdout
        # first for readability.
        combined = (stdout or "") + (stderr or "") if stderr else (stdout or "")
        return LinterResult(name, combined, return_code, error=None)
    #endregion

    #region PROCESS
    # Core workflow: walk the target directory and run every available
    # linter on each .py file. Results are committed atomically per file so
    # a mid-file exception cannot leave partial state.

    def process_file(self, file_path: str) -> None:
        """Run all available linters on a single file.

        Results are accumulated in a local list and only committed to
        :attr:`results` once every available linter has been attempted, so a
        mid-file exception (caught by :meth:`process_directory`) cannot leave
        a partial entry behind. The per-file report is generated from the
        committed list.
        """
        # Show which file we're processing
        file_name = os.path.basename(file_path)
        print(f"\n  Processing: {file_name}")

        # Run only the available linters, in a stable order matching the
        # LINTER_CONFIG declaration order.
        local_results: list[LinterResult] = []
        for linter_name in self.LINTER_CONFIG:
            if linter_name not in self.available_linters:
                continue
            print(f"    Running {linter_name}...", end='', flush=True)
            try:
                result = self._run_linter(linter_name, file_path)
            except Exception as e:
                # Defensive: _run_linter already converts known env errors to
                # LinterResult.error, but guard against anything unexpected so
                # one linter's failure doesn't abort the rest of the file.
                result = LinterResult(linter_name, "", 1, error=f"Runner error: {e!r}")
            status = "OK" if result.return_code == 0 and result.error is None else "ISSUES"
            print(f" {status}")
            local_results.append(result)

        # Commit atomically: either all linters for this file are recorded,
        # or none are.
        self.results[file_path] = local_results

        # Generate individual report for this file immediately
        self._generate_individual_report(file_path, local_results)

    def process_directory(self) -> list[str]:
        """Process all Python files in the target directory.

        Returns the list of file paths that were actually processed (after the
        single walk performed here), so callers can report an accurate count
        instead of re-walking the directory.

        Files whose processing raises an unexpected exception are still
        recorded in :attr:`results` with a synthetic ``LinterResult``
        (``linter_name="runner"``, ``error`` set to the exception text) so the
        failure shows up in both the per-file report and the summary database,
        not only on stdout.
        """
        processed: list[str] = []
        for root, _, files in os.walk(self.target_path):
            for file in files:
                if file.endswith('.py'):
                    file_path = os.path.join(root, file)
                    try:
                        self.process_file(file_path)
                        processed.append(file_path)
                    except Exception as e:
                        log.warning("Error processing %s: %s", os.path.basename(file_path), e)
                        # Record the failure so it appears in the summary.
                        self.results[file_path] = [
                            LinterResult("runner", "", 1, error=f"Error processing file: {e!r}")
                        ]
                        # Still write a per-file report for the failure.
                        try:
                            self._generate_individual_report(file_path, self.results[file_path])
                        except Exception:
                            pass
                        processed.append(file_path)
        
        print(f"\n  Completed processing {len(processed)} files total.")
        return processed
    #endregion

    #region REPORT
    # Output generation: per-file text reports and the consolidated summary
    # database (text + JSON).

    def _generate_individual_report(self, file_path: str, results: list[LinterResult]) -> None:
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
                
                has_problems = result.error is not None or result.return_code != 0
                
                if result.error is not None:
                    # Environment failure: the linter did not actually run.
                    f.write(f"ERROR (could not run {result.linter_name}): {result.error}\n\n")
                elif result.return_code == 0:
                    f.write(f"No issues found by {result.linter_name}.\n\n")
                else:
                    f.write(f"Issues found:\n\n")
                    f.write(result.output + "\n")
                
                # Only include the static "what to fix" guidance when this
                # linter actually produced issues or failed to run. Clean
                # reports stay compact.
                if has_problems:
                    help_text = self.LINTER_HELP.get(result.linter_name)
                    if help_text:
                        f.write(f"\n{'-' * 80}\n")
                        f.write(f"What to fix ({result.linter_name}):\n")
                        f.write(f"{'-' * 80}\n")
                        f.write(help_text)
                
                f.write("\n")
        
        print(f"    Report saved: {base_name}_linter_report.txt")

    def generate_summary_database(self) -> str:
        """Generate a condensed summary database of all linter results.

        Returns the path to the text summary file. A JSON sibling is also
        written next to it.
        """
        print("\nGenerating summary database...")
        # Include PID in the timestamp so two concurrent runs in the same
        # second don't clobber each other's summaries.
        timestamp = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_pid{os.getpid()}"
        
        # Text summary
        summary_file = os.path.join(self.output_dir, f"linter_summary_{timestamp}.txt")
        
        # Linters in a stable, sorted order - single source of truth for both
        # the table header and the per-row extraction.
        linters_sorted = sorted(self.available_linters)
        
        # Build per-file, per-linter summary data.
        summary_data: dict[str, dict[str, dict[str, object]]] = {}
        for file_path, results in self.results.items():
            file_name = os.path.basename(file_path)
            file_data: dict[str, dict[str, object]] = {}
            for result in results:
                if result.error is not None:
                    status = "ERROR"
                elif result.return_code == 0:
                    status = "PASS"
                else:
                    status = "FAIL"
                file_data[result.linter_name] = {
                    "status": status,
                    "issue_count": self._count_issues(result),
                }
            summary_data[file_name] = file_data
        
        # Write text summary
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("LINTER SUMMARY DATABASE\n")
            f.write("=" * 80 + "\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total Files: {len(self.results)}\n")
            f.write(f"Linters Used: {', '.join(linters_sorted)}\n")
            f.write("=" * 80 + "\n\n")
            
            # Summary table - columns driven by available_linters, not
            # hardcoded, so adding a linter to LINTER_CONFIG automatically
            # gets a column here.
            name_col = 50
            col_width = 8
            header = f"{'File':<{name_col}}" + "".join(f" {l.capitalize():<{col_width}}" for l in linters_sorted) + "\n"
            f.write(header)
            f.write("-" * (name_col + (col_width + 1) * len(linters_sorted)) + "\n")
            
            for file_name in sorted(summary_data.keys()):
                file_data = summary_data[file_name]
                short_name = self._shorten_name(file_name, name_col)
                row = f"{short_name:<{name_col}}"
                for linter in linters_sorted:
                    status = str(file_data.get(linter, {}).get("status", "N/A"))
                    row += f" {status:<{col_width}}"
                f.write(row + "\n")
            
            f.write("\n" + "=" * 80 + "\n")
            f.write("DETAILED ISSUE COUNTS\n")
            f.write("=" * 80 + "\n\n")
            
            for file_name in sorted(summary_data.keys()):
                file_data = summary_data[file_name]
                total_issues = sum(int(d.get("issue_count", 0)) for d in file_data.values())
                
                if total_issues > 0:
                    f.write(f"\n{file_name}:\n")
                    for linter in sorted(file_data.keys()):
                        count = int(file_data[linter].get("issue_count", 0))
                        if count > 0:
                            f.write(f"  {linter}: {count} issues\n")
        
        # Also save as JSON for programmatic access
        json_file = os.path.join(self.output_dir, f"linter_summary_{timestamp}.json")
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(summary_data, f, indent=2)
        
        print(f"Summary database saved: {summary_file}")
        print(f"JSON database saved: {json_file}")
        return summary_file
    #endregion

    #region UTILS
    # Pure helpers used by the report/summary generators: issue counting
    # from linter output and filename truncation for the summary table.

    def _count_issues(self, result: LinterResult) -> int:
        """Return a best-effort count of real issues in ``result``.

        Returns 0 for env errors (the linter never ran) and for passing
        linters. For linters with findings, parses the output with a
        linter-specific regex so banners, summary lines, and diff headers are
        not counted as issues. The synthetic ``"runner"`` linter (used for
        per-file processing failures) counts as 1 issue when an error is set.
        """
        if result.error is not None:
            return 1 if result.linter_name == "runner" else 0
        if result.return_code == 0 or not result.output:
            return 0
        pattern = self.ISSUE_PATTERNS.get(result.linter_name)
        if pattern is None:
            # Unknown linter: fall back to non-blank, non-banner lines.
            return sum(
                1 for line in result.output.splitlines()
                if line.strip() and not line.startswith("=") and not line.startswith("*")
            )
        return len(pattern.findall(result.output))

    @staticmethod
    def _shorten_name(name: str, max_len: int = 50) -> str:
        """Truncate ``name`` to ``max_len`` chars, preserving the suffix.

        Blender addon filenames follow ``z_blender_<GROUP>_<name>.py`` so the
        distinguishing part is usually the suffix. We keep the head and tail
        with an ellipsis in the middle, e.g.
        ``z_blender_MESH_very_long_addon_name.py`` ->
        ``z_blender_MESH_very...addon_name.py``.
        """
        if len(name) <= max_len:
            return name
        if max_len <= 3:
            return "..."[:max_len]
        keep = max_len - 3
        head = keep // 2
        tail = keep - head
        return f"{name[:head]}...{name[-tail:]}"
    #endregion


#region CLI
# Command-line entry point: argument parsing, runner construction, and the
# final user-facing summary print.
def main() -> None:
    # Determine target path
    if len(sys.argv) > 1:
        target_path = sys.argv[1]
    else:
        # Default to ../addon relative to this script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        target_path = os.path.normpath(os.path.join(script_dir, "..", "addon"))
        print(f"INFO: No target directory specified, using default: {os.path.abspath(target_path)}\n")
    
    # Validate path exists
    if not os.path.exists(target_path):
        log.error("Path '%s' does not exist", target_path)
        print(f"\nUsage: python {os.path.basename(__file__)} [target_directory]")
        print(f"Example: python {os.path.basename(__file__)} ../addon")
        sys.exit(1)
    
    print(f"Target directory: {os.path.abspath(target_path)}")
    
    # Construct the runner. This probes linter availability and raises
    # NoLintersAvailableError if none are installed.
    try:
        runner = MultiLinterRunner(target_path)
    except NoLintersAvailableError:
        sys.exit(1)
    
    print("=" * 80)
    print("Starting analysis...")
    print("=" * 80 + "\n")
    
    # Single directory walk: process_directory owns file discovery and
    # returns the list it actually processed, so the count reported to the
    # user always matches what was linted.
    processed_files = runner.process_directory()
    
    if not processed_files:
        log.warning("No Python files found in target directory")
        sys.exit(0)
    
    summary_file = runner.generate_summary_database()
    
    # Print summary
    print("\n" + "=" * 80)
    print("Linting complete!")
    print("=" * 80)
    print(f"Individual reports: {runner.output_dir}/<filename>_linter_report.txt")
    print(f"Summary database: {summary_file}")
    print(f"Analyzed {len(processed_files)} file(s) with {len(runner.available_linters)} linter(s)")
    print()

if __name__ == "__main__":
    main()
#endregion
