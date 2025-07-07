#!/usr/bin/env python3
"""
System validation script for Bedtime Storyteller.
Tests core functionality without requiring external dependencies.
"""

import sys
import os
import importlib.util
import subprocess
from pathlib import Path

def test_imports():
    """Test that all core modules can be imported."""
    print("=== Testing Module Imports ===")
    
    # Add storyteller to path
    sys.path.insert(0, str(Path(__file__).parent))
    
    modules_to_test = [
        "storyteller.config.settings",
        "storyteller.config.hardware_profiles", 
        "storyteller.providers.base",
        "storyteller.wakeword.loader",
        "storyteller.hal.interface",
        "storyteller.core.agent",
        "storyteller.storage.models",
        "storyteller.utils.safety_filter",
        "storyteller.utils.audio_utils"
    ]
    
    results = {}
    for module_name in modules_to_test:
        try:
            spec = importlib.util.find_spec(module_name)
            if spec is None:
                results[module_name] = "✗ Module not found"
                continue
                
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            results[module_name] = "✓ Import successful"
            
        except ImportError as e:
            results[module_name] = f"✗ Import failed: {e}"
        except Exception as e:
            results[module_name] = f"✗ Error: {e}"
    
    for module, result in results.items():
        print(f"  {module}: {result}")
    
    return all("✓" in result for result in results.values())

def test_file_structure():
    """Test that all required files exist."""
    print("\n=== Testing File Structure ===")
    
    required_files = [
        "storyteller/__init__.py",
        "storyteller/main.py",
        "storyteller/config/settings.py",
        "storyteller/config/hardware_profiles.py",
        "storyteller/providers/base.py",
        "storyteller/wakeword/loader.py",
        "storyteller/hal/interface.py",
        "storyteller/core/agent.py",
        "storyteller/storage/models.py",
        "storyteller/utils/safety_filter.py",
        "storyteller/utils/audio_utils.py",
        "requirements.txt",
        ".env.example",
        "README.md"
    ]
    
    missing_files = []
    for file_path in required_files:
        if not Path(file_path).exists():
            missing_files.append(file_path)
            print(f"  ✗ Missing: {file_path}")
        else:
            print(f"  ✓ Found: {file_path}")
    
    return len(missing_files) == 0

def test_syntax():
    """Test syntax of all Python files."""
    print("\n=== Testing Python Syntax ===")
    
    python_files = list(Path("storyteller").rglob("*.py"))
    syntax_errors = []
    
    for py_file in python_files:
        try:
            with open(py_file, 'r', encoding='utf-8') as f:
                code = f.read()
            
            compile(code, str(py_file), 'exec')
            print(f"  ✓ {py_file}: Syntax OK")
            
        except SyntaxError as e:
            syntax_errors.append(f"{py_file}: {e}")
            print(f"  ✗ {py_file}: Syntax Error - {e}")
        except Exception as e:
            syntax_errors.append(f"{py_file}: {e}")
            print(f"  ✗ {py_file}: Error - {e}")
    
    return len(syntax_errors) == 0

def test_configuration():
    """Test configuration system."""
    print("\n=== Testing Configuration ===")
    
    try:
        # Test basic settings import
        from storyteller.config.settings import Settings
        settings = Settings()
        print("  ✓ Settings class instantiated")
        
        # Test hardware profiles
        from storyteller.config.hardware_profiles import detect_hardware_profile
        profile = detect_hardware_profile()
        print(f"  ✓ Hardware profile detected: {profile.model.value}")
        
        return True
        
    except Exception as e:
        print(f"  ✗ Configuration test failed: {e}")
        return False

def test_memory_usage():
    """Test basic memory usage."""
    print("\n=== Testing Memory Usage ===")
    
    try:
        import psutil
        process = psutil.Process()
        memory_info = process.memory_info()
        memory_mb = memory_info.rss / 1024 / 1024
        
        print(f"  Current memory usage: {memory_mb:.1f} MB")
        
        # Test should pass if under 100MB for basic validation
        if memory_mb < 100:
            print("  ✓ Memory usage within acceptable range for validation")
            return True
        else:
            print("  ⚠ Memory usage higher than expected for validation")
            return False
            
    except ImportError:
        print("  ⚠ psutil not available, skipping memory test")
        return True
    except Exception as e:
        print(f"  ✗ Memory test failed: {e}")
        return False

def main():
    """Run all validation tests."""
    print("Bedtime Storyteller - System Validation")
    print("=" * 50)
    
    tests = [
        ("File Structure", test_file_structure),
        ("Python Syntax", test_syntax),
        ("Module Imports", test_imports),
        ("Configuration", test_configuration),
        ("Memory Usage", test_memory_usage)
    ]
    
    results = {}
    for test_name, test_func in tests:
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"  ✗ {test_name} failed with exception: {e}")
            results[test_name] = False
    
    print("\n" + "=" * 50)
    print("VALIDATION SUMMARY")
    print("=" * 50)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All validation tests passed! Core system is ready.")
        return 0
    else:
        print("❌ Some validation tests failed. Please review the issues above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())