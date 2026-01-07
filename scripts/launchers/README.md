# FishBroWFS Windows Launcher

## Purpose
This directory contains documentation for the official Windows launcher for the FishBroWFS Desktop UI. The launcher enables Windows users to start the Desktop UI via WSL (Windows Subsystem for Linux) with a single double-click.

## File Location
The Windows launcher has been promoted to the repository root as the **sole human entrypoint**:
- `FishBroWFS_UI.bat` - Located in the repository root (not in this directory)

## How to Use
1. **Prerequisites**:
   - Windows 10/11 with WSL 2 installed and enabled
   - Ubuntu (or another Linux distribution) installed in WSL
   - FishBroWFS_V2 project cloned to `/home/fishbro/FishBroWFS_V2` inside WSL
   - Python virtual environment (`.venv`) set up in the project

2. **Launch the UI**:
   - Double-click `FishBroWFS_UI.bat` from the repository root in Windows Explorer
   - The script will:
     - Check WSL availability
     - Verify the project path exists
     - Activate the Python virtual environment
     - Launch the Desktop UI via `scripts/desktop_launcher.py`

3. **Configuration** (optional):
   - Edit `FishBroWFS_UI.bat` in the repository root to change the WSL distribution:
     ```batch
     set WSL_DISTRO=Ubuntu  ; Change to your WSL distribution name
     ```

## WSL Requirement
The launcher requires Windows Subsystem for Linux (WSL) because:
- The FishBroWFS Desktop UI runs on Linux (PySide6, supervisor, etc.)
- WSL provides a Linux environment without dual-boot or VM overhead
- All project dependencies and virtual environments are Linux-based

To install WSL:
```powershell
# Run as Administrator in PowerShell
wsl --install
```

## Known Failure Modes

### 1. WSL Not Installed
**Symptom**: "ERROR: WSL (Windows Subsystem for Linux) is not installed or not in PATH"
**Solution**: Install WSL via `wsl --install` or enable from Windows Features.

### 2. Wrong WSL Distribution
**Symptom**: "ERROR: WSL distribution 'Ubuntu' not found"
**Solution**: Update the `WSL_DISTRO` variable in the batch file to match your installed distribution name.

### 3. Project Path Incorrect
**Symptom**: WSL errors about directory not found
**Solution**: Ensure the project is cloned to `/home/fishbro/FishBroWFS_V2` inside WSL, or modify the `PROJECT_PATH` variable.

### 4. Virtual Environment Missing
**Symptom**: Python import errors or "No module named" errors
**Solution**: Set up the virtual environment in WSL:
```bash
cd /home/fishbro/FishBroWFS_V2
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 5. Port 8000 Already Occupied
**Symptom**: Desktop UI shows port conflict error
**Solution**: Stop any other services using port 8000, or restart WSL.

## Important Note: Makefile is NOT a Launcher
**CRITICAL**: The `Makefile` in the project root is **NOT** a Windows launcher. It is:
- A Linux/macOS build tool for developers
- Requires GNU Make and a Linux shell
- Not executable on Windows native CMD/PowerShell

The `FishBroWFS_UI.bat` file in the repository root is the **ONLY** supported Windows entrypoint for operators.

## Technical Details
- **Entrypoint**: `scripts/desktop_launcher.py` (canonical Python launcher)
- **WSL Command**: `wsl -d <distro> -- bash -lc "cd /home/fishbro/FishBroWFS_V2 && source .venv/bin/activate && python scripts/desktop_launcher.py"`
- **Virtual Environment**: Uses `.venv` in project root (standard FishBroWFS setup)
- **Error Handling**: Script includes comprehensive error checking, logging to `%TEMP%\FishBroWFS_UI_launcher.log`, and `pause` to keep window open on failure

## Validation
To validate the launcher works:
1. Double-click `FishBroWFS_UI.bat` from the repository root
2. Observe:
   - WSL starts
   - Virtual environment activates
   - Desktop UI window opens
   - No error messages in console

## Support
For issues with the launcher, check:
1. WSL installation and distribution
2. Project path correctness
3. Virtual environment setup
4. Log file: `%TEMP%\FishBroWFS_UI_launcher.log`