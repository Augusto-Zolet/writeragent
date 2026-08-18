# WriterAgent - Python Compute Service package
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later

try:
    from plugin.version import EXTENSION_VERSION as __version__
except ImportError:
    __version__ = "0.8.59"

__all__ = ["__version__"]
