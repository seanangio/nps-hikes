"""
Main orchestrator for the profiling system.

This orchestrator manages the execution of all profiling modules,
handles dependencies, and provides a clean interface for running
profiling operations.

Key Features:
- Dynamic module loading and execution
- Dependency management between modules
- Configurable module enable/disable
- Error handling with optional continuation
- Comprehensive logging and reporting

Available Modules:
- nps_parks: NPS park statistics and data analysis
- nps_geography: NPS geographic and spatial analysis
- data_quality: Cross-table data quality and validation checks
- visualization: Data visualization and maps
- osm_hikes: OSM hiking trails analysis
- tnm_hikes: TNM hiking trails analysis
- data_freshness: Data freshness monitoring across all tables

Examples:
  # Run all enabled modules
  python profiling/orchestrator.py

  # Run specific modules
  python profiling/orchestrator.py osm_hikes tnm_hikes

  # Run with help
  python profiling/orchestrator.py --help

  # List available modules
  python profiling/orchestrator.py --list-modules

  # Run with verbose output
  python profiling/orchestrator.py --verbose osm_hikes
"""

import sys
import argparse
from typing import List, Dict, Any
from dotenv import load_dotenv

# Load environment variables before importing config-dependent modules
load_dotenv()

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from profiling.config import PROFILING_MODULES, PROFILING_SETTINGS
from profiling.utils import ProfilingLogger


class ProfilingOrchestrator:
    """Main orchestrator for profiling operations."""

    def __init__(self):
        self.logger = ProfilingLogger("orchestrator")
        self.results = {}
        self.failed_modules = []

    def _check_dependencies(self, module_name: str) -> bool:
        """Check if module dependencies are satisfied."""
        module_config = PROFILING_MODULES[module_name]
        dependencies = module_config.get("dependencies", [])

        for dep in dependencies:
            if dep not in self.results:
                self.logger.error(
                    f"Module {module_name} depends on {dep}, but {dep} hasn't run yet"
                )
                return False
        return True

    def _load_module(self, module_name: str):
        """Dynamically load a profiling module."""
        try:
            # Import the module dynamically
            module = __import__(f"profiling.modules.{module_name}", fromlist=[""])

            # Look for the main run function
            if hasattr(module, f"run_{module_name}"):
                return getattr(module, f"run_{module_name}")
            elif hasattr(module, "run_all"):
                return module.run_all
            else:
                self.logger.error(f"No run function found in module {module_name}")
                return None

        except ImportError as e:
            self.logger.error(f"Failed to import module {module_name}: {e}")
            return None

    def run_module(self, module_name: str) -> bool:
        """Run a single profiling module."""
        if module_name not in PROFILING_MODULES:
            self.logger.error(f"Unknown module: {module_name}")
            return False

        module_config = PROFILING_MODULES[module_name]

        if not module_config["enabled"]:
            self.logger.info(f"Module {module_name} is disabled, skipping")
            return True

        # Check dependencies
        if not self._check_dependencies(module_name):
            return False

        self.logger.info(
            f"Running module: {module_name} - {module_config['description']}"
        )

        try:
            # Load and run the module
            run_function = self._load_module(module_name)
            if run_function:
                result = run_function()
                self.results[module_name] = result
                self.logger.success(f"Module {module_name} completed successfully")
                return True
            else:
                self.failed_modules.append(module_name)
                return False

        except Exception as e:
            self.logger.error(f"Module {module_name} failed: {e}")
            self.failed_modules.append(module_name)

            if not PROFILING_SETTINGS["continue_on_error"]:
                raise

            return False

    def run_all_modules(self) -> Dict[str, Any]:
        """Run all enabled profiling modules in dependency order."""
        self.logger.info("Starting profiling orchestration...")
        self.logger.info(f"Output directory: {PROFILING_SETTINGS['output_directory']}")

        # Get list of enabled modules
        enabled_modules = [
            name for name, config in PROFILING_MODULES.items() if config["enabled"]
        ]

        self.logger.info(f"Enabled modules: {', '.join(enabled_modules)}")

        # Simple dependency resolution (topological sort would be better for complex deps)
        for module_name in enabled_modules:
            self.run_module(module_name)

        # Summary
        successful_count = len(self.results)
        failed_count = len(self.failed_modules)
        total_count = len(enabled_modules)

        self.logger.info(
            f"Profiling completed: {successful_count}/{total_count} modules successful"
        )

        if self.failed_modules:
            self.logger.error(f"Failed modules: {', '.join(self.failed_modules)}")

        return self.results

    def run_specific_modules(self, module_names: List[str]) -> Dict[str, Any]:
        """Run specific modules by name."""
        for module_name in module_names:
            if module_name in PROFILING_MODULES:
                self.run_module(module_name)
            else:
                self.logger.error(f"Unknown module: {module_name}")

        return self.results


# Convenience functions for external use
def run_all_profiling():
    """
    Run all enabled profiling modules.

    This function executes all profiling modules that are enabled in the configuration.
    Modules can be enabled/disabled by setting the 'enabled' flag in config.py.

    Returns:
        Dict[str, Any]: Results from all executed modules
    """
    orchestrator = ProfilingOrchestrator()
    return orchestrator.run_all_modules()


def run_specific_profiling(module_names: List[str]):
    """Run specific profiling modules."""
    orchestrator = ProfilingOrchestrator()
    return orchestrator.run_specific_modules(module_names)


def list_available_modules():
    """List all available profiling modules with their status and description."""
    print("Available Profiling Modules:")
    print("=" * 50)

    for module_name, config in PROFILING_MODULES.items():
        status = "✓ Enabled" if config["enabled"] else "✗ Disabled"
        print(f"{module_name:20} {status}")
        print(f"{'':20} {config['description']}")
        if config.get("dependencies"):
            print(f"{'':20} Dependencies: {', '.join(config['dependencies'])}")
        print()


def create_argument_parser():
    """Create and configure the argument parser for CLI."""
    parser = argparse.ArgumentParser(
        description="Profiling system orchestrator for NPS hikes data analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                              # Run all enabled modules
  %(prog)s osm_hikes tnm_hikes          # Run specific modules
  %(prog)s --list-modules               # List all available modules
  %(prog)s --verbose data_freshness     # Run with verbose output
  %(prog)s --help                       # Show this help message

Available Modules:
  nps_parks      - NPS park statistics and data analysis
  nps_geography  - NPS geographic and spatial analysis
  data_quality   - Cross-table data quality and validation checks
  visualization  - Data visualization and maps
  osm_hikes      - OSM hiking trails analysis
  tnm_hikes      - TNM hiking trails analysis
  data_freshness - Data freshness monitoring across all tables
        """,
    )

    parser.add_argument(
        "modules",
        nargs="*",
        help="Specific modules to run (default: run all enabled modules)",
    )

    parser.add_argument(
        "--list-modules",
        action="store_true",
        help="List all available modules with their status and description",
    )

    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")

    return parser


# CLI interface
if __name__ == "__main__":
    parser = create_argument_parser()
    args = parser.parse_args()

    if args.list_modules:
        list_available_modules()
        sys.exit(0)

    if args.verbose:
        # Set logging level to DEBUG for verbose output
        import logging
        logging.getLogger().setLevel(logging.DEBUG)
        # Also update our orchestrator logger
        orchestrator.logger.setLevel(logging.DEBUG)

    if args.modules:
        # Run specific modules
        print(f"Running modules: {', '.join(args.modules)}")
        run_specific_profiling(args.modules)
    else:
        # Run all modules
        print("Running all enabled modules...")
        run_all_profiling()
