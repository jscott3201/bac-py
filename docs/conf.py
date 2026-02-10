"""Sphinx configuration for bac-py documentation."""

import sys
from pathlib import Path

# -- Path setup --------------------------------------------------------------
# Add the source directory so autodoc can import modules without requiring
# the package to be installed.

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from bac_py import __version__

project = "bac-py"
author = "bac-py contributors"
copyright = "2025, bac-py contributors"

version = __version__
release = version

# -- General configuration ---------------------------------------------------

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "sphinx_autodoc_typehints",
]

master_doc = "index"
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]
language = "en"

# -- Autodoc -----------------------------------------------------------------

autodoc_member_order = "bysource"
autodoc_typehints = "description"
autodoc_typehints_format = "short"
autodoc_default_options = {
    "members": True,
    "show-inheritance": True,
    "undoc-members": False,
}
autodoc_mock_imports = ["orjson"]

# -- sphinx-autodoc-typehints ------------------------------------------------

always_use_bars_union = True
typehints_defaults = "braces"

# -- Intersphinx -------------------------------------------------------------

intersphinx_mapping = {
    "python": ("https://docs.python.org/3.13", None),
}

# -- HTML output -------------------------------------------------------------

html_theme = "furo"
html_static_path = ["_static"]
html_title = f"bac-py {version}"

# -- Warnings ----------------------------------------------------------------
# BACnetAddress exists in both bac_py.network.address and
# bac_py.types.constructed (different domain types with the same name).
# Suppress ambiguous cross-reference warnings from autodoc resolving the
# unqualified name.

suppress_warnings = ["ref.python"]
