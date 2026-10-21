import os

from hypothesis import settings

# Qt tests run headless on every platform.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Mutation runs execute the suite once per mutant: keep property tests small and
# deterministic there (`--hypothesis-profile=mutation`).
settings.register_profile("mutation", max_examples=25, derandomize=True, database=None)
