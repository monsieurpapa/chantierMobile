#!/usr/bin/env python
"""
Script to compile translation files (.po to .mo)
Run this after editing .po files to activate translations
"""

import os
import subprocess
import sys
from pathlib import Path

def compile_messages():
    """Compile all .po files to .mo files"""
    
    base_dir = Path(__file__).parent.resolve()
    locale_dir = base_dir / 'locale'
    
    if not locale_dir.exists():
        print(f"Error: Locale directory not found at {locale_dir}")
        return False
    
    languages = ['fr', 'en']
    compiled_count = 0
    
    for lang in languages:
        po_file = locale_dir / lang / 'LC_MESSAGES' / 'django.po'
        mo_file = locale_dir / lang / 'LC_MESSAGES' / 'django.mo'
        
        if not po_file.exists():
            print(f"Warning: {po_file} not found, skipping {lang}")
            continue
        
        try:
            # Use Django's compilemessages
            result = subprocess.run(
                [sys.executable, 'manage.py', 'compilemessages'],
                cwd=str(base_dir),
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                print(f"✓ Compiled {lang} translations: {po_file} -> {mo_file}")
                compiled_count += 1
            else:
                print(f"✗ Error compiling {lang}: {result.stderr}")
        
        except Exception as e:
            print(f"✗ Exception while compiling {lang}: {e}")
    
    if compiled_count > 0:
        print(f"\n✓ Successfully compiled {compiled_count} translation files")
        print("Restart Django server for changes to take effect")
        return True
    else:
        print("\n✗ No translation files compiled")
        return False

if __name__ == '__main__':
    success = compile_messages()
    sys.exit(0 if success else 1)
