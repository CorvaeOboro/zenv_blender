"""
DEV Addon Tester - Tests each addon by loading it in a temporary Blender instance and executing its operators
Logs all outputs, warnings, and errors to individual test report files

Example commands:
 & 'C:\Program Files\Blender Foundation\Blender 4.0\blender.exe' -b -P dev\DEV_blender_addon_tester.py  # Test all addons
 & 'C:\Program Files\Blender Foundation\Blender 4.0\blender.exe' -b -P dev\DEV_blender_addon_tester.py -- --addon z_blender_MESH_diffusion_reaction  # Test specific addon
"""

import bpy
import os
import sys
import datetime
import logging
import inspect
import traceback
import random
import argparse
from pathlib import Path


class AddonTester:
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

    def get_existing_test_reports(self) -> set:
        """Get a set of addon names that already have test reports"""
        existing_reports = set()
        if self.output_dir.exists():
            for report in self.output_dir.glob("test_report_*.txt"):
                # Extract addon name from report filename (format: test_report_addon_name_timestamp.txt)
                parts = report.stem.split('_', 2)  # Split into ['test', 'report', 'addon_name_timestamp']
                if len(parts) > 2:
                    addon_name = '_'.join(parts[2].split('_')[:-1])  # Remove timestamp
                    existing_reports.add(addon_name)
        return existing_reports
    
    def find_addons(self) -> list:
        """Find all Blender addons in the addon directory"""
        addon_files = []
        excluded_dirs = {'backup', 'removed', '__pycache__'}
        
        # Search in both main addon dir and wip subdirectory
        search_dirs = [self.addon_dir]
        wip_dir = self.addon_dir / 'wip'
        if wip_dir.exists():
            search_dirs.append(wip_dir)
        
        # Get existing test reports
        tested_addons = self.get_existing_test_reports()
        untested_addons = []
        previously_tested_addons = []
        
        for search_dir in search_dirs:
            for file in search_dir.rglob("*.py"):
                # Check if any parent folder is in excluded_dirs
                if not any(part.lower() in excluded_dirs for part in file.parts):
                    if file.name.startswith("z_blender_") and not file.name.startswith("z_blender_DEV_"):
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
        self.logger.info("Excluded directories: backup, removed")
        return addon_files
    
    def find_specific_addon(self, addon_name: str) -> list:
        """Find a specific addon in the addon directory"""
        addon_files = []
        excluded_dirs = {'backup', 'removed', '__pycache__'}
        
        # Search in both main addon dir and wip subdirectory
        search_dirs = [self.addon_dir]
        wip_dir = self.addon_dir / 'wip'
        if wip_dir.exists():
            search_dirs.append(wip_dir)
        
        for search_dir in search_dirs:
            for file in search_dir.rglob(f"{addon_name}.py"):
                if not any(part.lower() in excluded_dirs for part in file.parts):
                    addon_files.append(file)
                    self.logger.info(f"Found addon: {file}")
        
        if not addon_files:
            self.logger.error(f"No addon found with name: {addon_name}")
        
        return addon_files
    
    def setup_addon_logger(self, addon_name: str) -> tuple:
        """Create a logger for a specific addon"""
        logger = logging.getLogger(addon_name)
        logger.setLevel(logging.DEBUG)
        
        # Create log file
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = self.output_dir / f"test_report_{addon_name}_{timestamp}.txt"
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        
        # Format
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        return logger, log_file
    
    def test_addon(self, addon_file: Path):
        """Test a single addon"""
        addon_name = addon_file.stem
        logger, log_file = self.setup_addon_logger(addon_name)
        
        try:
            logger.info(f"Testing addon: {addon_name}")
            logger.info("=" * 80)
            logger.info(f"File path: {addon_file}")
            
            # Initialize test results
            operators_tested = 0
            operators_failed = 0
            
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
            import shutil
            shutil.copy2(addon_file, addon_path)
            
            # Add addon directory to sys.path temporarily
            addon_dir = str(addon_path.parent)
            if addon_dir not in sys.path:
                sys.path.append(addon_dir)
            
            try:
                # Import the addon module
                module_name = addon_file.stem
                try:
                    module = __import__(module_name)
                    sys.modules[module_name] = module
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
                operators_tested, operators_failed = self.test_operators(module, logger)
                
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
                if addon_dir in sys.path:
                    sys.path.remove(addon_dir)
            
        except Exception as e:
            logger.error(f"Unexpected error testing addon: {str(e)}")
            logger.error(traceback.format_exc())
        
        # Record test results
        self.test_results[addon_name] = {
            'log_file': log_file,
            'operators_tested': operators_tested,
            'operators_failed': operators_failed
        }
    
    def create_test_object(self, logger: logging.Logger) -> bpy.types.Object:
        """Create a test object (10cm tall by 3cm rectangle) and select it"""
        # Clear any existing selection
        bpy.ops.object.select_all(action='DESELECT')
        
        # Create a plane and scale it
        bpy.ops.mesh.primitive_plane_add(size=0.03, enter_editmode=False, align='WORLD', location=(0, 0, 0.05))
        test_obj = bpy.context.active_object
        test_obj.scale.z = 3.33  # Makes it 10cm tall (0.03 * 3.33 ≈ 0.1)
        test_obj.name = "ZENV_TEST_OBJECT"
        
        # Apply scale
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        
        logger.info("Created test object: 10cm tall by 3cm rectangle")
        return test_obj

    def test_operators(self, module, logger: logging.Logger):
        """Test the operators of an addon"""
        operators_tested = 0
        operators_failed = 0
        test_object = None
        
        # First check for operators in the module
        has_operators = False
        for name, obj in inspect.getmembers(module):
            if (inspect.isclass(obj) and 
                hasattr(obj, 'bl_idname') and 
                name.startswith('ZENV_OT_')):
                has_operators = True
                break
        
        if not has_operators:
            logger.warning("No ZENV operators found in addon")
            return 0, 0
        
        # Create a new scene for testing
        bpy.ops.wm.read_factory_settings(use_empty=True)
        
        # Test each operator
        for name, obj in inspect.getmembers(module):
            if (inspect.isclass(obj) and 
                hasattr(obj, 'bl_idname') and 
                name.startswith('ZENV_OT_')):
                
                logger.info(f"\nTesting operator: {name}")
                logger.info(f"bl_idname: {obj.bl_idname}")
                logger.info(f"bl_label: {getattr(obj, 'bl_label', 'No label')}")
                
                # First attempt without test object
                success = self.try_operator(obj.bl_idname, logger)
                
                # If failed, try again with test object
                if not success:
                    logger.info("Operator failed. Retrying with test object...")
                    
                    # Create test object if not already created
                    if test_object is None:
                        test_object = self.create_test_object(logger)
                    else:
                        # Ensure test object is selected
                        bpy.ops.object.select_all(action='DESELECT')
                        test_object.select_set(True)
                        bpy.context.view_layer.objects.active = test_object
                    
                    # Try operator again
                    success = self.try_operator(obj.bl_idname, logger)
                
                operators_tested += 1
                if not success:
                    operators_failed += 1
                    logger.error("Operator failed even with test object")
                else:
                    logger.info("Operator succeeded")
        
        # Clean up test object if created
        if test_object is not None:
            bpy.ops.object.select_all(action='DESELECT')
            test_object.select_set(True)
            bpy.context.view_layer.objects.active = test_object
            bpy.ops.object.delete()
            logger.info("Cleaned up test object")
        
        return operators_tested, operators_failed

    def try_operator(self, bl_idname: str, logger: logging.Logger) -> bool:
        """Try to execute an operator and return success status"""
        try:
            # Split operator category and name
            op_category, op_name = bl_idname.split('.')
            
            # Get the operator
            if hasattr(bpy.ops, op_category):
                op = getattr(bpy.ops, op_category)
                if hasattr(op, op_name):
                    # Execute operator
                    result = getattr(op, op_name)()
                    
                    # Check result
                    if result == {'FINISHED'}:
                        return True
                    elif result == {'CANCELLED'}:
                        logger.warning("Operator cancelled - this may be normal for some operators")
                        return False
                    else:
                        logger.warning(f"Operator returned {result}")
                        return False
                else:
                    logger.error(f"Operator {op_name} not found in category {op_category}")
                    return False
            else:
                logger.error(f"Operator category {op_category} not found")
                return False
                
        except Exception as e:
            logger.error(f"Error executing operator: {str(e)}")
            logger.error(traceback.format_exc())
            return False

    def write_summary(self):
        """Write test summary to file"""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        summary_file = self.output_dir / f"test_summary_{timestamp}.txt"
        
        with open(summary_file, 'w') as f:
            f.write("Addon Testing Summary Report\n")
            f.write("=========================\n\n")
            f.write(f"Generated: {datetime.datetime.now()}\n")
            f.write(f"Total addons tested: {len(self.test_results)}\n\n")
            
            # Write results for each addon
            for addon_name, results in self.test_results.items():
                f.write(f"\nAddon: {addon_name}\n")
                f.write("-" * (len(addon_name) + 7) + "\n")
                f.write(f"Operators tested: {results['operators_tested']}\n")
                f.write(f"Operators failed: {results['operators_failed']}\n")
                f.write(f"Log file: {results['log_file'].name}\n")
            
            # Write overall statistics
            total_operators = sum(r['operators_tested'] for r in self.test_results.values())
            total_failed = sum(r['operators_failed'] for r in self.test_results.values())
            
            f.write("\nOverall Statistics\n")
            f.write("=================\n")
            f.write(f"Total operators tested: {total_operators}\n")
            f.write(f"Total operators failed: {total_failed}\n")
            if total_operators > 0:
                f.write(f"Success rate: {((total_operators - total_failed) / total_operators * 100):.1f}%\n")
        
        self.logger.info(f"\nTesting complete. Summary written to: {summary_file}")

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="Test Blender addons")
    parser.add_argument("--addon", type=str, help="Specific addon name to test (without .py extension)")
    
    # Handle Blender's argument passing (everything after -- is passed to the script)
    if "--" in sys.argv:
        args = parser.parse_args(sys.argv[sys.argv.index("--")+1:])
    else:
        args = parser.parse_args([])
    
    return args

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
    
    # Print summary
    print("\nTest Summary:")
    for addon_name, result in tester.test_results.items():
        print(f"\n{addon_name}:")
        print(f"  Log file: {result['log_file']}")
        print(f"  Operators tested: {result['operators_tested']}")
        print(f"  Operators failed: {result['operators_failed']}")

if __name__ == "__main__":
    main()
