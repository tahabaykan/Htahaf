#!/usr/bin/env python3
"""
Terminal Output Tee Wrapper
============================

Usage:  python _tee_wrapper.py <log_file> <script.py> [args...]

Runs the given Python script as a subprocess using the SAME Python interpreter,
piping ALL stdout+stderr to:
  1. The current terminal (so you see everything live)
  2. A log file (so it survives after the terminal is closed)

The log file includes a header with the start timestamp and command.
"""

import sys
import os
import subprocess
import time
from datetime import datetime


def main():
    if len(sys.argv) < 3:
        print("Usage: python _tee_wrapper.py <log_file> <script.py> [args...]")
        sys.exit(1)

    log_file = sys.argv[1]
    script_and_args = sys.argv[2:]

    # Use the same Python interpreter that is running this wrapper
    python_exe = sys.executable
    cmd = [python_exe, "-u"] + script_and_args

    # Ensure log directory exists
    log_dir = os.path.dirname(log_file)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    # Banner
    start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cmd_str = " ".join(cmd)
    banner = (
        f"\n{'='*80}\n"
        f"  TERMINAL SESSION LOG\n"
        f"  Started: {start_time}\n"
        f"  Python:  {python_exe}\n"
        f"  Script:  {' '.join(script_and_args)}\n"
        f"  Log:     {log_file}\n"
        f"{'='*80}\n"
    )

    # Print banner to console
    sys.stdout.write(banner)
    sys.stdout.flush()

    # Open log file
    with open(log_file, "w", encoding="utf-8", errors="replace") as f:
        f.write(banner)
        f.flush()

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=0,  # Unbuffered for real-time
            )

            # Read line-by-line for real-time output
            while True:
                line = proc.stdout.readline()
                if not line and proc.poll() is not None:
                    break
                if line:
                    decoded = line.decode("utf-8", errors="replace")
                    sys.stdout.write(decoded)
                    sys.stdout.flush()
                    f.write(decoded)
                    f.flush()

            # Capture any remaining output
            remaining = proc.stdout.read()
            if remaining:
                decoded = remaining.decode("utf-8", errors="replace")
                sys.stdout.write(decoded)
                sys.stdout.flush()
                f.write(decoded)
                f.flush()

            exit_code = proc.returncode

        except KeyboardInterrupt:
            proc.terminate()
            exit_code = -1
        except Exception as e:
            error_msg = f"\n[TEE_WRAPPER] Error: {e}\n"
            sys.stdout.write(error_msg)
            f.write(error_msg)
            exit_code = 1

        # Footer
        end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        footer = (
            f"\n{'='*80}\n"
            f"  SESSION ENDED: {end_time}  |  Exit Code: {exit_code}\n"
            f"{'='*80}\n"
        )
        sys.stdout.write(footer)
        sys.stdout.flush()
        f.write(footer)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
