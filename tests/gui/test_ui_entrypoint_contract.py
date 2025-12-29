"""Guard test ensuring the UI entrypoint correctly calls ui.run()."""

import re
from pathlib import Path


def read_file_content(path: Path) -> str:
    """Return file content as a string."""
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def test_entrypoint_calls_ui_run():
    """Verify that the official UI entrypoint (main.py) calls ui.run().

    This guard ensures we never regress to the state where the NiceGUI server
    fails to start because ui.run() is missing.
    """
    repo_root = Path(__file__).parent.parent.parent
    main_file = repo_root / 'main.py'
    app_file = repo_root / 'src' / 'gui' / 'nicegui' / 'app.py'

    # 1. main.py must call start_ui (which must call ui.run)
    main_content = read_file_content(main_file)
    assert 'start_ui(' in main_content, (
        "main.py does not call start_ui (the UI entrypoint)"
    )
    # Ensure start_ui is imported from gui.nicegui.app
    assert 'from gui.nicegui.app import start_ui' in main_content, (
        "main.py does not import start_ui correctly"
    )

    # 2. app.py must define start_ui
    app_content = read_file_content(app_file)
    assert 'def start_ui' in app_content, (
        "app.py does not define start_ui function"
    )

    # 3. app.py must contain a call to ui.run(...)
    assert 'ui.run(' in app_content, (
        "app.py does not call ui.run() – NiceGUI server will not start"
    )

    # 4. Ensure ui.run is not guarded by a wrong __name__ condition inside app.py
    # (If ui.run appears inside a `if __name__ == "__main__":` block, it won't run when imported.)
    # We'll check that there is no 'if __name__ == "__main__"' before ui.run in the same file.
    lines = app_content.split('\n')
    ui_run_line = None
    for i, line in enumerate(lines):
        if 'ui.run(' in line:
            ui_run_line = i
            break
    if ui_run_line is not None:
        # Check preceding lines for a __main__ guard
        preceding = '\n'.join(lines[:ui_run_line])
        if re.search(r'if\s+__name__\s*==\s*["\']__main__["\']', preceding):
            # This is okay only if the guard also includes "__mp_main__"
            if '__mp_main__' not in preceding:
                raise AssertionError(
                    "ui.run() is guarded by a plain __name__ == '__main__' "
                    "without __mp_main__, which may break multiprocessing."
                )

    # 5. Ensure ui.run is called with at least host and port arguments (optional)
    # We'll just trust the call.

    # If we reach here, the entrypoint contract is satisfied.
    # No need to actually start the server in a test.