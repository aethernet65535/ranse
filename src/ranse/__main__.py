"""python -m ranse"""

# Absolute on purpose: ranse.spec uses this module as the frozen app's
# entry script, and PyInstaller runs it as a top-level ``__main__`` with no
# parent package, where the relative spelling dies at startup with
# "attempted relative import with no known parent package".
from ranse.cli import main

if __name__ == "__main__":
    main()
