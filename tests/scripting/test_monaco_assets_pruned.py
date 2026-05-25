# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os

from plugin.scripting.editor_launcher import _ASSETS_DIR


def test_monaco_vs_pruned_for_python_only_editor():
    vs = os.path.join(_ASSETS_DIR, "vs")
    assert os.path.isdir(os.path.join(vs, "basic-languages", "python"))
    assert not os.path.isdir(os.path.join(vs, "language"))
    assert not os.path.isfile(os.path.join(vs, "nls.messages.de.js"))
    # Spot-check a language we do not ship after prune.
    assert not os.path.isdir(os.path.join(vs, "basic-languages", "typescript"))
