#!/usr/bin/env python3
"""
Release tool for FishBroWFS_V2.

Generates release packages (txt or zip) excluding sensitive information like .git
"""

from __future__ import annotations

import os
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path


def should_exclude(path: Path, repo_root: Path) -> bool:
    """
    Check if a path should be excluded from release.
    
    Excludes:
    - .git directory and all its contents
    - __pycache__ directories
    - .pyc, .pyo files
    - Common build/test artifacts
    """
    path_str = str(path)
    path_parts = path.parts
    
    # Exclude .git directory
    if '.git' in path_parts:
        return True
    
    # Exclude cache directories
    if '__pycache__' in path_parts:
        return True
    
    # Exclude bytecode files
    if path.suffix in ('.pyc', '.pyo'):
        return True
    
    # Exclude common build/test artifacts
    exclude_names = {
        '.pytest_cache', '.mypy_cache', '.ruff_cache',
        '.coverage', 'htmlcov', '.tox', 'dist', 'build',
        '*.egg-info', '.eggs'
    }
    
    for name in exclude_names:
        if name in path_parts or path.name.startswith(name.replace('*', '')):
            return True
    
    # Exclude GM_Huang itself from the release (optional, but makes sense)
    # Actually, let's include it since it's part of the project structure
    
    return False


def get_python_files(repo_root: Path) -> list[Path]:
    """Get all Python files in the repository, excluding sensitive paths."""
    python_files = []
    
    for py_file in repo_root.rglob('*.py'):
        if not should_exclude(py_file, repo_root):
            python_files.append(py_file)
    
    return sorted(python_files)


def get_directory_structure(repo_root: Path) -> str:
    """Generate a text representation of directory structure."""
    lines = []
    
    def walk_tree(directory: Path, prefix: str = '', is_last: bool = True):
        """Recursively walk directory tree and build structure."""
        if should_exclude(directory, repo_root):
            return
        
        # Skip if it's the repo root itself
        if directory == repo_root:
            lines.append(f"{directory.name}/")
        else:
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{directory.name}/")
        
        # Get subdirectories and files
        try:
            items = sorted([p for p in directory.iterdir() 
                          if not should_exclude(p, repo_root)])
            dirs = [p for p in items if p.is_dir()]
            files = [p for p in items if p.is_file() and p.suffix == '.py']
            
            # Process directories
            for i, item in enumerate(dirs):
                is_last_item = (i == len(dirs) - 1) and len(files) == 0
                extension = "    " if is_last else "│   "
                walk_tree(item, prefix + extension, is_last_item)
            
            # Process Python files
            for i, file in enumerate(files):
                is_last_item = i == len(files) - 1
                connector = "└── " if is_last_item else "├── "
                lines.append(f"{prefix}{'    ' if is_last else '│   '}{connector}{file.name}")
        except PermissionError:
            pass
    
    walk_tree(repo_root)
    return "\n".join(lines)


def generate_release_txt(repo_root: Path, output_path: Path) -> None:
    """Generate a text file with directory structure and Python code."""
    print(f"Generating release TXT: {output_path}")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        # Header
        f.write("=" * 80 + "\n")
        f.write(f"FishBroWFS_V2 Release Package\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 80 + "\n\n")
        
        # Directory structure
        f.write("DIRECTORY STRUCTURE\n")
        f.write("-" * 80 + "\n")
        f.write(get_directory_structure(repo_root))
        f.write("\n\n")
        
        # Python files and their content
        f.write("=" * 80 + "\n")
        f.write("PYTHON FILES AND CODE\n")
        f.write("=" * 80 + "\n\n")
        
        python_files = get_python_files(repo_root)
        
        for py_file in python_files:
            relative_path = py_file.relative_to(repo_root)
            f.write(f"\n{'=' * 80}\n")
            f.write(f"FILE: {relative_path}\n")
            f.write(f"{'=' * 80}\n\n")
            
            try:
                content = py_file.read_text(encoding='utf-8')
                f.write(content)
                if not content.endswith('\n'):
                    f.write('\n')
            except Exception as e:
                f.write(f"[ERROR: Could not read file: {e}]\n")
            
            f.write("\n")
    
    print(f"✓ Release TXT generated: {output_path}")


def generate_release_zip(repo_root: Path, output_path: Path) -> None:
    """Generate a zip file of the project, excluding sensitive information."""
    print(f"Generating release ZIP: {output_path}")
    
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        python_files = get_python_files(repo_root)
        
        # Also include non-Python files that are important
        important_extensions = {'.toml', '.txt', '.md', '.yml', '.yaml'}
        important_files = []
        
        for ext in important_extensions:
            for file in repo_root.rglob(f'*{ext}'):
                if not should_exclude(file, repo_root):
                    important_files.append(file)
        
        all_files = sorted(set(python_files + important_files))
        
        for file_path in all_files:
            relative_path = file_path.relative_to(repo_root)
            zipf.write(file_path, relative_path)
            print(f"  Added: {relative_path}")
    
    print(f"✓ Release ZIP generated: {output_path}")
    print(f"  Total files: {len(all_files)}")


def get_git_sha(repo_root: Path) -> str:
    """
    Get short git SHA for current HEAD.
    
    Returns empty string if git is not available or not in a git repo.
    Does not fail if git command fails (non-blocking).
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        # Git not available or command failed - silently skip
        pass
    return ""


def main() -> None:
    """Main entry point."""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python release_tool.py [txt|zip]")
        sys.exit(1)
    
    mode = sys.argv[1].lower()
    
    # Get repo root (parent of GM_Huang)
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent
    
    # Generate output filename with timestamp and optional git SHA
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    project_name = repo_root.name
    
    git_sha = get_git_sha(repo_root)
    git_suffix = f"-{git_sha}" if git_sha else ""
    
    if mode == 'txt':
        output_path = repo_root / f"{project_name}_release_{timestamp}{git_suffix}.txt"
        generate_release_txt(repo_root, output_path)
    elif mode == 'zip':
        output_path = repo_root / f"{project_name}_release_{timestamp}{git_suffix}.zip"
        generate_release_zip(repo_root, output_path)
    else:
        print(f"Unknown mode: {mode}. Use 'txt' or 'zip'")
        sys.exit(1)


if __name__ == "__main__":
    main()

