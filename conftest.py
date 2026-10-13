# Safety net: the root-level test_*.py files are old manual scripts (they
# build a real BatchProcessor, call YouTube, read the real database...), not
# automated tests. Never let pytest collect them, even via `pytest .`.
# The real test suite lives in tests/.
collect_ignore_glob = ["test_*.py", "test*_script.py"]
