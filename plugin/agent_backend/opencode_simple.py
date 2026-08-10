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
"""OpenCode agent backend using the shared ACPBackend base class."""

import logging
import os
import shutil

from plugin.agent_backend.acp_backend import ACPBackend

log = logging.getLogger(__name__)

_OPENCODE_ACP_DEFAULT_ARGS = ["acp"]


class OpenCodeBackend(ACPBackend):
    """ACP-based OpenCode backend (`opencode acp`)."""

    backend_id = "opencode"

    def _load_config(self):
        super()._load_config()
        # Official CLI: `opencode acp` (subcommand appended when settings args are empty).
        if self._binary_path and os.path.basename(self._binary_path).lower() == "opencode" and not self._extra_args:
            self._extra_args = list(_OPENCODE_ACP_DEFAULT_ARGS)

    def _find_binary(self):
        """Locate the `opencode` executable; `_load_config` adds the `acp` subcommand."""
        binary_name = "opencode"
        path = shutil.which(binary_name)
        if path:
            return path
        home = os.path.expanduser("~")
        for candidate in (os.path.join(home, ".local", "bin", binary_name), os.path.join(home, ".cargo", "bin", binary_name)):
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
        return None

    def get_binary_name(self) -> str:
        """Primary executable for PATH lookup (`opencode acp` is the supported install)."""
        return "opencode"

    def is_available(self, ctx):
        """Like ACPBackend but PATH fallback applies default `acp` args."""
        self._load_config()
        if self._binary_path and os.path.isfile(self._binary_path):
            log.info("%s binary found: %s", self.get_display_name(), self._binary_path)
            return True
        path = shutil.which("opencode")
        if path:
            self._binary_path = path
            if not self._extra_args:
                self._extra_args = list(_OPENCODE_ACP_DEFAULT_ARGS)
            log.info("%s found via PATH: %s", self.get_display_name(), path)
            return True
        log.info("%s binary not found", self.get_display_name())
        return False

    def get_display_name(self) -> str:
        """Return display name for UI."""
        return "OpenCode (ACP)"

    def get_agent_name(self) -> str:
        """Return ACP agent name."""
        return "opencode"
