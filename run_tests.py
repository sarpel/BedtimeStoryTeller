#!/usr/bin/env python3
"""
Test runner for Bedtime Storyteller.
Provides different test execution modes and reporting.
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path
from typing import List, Optional

def run_command(cmd: List[str], capture_output: bool = False) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    print(f"Running: {' '.join(cmd)}")
    
    if capture_output:
        return subprocess.run(cmd, capture_output=True, text=True)
    else:
        return subprocess.run(cmd)

def install_test_dependencies():
    """Install test dependencies."""
    print("Installing test dependencies...")
    
    deps = [
        "pytest>=7.0.0",
        "pytest-asyncio>=0.21.0", 
        "pytest-cov>=4.0.0",
        "pytest-mock>=3.10.0",
        "pytest-timeout>=2.1.0",
        "pytest-xdist>=3.0.0",  # For parallel testing
        "coverage>=7.0.0"
    ]
    
    for dep in deps:
        result = run_command([sys.executable, "-m", "pip", "install", dep])
        if result.returncode != 0:
            print(f"Warning: Failed to install {dep}")

def run_unit_tests(verbose: bool = False, coverage: bool = False) -> int:
    """Run unit tests."""
    print("Running unit tests...")
    
    cmd = [sys.executable, "-m", "pytest", "tests/unit/"]
    
    if verbose:
        cmd.append("-v")
    
    if coverage:
        cmd.extend(["--cov=storyteller", "--cov-report=html", "--cov-report=term"])
    
    cmd.extend(["-m", "unit"])
    
    result = run_command(cmd)
    return result.returncode

def run_integration_tests(verbose: bool = False) -> int:
    """Run integration tests."""
    print("Running integration tests...")
    
    cmd = [sys.executable, "-m", "pytest", "tests/integration/"]
    
    if verbose:
        cmd.append("-v")
    
    cmd.extend(["-m", "integration"])
    
    result = run_command(cmd)
    return result.returncode

def run_hardware_tests(verbose: bool = False, skip_actual_hardware: bool = True) -> int:
    """Run hardware tests."""
    print("Running hardware tests...")
    
    cmd = [sys.executable, "-m", "pytest", "tests/hardware/"]
    
    if verbose:
        cmd.append("-v")
    
    if skip_actual_hardware:
        cmd.extend(["-m", "not actual_hardware"])
    
    cmd.extend(["-m", "hardware"])
    
    result = run_command(cmd)
    return result.returncode

def run_safety_tests(verbose: bool = False) -> int:
    """Run safety and content filtering tests."""
    print("Running safety tests...")
    
    cmd = [sys.executable, "-m", "pytest"]
    
    if verbose:
        cmd.append("-v")
    
    cmd.extend(["-m", "safety"])
    
    result = run_command(cmd)
    return result.returncode

def run_performance_tests(verbose: bool = False) -> int:
    """Run performance tests."""
    print("Running performance tests...")
    
    cmd = [sys.executable, "-m", "pytest"]
    
    if verbose:
        cmd.append("-v")
    
    cmd.extend(["-m", "performance", "--timeout=60"])
    
    result = run_command(cmd)
    return result.returncode

def run_memory_tests(verbose: bool = False) -> int:
    """Run memory usage tests."""
    print("Running memory tests...")
    
    cmd = [sys.executable, "-m", "pytest"]
    
    if verbose:
        cmd.append("-v")
    
    cmd.extend(["-m", "memory"])
    
    result = run_command(cmd)
    return result.returncode

def run_parallel_tests(num_workers: int = 4, verbose: bool = False) -> int:
    """Run tests in parallel."""
    print(f"Running tests in parallel with {num_workers} workers...")
    
    cmd = [
        sys.executable, "-m", "pytest",
        f"-n={num_workers}",
        "--dist=worksteal"
    ]
    
    if verbose:
        cmd.append("-v")
    
    result = run_command(cmd)
    return result.returncode

def run_specific_test(test_path: str, verbose: bool = False) -> int:
    """Run a specific test file or test function."""
    print(f"Running specific test: {test_path}")
    
    cmd = [sys.executable, "-m", "pytest", test_path]
    
    if verbose:
        cmd.append("-v")
    
    result = run_command(cmd)
    return result.returncode

def run_ci_tests() -> int:
    """Run tests suitable for CI environment."""
    print("Running CI test suite...")
    
    cmd = [
        sys.executable, "-m", "pytest",
        "--cov=storyteller",
        "--cov-report=xml",
        "--cov-report=term",
        "--junitxml=test-results.xml",
        "-m", "not hardware",  # Skip hardware tests in CI
        "--timeout=30"
    ]
    
    result = run_command(cmd)
    return result.returncode

def lint_code() -> int:
    """Run code linting."""
    print("Running code linting...")
    
    exit_code = 0
    
    # Try different linters
    linters = [
        (["python", "-m", "ruff", "check", "storyteller/"], "ruff"),
        (["python", "-m", "black", "--check", "storyteller/"], "black"),
        (["python", "-m", "mypy", "storyteller/"], "mypy")
    ]
    
    for cmd, name in linters:
        print(f"Running {name}...")
        result = run_command(cmd, capture_output=True)
        
        if result.returncode != 0:
            print(f"{name} found issues:")
            print(result.stdout)
            if result.stderr:
                print(result.stderr)
            exit_code = 1
        else:
            print(f"{name}: OK")
    
    return exit_code

def generate_coverage_report():
    """Generate detailed coverage report."""
    print("Generating coverage report...")
    
    # Run tests with coverage
    cmd = [
        sys.executable, "-m", "pytest",
        "--cov=storyteller",
        "--cov-report=html:htmlcov",
        "--cov-report=term-missing",
        "--cov-report=json:coverage.json"
    ]
    
    result = run_command(cmd)
    
    if result.returncode == 0:
        print("Coverage report generated:")
        print("  HTML: htmlcov/index.html")
        print("  JSON: coverage.json")
    
    return result.returncode

def check_test_environment():
    """Check if test environment is properly set up."""
    print("Checking test environment...")
    
    issues = []
    
    # Check Python version
    if sys.version_info < (3, 9):
        issues.append(f"Python 3.9+ required, found {sys.version}")
    
    # Check if pytest is available
    try:
        import pytest
        print(f"pytest version: {pytest.__version__}")
    except ImportError:
        issues.append("pytest not installed")
    
    # Check if source code is available
    if not Path("storyteller").exists():
        issues.append("storyteller source code not found")
    
    # Check if test files exist
    if not Path("tests").exists():
        issues.append("tests directory not found")
    
    if issues:
        print("Issues found:")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    else:
        print("Test environment looks good!")
        return 0

def main():
    """Main test runner."""
    parser = argparse.ArgumentParser(description="Bedtime Storyteller Test Runner")
    
    parser.add_argument("--install-deps", action="store_true",
                       help="Install test dependencies")
    parser.add_argument("--check-env", action="store_true",
                       help="Check test environment")
    parser.add_argument("--lint", action="store_true",
                       help="Run code linting")
    parser.add_argument("--coverage", action="store_true",
                       help="Generate coverage report")
    
    # Test type selection
    parser.add_argument("--unit", action="store_true",
                       help="Run unit tests")
    parser.add_argument("--integration", action="store_true", 
                       help="Run integration tests")
    parser.add_argument("--hardware", action="store_true",
                       help="Run hardware tests")
    parser.add_argument("--safety", action="store_true",
                       help="Run safety tests")
    parser.add_argument("--performance", action="store_true",
                       help="Run performance tests")
    parser.add_argument("--memory", action="store_true",
                       help="Run memory tests")
    parser.add_argument("--ci", action="store_true",
                       help="Run CI test suite")
    parser.add_argument("--all", action="store_true",
                       help="Run all tests")
    
    # Test execution options
    parser.add_argument("--parallel", type=int, metavar="N",
                       help="Run tests in parallel with N workers")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Verbose output")
    parser.add_argument("--test", type=str, metavar="PATH",
                       help="Run specific test file or function")
    parser.add_argument("--no-hardware", action="store_true",
                       help="Skip actual hardware tests")
    
    args = parser.parse_args()
    
    # Change to script directory
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    
    exit_code = 0
    
    # Handle utility commands
    if args.install_deps:
        install_test_dependencies()
        return 0
    
    if args.check_env:
        return check_test_environment()
    
    if args.lint:
        exit_code = max(exit_code, lint_code())
    
    if args.coverage:
        exit_code = max(exit_code, generate_coverage_report())
        return exit_code
    
    # Handle test execution
    if args.test:
        exit_code = run_specific_test(args.test, args.verbose)
    elif args.ci:
        exit_code = run_ci_tests()
    elif args.parallel:
        exit_code = run_parallel_tests(args.parallel, args.verbose)
    elif args.all:
        # Run all test suites
        exit_code = max(exit_code, run_unit_tests(args.verbose, False))
        exit_code = max(exit_code, run_integration_tests(args.verbose))
        exit_code = max(exit_code, run_hardware_tests(args.verbose, args.no_hardware))
        exit_code = max(exit_code, run_safety_tests(args.verbose))
    else:
        # Run individual test suites based on flags
        if args.unit:
            exit_code = max(exit_code, run_unit_tests(args.verbose, False))
        
        if args.integration:
            exit_code = max(exit_code, run_integration_tests(args.verbose))
        
        if args.hardware:
            exit_code = max(exit_code, run_hardware_tests(args.verbose, args.no_hardware))
        
        if args.safety:
            exit_code = max(exit_code, run_safety_tests(args.verbose))
        
        if args.performance:
            exit_code = max(exit_code, run_performance_tests(args.verbose))
        
        if args.memory:
            exit_code = max(exit_code, run_memory_tests(args.verbose))
        
        # If no specific tests selected, run basic suite
        if not any([args.unit, args.integration, args.hardware, args.safety, 
                   args.performance, args.memory]):
            print("No specific tests selected, running unit and integration tests...")
            exit_code = max(exit_code, run_unit_tests(args.verbose, False))
            exit_code = max(exit_code, run_integration_tests(args.verbose))
    
    if exit_code == 0:
        print("\n✅ All tests passed!")
    else:
        print("\n❌ Some tests failed!")
    
    return exit_code

if __name__ == "__main__":
    sys.exit(main())