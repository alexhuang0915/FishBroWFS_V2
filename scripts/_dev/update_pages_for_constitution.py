#!/usr/bin/env python3
"""Update all 7 pages to use page_shell from UI Constitution."""
import os
import re
import sys
from pathlib import Path

# Path to pages directory
PAGES_DIR = Path("src/gui/nicegui/pages")
PAGE_FILES = [
    "dashboard.py",
    "wizard.py", 
    "history.py",
    "candidates.py",
    "portfolio.py",
    "deploy.py",
    "settings.py",
]

# Template for import addition
IMPORT_LINE = "from ..constitution.page_shell import page_shell\n"

# Pattern to find render() function start
RENDER_PATTERN = r"def render\(\) -> None:"

def update_page(filepath: Path) -> bool:
    """Update a single page file to use page_shell."""
    try:
        content = filepath.read_text()
        
        # Check if already has page_shell import
        if "from ..constitution.page_shell import page_shell" in content:
            print(f"  ✓ {filepath.name} already has page_shell import")
            return True
        
        # Add import after other imports
        lines = content.splitlines()
        import_added = False
        new_lines = []
        
        for i, line in enumerate(lines):
            new_lines.append(line)
            # Look for the last import line before render function
            if line.strip().startswith("from ") or line.strip().startswith("import "):
                # Check if next line is not an import
                if i + 1 < len(lines) and not (lines[i+1].strip().startswith("from ") or lines[i+1].strip().startswith("import ")):
                    # Add our import after this one
                    new_lines.append(IMPORT_LINE)
                    import_added = True
        
        if not import_added:
            # Fallback: add after the last import we can find
            for i in range(len(new_lines)-1, -1, -1):
                if new_lines[i].strip().startswith("from ") or new_lines[i].strip().startswith("import "):
                    new_lines.insert(i+1, IMPORT_LINE)
                    import_added = True
                    break
        
        # Now wrap the render function content
        content = "\n".join(new_lines)
        
        # Find the render function and wrap its content
        # This is a simple approach - we'll look for "def render() -> None:" and the indented block
        # For simplicity, we'll use a regex to capture the function body
        # This is a bit complex, so we'll do a simpler approach: manually update each file
        
        print(f"  → {filepath.name}: Added import")
        filepath.write_text(content)
        return True
        
    except Exception as e:
        print(f"  ✗ {filepath.name}: {e}")
        return False

def main():
    print("Updating pages for UI Constitution...")
    
    os.chdir(Path(__file__).parent.parent.parent)  # Go to project root
    
    updated = 0
    for page_file in PAGE_FILES:
        filepath = PAGES_DIR / page_file
        if not filepath.exists():
            print(f"  ! {page_file} not found")
            continue
        
        print(f"Processing {page_file}...")
        if update_page(filepath):
            updated += 1
    
    print(f"\nUpdated {updated}/{len(PAGE_FILES)} pages")
    
    # Now we need to manually wrap each render function
    print("\nNote: Each render function needs to be manually wrapped with page_shell.")
    print("Example pattern:")
    print("""
def render() -> None:
    def render_content():
        # Original content here
        ...
    
    page_shell("Page Title", render_content)
""")
    
    return 0 if updated == len(PAGE_FILES) else 1

if __name__ == "__main__":
    sys.exit(main())