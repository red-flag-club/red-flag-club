import pathlib
import sys

# Make `src` importable as a package regardless of the directory pytest is
# invoked from.
sys.path.insert(0, str(pathlib.Path(__file__).parent))
