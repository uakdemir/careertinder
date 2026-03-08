"""Subprocess runner for executing CLI commands from the dashboard.

Wraps subprocess.Popen to run `python run.py <args>` and stream output
to a Streamlit placeholder incrementally.
"""

import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Use the same Python interpreter as the running process
PYTHON = sys.executable


def run_pipeline_command(
    args: list[str],
    placeholder,
) -> int:
    """Run a CLI command via subprocess and stream output to a Streamlit placeholder.

    Uses Popen with line-by-line stdout reading so the Streamlit placeholder
    updates incrementally (not blocked until completion).

    Args:
        args: Command arguments after 'python run.py' (e.g. ['filter', '--force'])
        placeholder: Streamlit placeholder (.empty() container) for output display

    Returns:
        Process exit code
    """
    run_py = str(Path("run.py").resolve())
    cmd = [PYTHON, run_py, *args]
    logger.info("Running pipeline command: %s", " ".join(cmd))

    output_lines: list[str] = []

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(Path.cwd()),
        )

        if proc.stdout is None:
            placeholder.error("Failed to capture command output")
            return 1

        for line in proc.stdout:
            output_lines.append(line)
            placeholder.code("".join(output_lines))

        proc.wait(timeout=600)
        return proc.returncode

    except subprocess.TimeoutExpired:
        proc.kill()
        output_lines.append("\n--- TIMEOUT (600s) ---\n")
        placeholder.code("".join(output_lines))
        logger.error("Pipeline command timed out: %s", " ".join(cmd))
        return 1

    except Exception as e:
        output_lines.append(f"\n--- ERROR: {e} ---\n")
        placeholder.code("".join(output_lines))
        logger.exception("Pipeline command failed: %s", " ".join(cmd))
        return 1
