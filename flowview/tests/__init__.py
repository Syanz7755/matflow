"""FlowView's own test suite.

Hermetic by construction: every test builds its fixtures inside a
:class:`tempfile.TemporaryDirectory`, points ``MATFLOW_DATA_ROOT`` at that directory, and never
imports ``backend`` at module import time. The suite runs both under
``python -m unittest discover`` and under ``pytest``.
"""
