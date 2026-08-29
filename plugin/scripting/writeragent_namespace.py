# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Slim-bundle stand-in for top-level ``writeragent`` when ``writeragent_api`` is not shipped.

LibrePy omits the generated tool-proxy module; ``AliasImporter`` loads this module
instead so ``from writeragent.scripting.* import ...`` can resolve child packages
via the existing writeragent→plugin alias. ``wa.scripts`` / ``wa.doc`` are attached
at execute time (``named_scripts.attach_named_script_libraries``).
"""
