"""Print the AI agent's outputs in the terminal.

In VS Code: open this file and click the ▶ "Run Python File" button (top-right),
or run in the terminal:   python ai_outputs.py

It prints 11 sections (PEAS, fine calculation, forward chaining, fuzzy logic, utility score,
heap queue, anti-spam, machine learning, fairness guard, an agent cycle and the guided demo)
and saves them to outputs/ai_outputs.txt. The first run installs the Python packages and
creates the demo data automatically (a few minutes). Node.js is NOT needed for this.
"""
import sys

import run

if __name__ == "__main__":
    sys.argv = [sys.argv[0], "--console"]
    try:
        run.main()
    except run.subprocess.CalledProcessError as exc:
        sys.exit(f"\nCommand failed with exit code {exc.returncode}: {' '.join(map(str, exc.cmd))}")
