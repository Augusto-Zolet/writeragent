# WriterAgent - tests for vendored nbformat (plugin/contrib/nbformat)

import json
import tempfile
from pathlib import Path

import pytest

from plugin.contrib.nbformat import NBFormatError, read_ipynb, reads


_MINIMAL_V4 = {
    "nbformat": 4,
    "nbformat_minor": 5,
    "metadata": {},
    "cells": [
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": ["# Title\n", "body\n"],
        },
        {
            "cell_type": "code",
            "execution_count": 1,
            "metadata": {},
            "source": ["a = 1\n", "print(a)\n"],
            "outputs": [
                {
                    "output_type": "stream",
                    "name": "stdout",
                    "text": ["1\n"],
                },
                {
                    "output_type": "execute_result",
                    "execution_count": 1,
                    "metadata": {},
                    "data": {"text/plain": ["1"]},
                },
            ],
        },
    ],
}


def test_reads_rejoins_source_and_stream_text():
    nb = reads(json.dumps(_MINIMAL_V4))
    assert nb.cells[0].source == "# Title\nbody\n"
    assert nb.cells[1].source == "a = 1\nprint(a)\n"
    assert nb.cells[1].outputs[0].text == "1\n"
    assert nb.cells[1].outputs[1].data["text/plain"] == "1"


def test_read_ipynb_round_trip_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".ipynb", delete=False, encoding="utf-8") as f:
        json.dump(_MINIMAL_V4, f)
        path = f.name
    try:
        nb = read_ipynb(path)
        assert len(nb.cells) == 2
        assert nb.cells[1].cell_type == "code"
    finally:
        Path(path).unlink(missing_ok=True)


def test_rejects_nbformat_v3():
    v3 = dict(_MINIMAL_V4)
    v3["nbformat"] = 3
    v3["nbformat_minor"] = 0
    with pytest.raises(NBFormatError, match="v4"):
        reads(json.dumps(v3))
