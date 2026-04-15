#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler to prevent "forrtl: error (200)"
# This must be set BEFORE importing any packages that use MKL (NumPy, SciPy, etc.)
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'


class _TeeStream:
    """Duplicates writes to the original console stream and a log file."""

    def __init__(self, original, log_file):
        self._original = original
        self._log_file = log_file

    def write(self, data):
        self._original.write(data)
        try:
            self._log_file.write(data)
            self._log_file.flush()
        except Exception:
            pass
        return len(data) if isinstance(data, str) else None

    def flush(self):
        self._original.flush()
        try:
            self._log_file.flush()
        except Exception:
            pass

    def fileno(self):
        return self._original.fileno()

    def isatty(self):
        return self._original.isatty()

    def __getattr__(self, name):
        return getattr(self._original, name)


def _setup_log_tee():
    """Redirect stdout and stderr to both the console and tlamatini.log."""
    if getattr(sys, 'frozen', False):
        log_dir = os.path.dirname(sys.executable)
    else:
        log_dir = os.path.dirname(os.path.abspath(__file__))

    log_path = os.path.join(log_dir, 'tlamatini.log')
    try:
        log_file = open(log_path, 'w', encoding='utf-8')  # noqa: SIM115
    except OSError:
        return

    sys.stdout = _TeeStream(sys.stdout, log_file)
    sys.stderr = _TeeStream(sys.stderr, log_file)


_setup_log_tee()


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tlamatini.settings')

    # --- .FLW File Association Support ---
    # When running as a frozen executable (PyInstaller) and the sole argument
    # is a .flw file path (e.g. from double-clicking in Explorer), we:
    #   1. Store the file path in an environment variable for Django views
    #   2. Rewrite sys.argv so Django starts the web server
    # If running frozen WITHOUT a .flw argument, clear any stale env var
    # left over from a previous run so no file auto-opens.
    if getattr(sys, 'frozen', False):
        if len(sys.argv) == 2:
            candidate = sys.argv[1]
            if candidate.lower().endswith('.flw') and not candidate.startswith('-'):
                # Normalize and store the .flw file path
                flw_path = os.path.abspath(candidate)
                os.environ['SYSTEMAGENT_FLW_FILE'] = flw_path
                print(f"--- [FLW] Flow file detected: {flw_path}")
                print("--- [FLW] Rewriting argv to start server...")
                # Replace argv so Django starts the server instead of
                # interpreting the .flw path as a management command
                sys.argv = [sys.argv[0], 'runserver', '--noreload', '0.0.0.0:8000']
            else:
                # Argument is not a .flw file — clear any stale env var
                os.environ.pop('SYSTEMAGENT_FLW_FILE', None)
        else:
            # No .flw argument provided — clear any stale env var
            os.environ.pop('SYSTEMAGENT_FLW_FILE', None)

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHON_HOME environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
