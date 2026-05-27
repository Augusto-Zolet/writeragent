# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2024 John Balis
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""Base classes for UNO listeners to reduce boilerplate.

These classes are now deprecated in favor of ``plugin.framework.uno_listeners`` and
are kept here as re-exports for backward compatibility.
"""

import logging
from plugin.framework.uno_listeners import (
    BaseListener,
    BaseActionListener,
    BaseItemListener,
    BaseTextListener,
    BaseKeyListener,
    BaseWindowListener,
    BaseDocumentEventListener,
    BaseCloseListener,
    BaseTerminateListener,
)

log = logging.getLogger(__name__)

__all__ = [
    "BaseListener",
    "BaseActionListener",
    "BaseItemListener",
    "BaseTextListener",
    "BaseKeyListener",
    "BaseWindowListener",
    "BaseDocumentEventListener",
    "BaseCloseListener",
    "BaseTerminateListener",
]


