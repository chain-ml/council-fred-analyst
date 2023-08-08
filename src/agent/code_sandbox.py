from contextlib import contextmanager
import subprocess
import sys

"""
Instructions to set up code sandbox.
1. cd to 'this' directory
2. `python -m venv code_sandbox`
3. `source code_sandbox/bin/activate`
4. pip install pandas plotly
"""

@contextmanager
def sandbox_environment(sandbox_path):
    # Save the original sys.path and sys.modules
    original_sys_path = sys.path.copy()
    original_sys_modules = sys.modules.copy()

    try:
        # Add the virtual environment path to sys.path
        sys.path.insert(0, sandbox_path)

        # - Disable filesystem access:
        # sys.modules["os"] = None

        # - Disable network access:
        sys.modules["_socket"] = None
        sys.modules["socket"] = None
        sys.modules["urllib"] = None

        yield

    finally:
        # Restore the original sys.path and sys.modules
        sys.path = original_sys_path
        sys.modules = original_sys_modules


def run_code_in_sandbox(code, sandbox_path):
    with sandbox_environment(sandbox_path):
        print("Starting execution...")
        execution = subprocess.run([f"{sandbox_path}/python", "-c", code], capture_output=True)
        return {
            "code": code,
            "returncode": execution.returncode,
            "stdout": execution.stdout.decode(),
            "stderr": execution.stderr.decode(),
        }
