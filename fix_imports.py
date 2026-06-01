"""
Fix import paths in ASTA implementation
Changes 'from app.' to 'from backend.app.'
"""

import os
import re
from pathlib import Path

def fix_imports_in_file(file_path):
    """Fix import statements in a single file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # Pattern 1: from app.something import
        content = re.sub(
            r'^from app\.([a-zA-Z_][a-zA-Z0-9_\.]*)',
            r'from backend.app.\1',
            content,
            flags=re.MULTILINE
        )
        
        # Pattern 2: import app.something
        content = re.sub(
            r'^import app\.([a-zA-Z_][a-zA-Z0-9_\.]*)',
            r'import backend.app.\1',
            content,
            flags=re.MULTILINE
        )
        
        if content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        return False
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return False

def main():
    """Fix imports in all Python files"""
    
    directories = [
        'backend/app/services',
        'backend/app/workflows',
        'backend/app/core',
        'backend/app/api',
        'backend/app/utils',
    ]
    
    fixed_count = 0
    total_count = 0
    
    print("Fixing import paths...\n")
    
    for directory in directories:
        if not os.path.exists(directory):
            print(f"⚠ Directory not found: {directory}")
            continue
        
        for root, dirs, files in os.walk(directory):
            for file in files:
                if file.endswith('.py'):
                    file_path = os.path.join(root, file)
                    total_count += 1
                    
                    if fix_imports_in_file(file_path):
                        print(f"✓ Fixed: {file_path}")
                        fixed_count += 1
                    else:
                        print(f"  Skipped: {file_path} (no changes needed)")
    
    print(f"\n{'='*60}")
    print(f"Summary:")
    print(f"  Total files checked: {total_count}")
    print(f"  Files modified: {fixed_count}")
    print(f"  Files unchanged: {total_count - fixed_count}")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()
