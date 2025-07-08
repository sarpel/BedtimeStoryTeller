#!/usr/bin/env python3
"""
Quick patch script to fix the main.py indentation error.
"""

import re

def fix_main_py():
    """Fix the indentation error in main.py"""
    
    # Read the current main.py
    with open('storyteller/main.py', 'r') as f:
        content = f.read()
    
    # Find and fix the problematic section
    # Look for the function definition line and ensure proper indentation
    lines = content.split('\n')
    
    # Fix the specific indentation issue
    fixed_lines = []
    inside_click_block = False
    
    for i, line in enumerate(lines):
        # Detect if we're in the CLICK_AVAILABLE block
        if 'if CLICK_AVAILABLE:' in line:
            inside_click_block = True
            fixed_lines.append(line)
            continue
        elif inside_click_block and line.strip() == '' and (i + 1 < len(lines)) and not lines[i + 1].startswith('    '):
            # End of CLICK_AVAILABLE block
            inside_click_block = False
            fixed_lines.append(line)
            continue
        
        if inside_click_block:
            # Ensure all lines in CLICK_AVAILABLE block are properly indented
            if line.strip() and not line.startswith('    '):
                # This line needs to be indented
                fixed_lines.append('    ' + line)
            else:
                fixed_lines.append(line)
        else:
            fixed_lines.append(line)
    
    # Write the fixed content back
    with open('storyteller/main.py', 'w') as f:
        f.write('\n'.join(fixed_lines))
    
    print("✅ Fixed indentation in main.py")

def create_simple_runner():
    """Create a simple runner script that works without CLI"""
    
    runner_content = '''#!/usr/bin/env python3
"""
Simple runner for Bedtime Storyteller that bypasses CLI issues.
"""

import asyncio
import sys
import os

# Add current directory to Python path
sys.path.insert(0, '.')

async def main():
    """Run the storyteller service without CLI dependencies."""
    try:
        # Import the simple main
        from storyteller.simple_main import run_service
        
        # Run the service
        exit_code = await run_service(daemon=False)
        return exit_code
        
    except ImportError:
        print("❌ simple_main.py not found, trying direct approach...")
        
        # Direct approach without CLI
        from storyteller.simple_main import StorytellerApplication
        
        app = StorytellerApplication()
        await app.initialize()
        await app.run()
        return 0
    
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
'''
    
    with open('run_storyteller.py', 'w') as f:
        f.write(runner_content)
    
    # Make it executable
    import stat
    st = os.stat('run_storyteller.py')
    os.chmod('run_storyteller.py', st.st_mode | stat.S_IEXEC)
    
    print("✅ Created run_storyteller.py")

if __name__ == "__main__":
    print("🔧 Applying quick fix for main.py indentation error...")
    
    try:
        fix_main_py()
        create_simple_runner()
        
        print("")
        print("✅ Quick fix applied successfully!")
        print("")
        print("Now you can run:")
        print("  python3 run_storyteller.py")
        print("  OR")
        print("  python3 -m storyteller.simple_main")
        
    except Exception as e:
        print(f"❌ Fix failed: {e}")
        print("")
        print("Alternative: Use the simple main directly:")
        print("  python3 -m storyteller.simple_main")