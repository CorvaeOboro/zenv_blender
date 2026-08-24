r"""
DEV Addon Tester - Tests each addon by loading it in a temporary Blender instance and executing its operators
Logs all outputs, warnings, and errors to individual test report files

Example commands:
 & 'C:\Program Files\Blender Foundation\Blender 4.0\blender.exe' -b -P dev\DEV_blender_addon_tester.py  # Test all addons
 & 'C:\Program Files\Blender Foundation\Blender 4.0\blender.exe' -b -P dev\DEV_blender_addon_tester.py -- --addon z_blender_MESH_diffusion_reaction  # Test specific addon

VERSION::20260822
"""

#region IMPORTS
# Standard library imports used across discovery, logging, operator testing, and CLI parsing.
import bpy
import os
import sys
import re
import datetime
import logging
import inspect
import traceback
import random
import argparse
import shutil
from pathlib import Path
#endregion

#region REGEX
# Matches report filenames: test_report_<addon_name>_<YYYYMMDD>_<HHMMSS>.txt
# The addon name itself may contain underscores, so we anchor on the trailing timestamp.
_REPORT_NAME_RE = re.compile(r'^test_report_(.*)_(\d{8}_\d{6})$')
#endregion


class AddonTester:
    #region INIT
    # Constructor: wires up addon/output paths, results store, and the console logger.
    def __init__(self, addon_dir: str, output_dir: str):
        """Initialize the addon tester"""
        self.addon_dir = Path(addon_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.test_results = {}

        # Set up logging
        self.logger = logging.getLogger('AddonTester')
        self.logger.setLevel(logging.DEBUG)

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        self.logger.addHandler(console_handler)
    #endregion

    #region DISCOVER
    # Workflow stage 1: find addon files on disk and bucket them into
    # untested vs previously-tested so untested addons are tested first.
    # Shared filtering helpers ensure find_addons and find_specific_addon
    # apply identical exclusion and naming-convention rules.

    # Directories that are never scanned for addons.
    _EXCLUDED_DIRS = frozenset({'backup', 'removed', '__pycache__'})

    def _is_excluded_path(self, file: Path) -> bool:
        """Return True if the file lives under an excluded *directory*.

        Only directory components are checked; the filename itself is not
        considered, so a file literally named ``backup.py`` is not excluded
        merely because of its name.
        """
        return any(part.lower() in self._EXCLUDED_DIRS for part in file.parent.parts)

    def _is_addon_filename(self, file: Path) -> bool:
        """Return True if the filename matches the addon naming convention."""
        return (file.name.startswith("z_blender_")
                and not file.name.startswith("z_blender_DEV_"))

    def _search_dirs(self) -> list:
        """Return the list of directories to scan (main addon dir + wip/).

        Only the main addon directory is returned because ``rglob`` is
        recursive and already descends into ``wip/``.  Adding ``wip/`` as a
        separate search dir caused every wip addon to be discovered twice.
        """
        return [self.addon_dir]

    def get_existing_test_reports(self) -> set:
        """Get a set of addon names that already have test reports"""
        existing_reports = set()
        if self.output_dir.exists():
            for report in self.output_dir.glob("test_report_*.txt"):
                # Parse addon name from report filename using the trailing
                # YYYYMMDD_HHMMSS timestamp as an anchor (the timestamp itself
                # contains an underscore, so naive split() is unsafe).
                match = _REPORT_NAME_RE.match(report.stem)
                if match:
                    existing_reports.add(match.group(1))
        return existing_reports

    def find_addons(self) -> list:
        """Find all Blender addons in the addon directory"""
        # Get existing test reports
        tested_addons = self.get_existing_test_reports()
        untested_addons = []
        previously_tested_addons = []

        for search_dir in self._search_dirs():
            for file in search_dir.rglob("*.py"):
                if self._is_excluded_path(file):
                    continue
                if not self._is_addon_filename(file):
                    continue
                # Sort into tested and untested lists
                if file.stem in tested_addons:
                    previously_tested_addons.append(file)
                else:
                    untested_addons.append(file)
                self.logger.info(f"Found addon: {file}")

        # Randomize both lists
        random.shuffle(untested_addons)
        random.shuffle(previously_tested_addons)

        # Prioritize untested addons by putting them first
        addon_files = untested_addons + previously_tested_addons

        self.logger.info(f"\nFound {len(addon_files)} addons to test")
        self.logger.info(f"Untested addons: {len(untested_addons)}")
        self.logger.info(f"Previously tested addons: {len(previously_tested_addons)}")
        self.logger.info(f"Excluded directories: {sorted(self._EXCLUDED_DIRS)}")
        return addon_files

    def find_specific_addon(self, addon_name: str) -> list:
        """Find a specific addon in the addon directory.

        Applies the same exclusion and naming-convention filters as
        :meth:`find_addons` so the two discovery paths stay consistent.
        """
        addon_files = []

        for search_dir in self._search_dirs():
            for file in search_dir.rglob(f"{addon_name}.py"):
                if self._is_excluded_path(file):
                    continue
                if not self._is_addon_filename(file):
                    # A name match that doesn't satisfy the naming convention
                    # (e.g. a DEV utility) is skipped to stay consistent with
                    # find_addons.
                    continue
                addon_files.append(file)
                self.logger.info(f"Found addon: {file}")

        if not addon_files:
            self.logger.error(f"No addon found with name: {addon_name}")

        return addon_files
    #endregion

    #region LOGGING
    # Workflow stage 2: create a per-addon file logger that captures all
    # output for one addon into its own test report file.
    def setup_addon_logger(self, addon_name: str) -> tuple:
        """Create a logger for a specific addon.

        Loggers are global singletons keyed by name, so if the same addon is
        tested more than once in a session we must clear any handlers left
        over from a previous run -- otherwise output is duplicated to every
        prior log file and the handler list grows without bound.
        """
        logger = logging.getLogger(addon_name)
        logger.setLevel(logging.DEBUG)
        # Drop handlers from any previous run for this addon name.
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()

        # Create log file
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = self.output_dir / f"test_report_{addon_name}_{timestamp}.txt"
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)

        # Format
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        return logger, log_file
    #endregion

    #region TESTADDON
    # Workflow stage 3 (core): orchestrate the full lifecycle of testing a
    # single addon -- install, import, register, run operators, unregister,
    # and clean up.  This is the most important method in the class.
    def test_addon(self, addon_file: Path):
        """Test a single addon"""
        addon_name = addon_file.stem
        logger = None
        log_file = None
        # Initialize test results so the recording block at the end always
        # has well-defined values even if we bail out before testing operators.
        operators_tested = 0
        operators_failed = 0
        operators_cancelled = 0
        unit_tests_run = 0
        unit_tests_failed = 0
        unit_tests_errored = 0
        # 'tested'  -> reached the operator-testing phase
        # 'error'   -> failed before reaching operators (install/import/register)
        status = 'error'

        try:
            logger, log_file = self.setup_addon_logger(addon_name)

            logger.info(f"Testing addon: {addon_name}")
            logger.info("=" * 80)
            logger.info(f"File path: {addon_file}")

            # Create a new scene to ensure clean state
            bpy.ops.wm.read_factory_settings(use_empty=True)

            # Remove addon if it exists in user addons directory
            addon_path = Path(bpy.utils.resource_path('USER')) / "scripts" / "addons" / f"{addon_name}.py"
            if addon_path.exists():
                logger.info(f"Removing existing addon from: {addon_path}")
                try:
                    # First try to unregister if it's loaded
                    if addon_name in bpy.context.preferences.addons:
                        bpy.ops.preferences.addon_disable(module=addon_name)
                    addon_path.unlink()
                except Exception as e:
                    logger.error(f"Failed to remove existing addon: {str(e)}")
                    logger.error(traceback.format_exc())
                    return

            # Copy addon file to user addons directory
            logger.info(f"Installing addon to: {addon_path}")
            addon_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(addon_file, addon_path)

            # Add addon directory to sys.path temporarily
            addon_dir = str(addon_path.parent)
            path_added = addon_dir not in sys.path
            if path_added:
                sys.path.append(addon_dir)

            module_name = addon_file.stem
            module = None
            try:
                # Import the addon module
                try:
                    module = __import__(module_name)
                except Exception as e:
                    logger.error(f"Failed to import module: {str(e)}")
                    logger.error(traceback.format_exc())
                    return

                # Log basic addon info
                if hasattr(module, 'bl_info'):
                    logger.info("bl_info:")
                    for key, value in module.bl_info.items():
                        logger.info(f"  {key}: {value}")
                else:
                    logger.warning("No bl_info dictionary found!")

                # Try to register the addon
                try:
                    if hasattr(module, 'register'):
                        module.register()
                        logger.info("Successfully registered addon")
                    else:
                        logger.error("No register() function found!")
                        return
                except Exception as e:
                    logger.error(f"Failed to register addon: {str(e)}")
                    logger.error(traceback.format_exc())
                    return

                # Test the operators
                operators_tested, operators_failed, operators_cancelled = self.test_operators(module, logger)
                status = 'tested'

                # Run bug-specific unit tests from the addon's tests/ folder
                # (if any). These are unittest test cases that build targeted
                # scenes and assert specific outcomes for known bug fixes.
                unit_tests_run, unit_tests_failed, unit_tests_errored = self.test_unit_tests(addon_file, logger)

                # Try to unregister the addon
                try:
                    if hasattr(module, 'unregister'):
                        module.unregister()
                        logger.info("Successfully unregistered addon")
                    else:
                        logger.error("No unregister() function found!")
                except Exception as e:
                    logger.error(f"Failed to unregister addon: {str(e)}")
                    logger.error(traceback.format_exc())

            finally:
                # Clean up sys.path
                if path_added and addon_dir in sys.path:
                    sys.path.remove(addon_dir)
                # Remove the imported module so a later re-test re-reads the file
                # instead of returning a stale cached object from sys.modules.
                if module_name in sys.modules:
                    del sys.modules[module_name]
                # Delete the copied addon file so the user profile is not polluted
                # with leftover test artifacts.
                if addon_path.exists():
                    try:
                        addon_path.unlink()
                    except OSError as cleanup_err:
                        logger.warning(f"Could not remove copied addon {addon_path}: {cleanup_err}")

        except Exception as e:
            # Fall back to the class logger if the per-addon logger was never
            # created (e.g. setup_addon_logger raised before assignment).
            report_logger = logger or self.logger
            report_logger.error(f"Unexpected error testing addon: {str(e)}")
            report_logger.error(traceback.format_exc())

        # Record test results
        self.test_results[addon_name] = {
            'log_file': log_file,
            'status': status,
            'operators_tested': operators_tested,
            'operators_failed': operators_failed,
            'operators_cancelled': operators_cancelled,
            'unit_tests_run': unit_tests_run,
            'unit_tests_failed': unit_tests_failed,
            'unit_tests_errored': unit_tests_errored,
        }
    #endregion

    #region TESTOPS
    # Workflow stage 3a: iterate over every ZENV_OT_ operator class exposed
    # by the addon and attempt to execute it, with and without a test object.
    def test_operators(self, module, logger: logging.Logger):
        """Test the operators of an addon.

        Returns a tuple ``(operators_tested, operators_failed, operators_cancelled)``.
        Cancelled operators are reported separately from failures because a
        ``{'CANCELLED'}`` result is often normal behaviour, not a bug.
        """
        operators_tested = 0
        operators_failed = 0
        operators_cancelled = 0
        test_object = None

        # Collect operator classes once (inspect.getmembers is relatively
        # expensive and was previously called twice per addon).
        operators = [
            (name, obj) for name, obj in inspect.getmembers(module)
            if (inspect.isclass(obj)
                and hasattr(obj, 'bl_idname')
                and name.startswith('ZENV_OT_'))
        ]

        if not operators:
            logger.warning("No ZENV operators found in addon")
            return 0, 0, 0

        # Reset to an empty scene once, immediately before testing operators.
        # (The earlier reset in test_addon was redundant and could discard
        # state set up between the two calls.)
        bpy.ops.wm.read_factory_settings(use_empty=True)

        # Test each operator
        for name, obj in operators:
            logger.info(f"\nTesting operator: {name}")
            logger.info(f"bl_idname: {obj.bl_idname}")
            logger.info(f"bl_label: {getattr(obj, 'bl_label', 'No label')}")

            # First attempt without test object
            status = self.try_operator(obj.bl_idname, logger)

            # If not finished, try again with a test object selected
            if status != 'FINISHED':
                logger.info(f"Operator {status}. Retrying with test object...")

                # Create test object if not already created
                if test_object is None:
                    test_object = self.create_test_object(logger)
                else:
                    # Ensure test object is selected
                    bpy.ops.object.select_all(action='DESELECT')
                    test_object.select_set(True)
                    bpy.context.view_layer.objects.active = test_object

                # Try operator again
                status = self.try_operator(obj.bl_idname, logger)

            operators_tested += 1
            if status == 'FINISHED':
                logger.info("Operator succeeded")
            elif status == 'CANCELLED':
                operators_cancelled += 1
                logger.warning("Operator cancelled even with test object")
            else:
                operators_failed += 1
                logger.error(f"Operator failed even with test object (status={status})")

        # Clean up test object if created
        if test_object is not None:
            bpy.ops.object.select_all(action='DESELECT')
            test_object.select_set(True)
            bpy.context.view_layer.objects.active = test_object
            bpy.ops.object.delete()
            logger.info("Cleaned up test object")

        return operators_tested, operators_failed, operators_cancelled
    #endregion

    #region UNITTESTS
    # Workflow stage 3b: discover and run bug-specific unittest files from
    # the addon's ``tests/`` subfolder.  These complement the smoke-test
    # pass above by asserting specific outcomes for known bug fixes.
    def test_unit_tests(self, addon_file: Path, logger: logging.Logger):
        """Run unittest files from the addon's ``tests/`` subfolder.

        Looks for ``<addon_dir>/tests/test_*.py`` and runs them via
        ``unittest``.  Output is captured and logged to the per-addon log
        file.  Returns ``(run, failed, errored)`` counts.

        If no tests/ folder exists, returns ``(0, 0, 0)`` silently.
        """
        tests_dir = addon_file.parent / "tests"
        if not tests_dir.is_dir():
            logger.info("No tests/ subfolder found - skipping unit tests.")
            return 0, 0, 0

        test_files = sorted(tests_dir.glob("test_*.py"))
        if not test_files:
            logger.info(f"tests/ exists but contains no test_*.py files.")
            return 0, 0, 0

        logger.info(f"\n{'=' * 80}")
        logger.info(f"Running {len(test_files)} unit test file(s) from {tests_dir}")
        logger.info(f"{'=' * 80}")

        # Make the tests directory importable so ``import _test_utils`` works.
        tests_dir_str = str(tests_dir)
        path_added = tests_dir_str not in sys.path
        if path_added:
            sys.path.insert(0, tests_dir_str)

        # Also make the addon's parent dir importable so the test utils can
        # import the addon module by name.
        addon_dir_str = str(addon_file.parent)
        addon_path_added = addon_dir_str not in sys.path
        if addon_path_added:
            sys.path.insert(0, addon_dir_str)

        total_run = 0
        total_failures = 0
        total_errors = 0

        try:
            import unittest as _unittest
            import io as _io

            loader = _unittest.TestLoader()
            suite = _unittest.TestSuite()

            for tf in test_files:
                module_name = tf.stem  # e.g. "test_clean_unused_textures"
                try:
                    # Force reimport so repeated runs in one session pick up
                    # changes.
                    if module_name in sys.modules:
                        import importlib
                        importlib.reload(sys.modules[module_name])
                    else:
                        __import__(module_name)
                    suite.addTests(loader.loadTestsFromName(module_name))
                    logger.info(f"  Discovered: {module_name}")
                except Exception as e:
                    logger.error(f"  Failed to load {module_name}: {e}")
                    logger.error(traceback.format_exc())
                    total_errors += 1

            if suite.countTestCases() == 0:
                logger.info("No test cases loaded.")
                return 0, 0, total_errors

            # Run with a stream that we can log.
            stream = _io.StringIO()
            runner = _unittest.TextTestRunner(stream=stream, verbosity=2)
            result = runner.run(suite)

            total_run = result.testsRun
            total_failures = len(result.failures)
            total_errors = len(result.errors)

            # Log the full unittest output.
            logger.info(f"\nUnit test output:\n{stream.getvalue()}")

            if result.wasSuccessful():
                logger.info(f"Unit tests PASSED: {total_run} run, 0 failures, 0 errors")
            else:
                logger.warning(
                    f"Unit tests FAILED: {total_run} run, "
                    f"{total_failures} failures, {total_errors} errors"
                )

        finally:
            if path_added and tests_dir_str in sys.path:
                sys.path.remove(tests_dir_str)
            if addon_path_added and addon_dir_str in sys.path:
                sys.path.remove(addon_dir_str)

        return total_run, total_failures, total_errors
    #endregion

    #region TRYOP
    # Low-level operator dispatch: resolve a bl_idname to a bpy.ops callable
    # and execute it, returning a status string for the caller to interpret.
    def try_operator(self, bl_idname: str, logger: logging.Logger) -> str:
        """Try to execute an operator and return a status string.

        Returns one of:
            ``'FINISHED'``  - operator returned ``{'FINISHED'}``
            ``'CANCELLED'`` - operator returned ``{'CANCELLED'}`` (may be normal)
            ``'ERROR'``     - operator raised or returned an unexpected value
            ``'NOT_FOUND'`` - the operator or its category is not registered
        """
        try:
            # Split operator category and name (maxsplit=1 protects against
            # bl_idnames that contain more than one dot).
            op_category, op_name = bl_idname.split('.', 1)

            # Get the operator
            if not hasattr(bpy.ops, op_category):
                logger.error(f"Operator category {op_category} not found")
                return 'NOT_FOUND'
            op = getattr(bpy.ops, op_category)
            if not hasattr(op, op_name):
                logger.error(f"Operator {op_name} not found in category {op_category}")
                return 'NOT_FOUND'

            # Execute operator
            result = getattr(op, op_name)()

            # Check result
            if result == {'FINISHED'}:
                return 'FINISHED'
            elif result == {'CANCELLED'}:
                logger.warning("Operator cancelled - this may be normal for some operators")
                return 'CANCELLED'
            else:
                logger.warning(f"Operator returned {result}")
                return 'ERROR'

        except Exception as e:
            logger.error(f"Error executing operator: {str(e)}")
            logger.error(traceback.format_exc())
            return 'ERROR'
    #endregion

    #region TESTOBJ
    # Scene helper: build a small 3x3x10cm box and select it so operators
    # that require an active object have something to work with.
    def create_test_object(self, logger: logging.Logger) -> bpy.types.Object:
        """Create a test object (3cm x 3cm x 10cm box) and select it.

        A cube is used (rather than a plane) so that scaling Z actually
        produces height, matching the documented "10cm tall" geometry.
        """
        # Clear any existing selection
        bpy.ops.object.select_all(action='DESELECT')

        # Create a unit cube (2m edge length by default with size=1) and scale
        # it to 3cm x 3cm x 10cm. Using size=0.03 gives a 3cm cube, then we
        # stretch Z so the final height is 10cm.
        bpy.ops.mesh.primitive_cube_add(size=0.03, enter_editmode=False, align='WORLD', location=(0, 0, 0.05))
        test_obj = bpy.context.active_object
        test_obj.scale.z = 10.0 / 3.0  # 3cm cube -> 10cm tall
        test_obj.name = "ZENV_TEST_OBJECT"

        # Apply scale so the geometry reflects the dimensions
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

        logger.info("Created test object: 3cm x 3cm x 10cm box")
        return test_obj
    #endregion

    #region SUMMARY
    # Workflow stage 4: aggregate per-addon results into a single summary
    # report file with overall statistics (success rate, error count, etc.).
    def write_summary(self):
        """Write test summary to file"""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        summary_file = self.output_dir / f"test_summary_{timestamp}.txt"

        # Use an explicit UTF-8 encoding so non-ASCII addon names or bl_info
        # values do not raise UnicodeEncodeError on Windows (cp1252 default).
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write("Addon Testing Summary Report\n")
            f.write("=========================\n\n")
            f.write(f"Generated: {datetime.datetime.now()}\n")
            f.write(f"Total addons tested: {len(self.test_results)}\n\n")

            # Write results for each addon
            for addon_name, results in self.test_results.items():
                f.write(f"\nAddon: {addon_name}\n")
                f.write("-" * (len(addon_name) + 7) + "\n")
                f.write(f"Status: {results['status']}\n")
                f.write(f"Operators tested: {results['operators_tested']}\n")
                f.write(f"Operators failed: {results['operators_failed']}\n")
                f.write(f"Operators cancelled: {results['operators_cancelled']}\n")
                f.write(f"Unit tests run: {results.get('unit_tests_run', 0)}\n")
                f.write(f"Unit tests failed: {results.get('unit_tests_failed', 0)}\n")
                f.write(f"Unit tests errored: {results.get('unit_tests_errored', 0)}\n")
                log_file = results['log_file']
                f.write(f"Log file: {log_file.name if log_file else 'N/A'}\n")

            # Write overall statistics
            total_operators = sum(r['operators_tested'] for r in self.test_results.values())
            total_failed = sum(r['operators_failed'] for r in self.test_results.values())
            total_cancelled = sum(r['operators_cancelled'] for r in self.test_results.values())
            total_unit_run = sum(r.get('unit_tests_run', 0) for r in self.test_results.values())
            total_unit_failed = sum(r.get('unit_tests_failed', 0) for r in self.test_results.values())
            total_unit_errored = sum(r.get('unit_tests_errored', 0) for r in self.test_results.values())
            errored_addons = sum(1 for r in self.test_results.values() if r['status'] == 'error')

            f.write("\nOverall Statistics\n")
            f.write("=================\n")
            f.write(f"Total operators tested: {total_operators}\n")
            f.write(f"Total operators failed: {total_failed}\n")
            f.write(f"Total operators cancelled: {total_cancelled}\n")
            f.write(f"Total unit tests run: {total_unit_run}\n")
            f.write(f"Total unit tests failed: {total_unit_failed}\n")
            f.write(f"Total unit tests errored: {total_unit_errored}\n")
            f.write(f"Addons that errored before testing: {errored_addons}\n")
            if total_operators > 0:
                f.write(f"Operator success rate: {((total_operators - total_failed) / total_operators * 100):.1f}%\n")
            if total_unit_run > 0:
                f.write(f"Unit test success rate: {((total_unit_run - total_unit_failed - total_unit_errored) / total_unit_run * 100):.1f}%\n")

        self.logger.info(f"\nTesting complete. Summary written to: {summary_file}")
    #endregion

#region CLI
# Command-line argument parsing. Blender passes script arguments after the
# last "--" separator, which may differ from the first one Blender injects.
def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="Test Blender addons")
    parser.add_argument("--addon", type=str, help="Specific addon name to test (without .py extension)")

    # Handle Blender's argument passing (everything after the LAST -- is
    # passed to the script). Using the last occurrence is safer because
    # Blender itself may inject a "--" in some invocation modes.
    if "--" in sys.argv:
        separator_index = len(sys.argv) - 1 - sys.argv[::-1].index("--")
        args = parser.parse_args(sys.argv[separator_index + 1:])
    else:
        args = parser.parse_args([])

    return args
#endregion

#region MAIN
# Entry point: parse args, discover addons, run tests, write summary, print console output.
def main():
    """Main function"""
    # Parse arguments
    args = parse_args()

    # Initialize tester
    addon_dir = Path(__file__).parent.parent / "addon"
    output_dir = Path(__file__).parent / "addon_test_reports"
    tester = AddonTester(addon_dir, output_dir)

    # Find and test addons
    if args.addon:
        # Test specific addon
        addon_files = tester.find_specific_addon(args.addon)
    else:
        # Test all addons
        addon_files = tester.find_addons()

    # Run tests
    for addon_file in addon_files:
        tester.test_addon(addon_file)

    # Write summary report file
    tester.write_summary()

    # Print summary
    print("\nTest Summary:")
    for addon_name, result in tester.test_results.items():
        print(f"\n{addon_name}:")
        print(f"  Status: {result['status']}")
        print(f"  Log file: {result['log_file']}")
        print(f"  Operators tested: {result['operators_tested']}")
        print(f"  Operators failed: {result['operators_failed']}")
        print(f"  Operators cancelled: {result['operators_cancelled']}")
        print(f"  Unit tests run: {result.get('unit_tests_run', 0)}")
        print(f"  Unit tests failed: {result.get('unit_tests_failed', 0)}")
        print(f"  Unit tests errored: {result.get('unit_tests_errored', 0)}")

if __name__ == "__main__":
    main()
#endregion
