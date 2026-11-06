"""The integration files split into CI shards of similar duration."""

from __future__ import annotations

import io
import json
import sys

from tests import shard


def test_every_file_is_in_exactly_one_shard(tmp_path):
    files = [f"tests/integration/test_{i}.py" for i in range(9)]
    durations = {files[0]: 100.0, files[1]: 50.0, files[2]: 10.0}
    shards = [shard.files_of(n, 3, files, durations) for n in (1, 2, 3)]
    assert sorted(f for s in shards for f in s) == sorted(files)


def test_the_slowest_files_go_to_different_shards():
    files = ["a.py", "b.py", "c.py", "d.py"]
    durations = {"a.py": 600.0, "b.py": 500.0, "c.py": 100.0, "d.py": 100.0}
    one, two = shard.files_of(1, 2, files, durations), shard.files_of(2, 2, files, durations)
    assert {"a.py", "b.py"} - set(one) and {"a.py", "b.py"} - set(two)
    weight = [sum(durations[f] for f in s) for s in (one, two)]
    assert max(weight) - min(weight) <= 100


def test_a_file_without_a_duration_weighs_the_median():
    durations = {"a.py": 10.0, "b.py": 30.0, "c.py": 1000.0}
    assert shard.weight("new.py", durations) == 30.0


def test_the_command_reads_the_durations_file(tmp_path, capsys):
    (tmp_path / "durations.json").write_text(json.dumps({"test_x.py": 5.0}))
    (tmp_path / "test_x.py").write_text("")
    (tmp_path / "test_y.py").write_text("")
    printed = []
    for n in (1, 2):
        shard.main([str(n), "2", str(tmp_path)])
        printed += capsys.readouterr().out.split()
    assert sorted(printed) == sorted((tmp_path / f).as_posix() for f in ("test_x.py", "test_y.py"))


def test_the_command_prints_no_carriage_returns(tmp_path, monkeypatch):
    # On Windows a text stdout writes "\r\n", and bash's $(...) keeps the "\r"
    # in every file name: pytest then finds none of them.
    (tmp_path / "test_x.py").write_text("")
    (tmp_path / "test_y.py").write_text("")
    raw = io.BytesIO()
    out = io.TextIOWrapper(raw, encoding="utf-8", newline="\r\n")
    monkeypatch.setattr(sys, "stdout", out)
    shard.main(["1", "1", str(tmp_path)])
    out.flush()
    assert b"\r" not in raw.getvalue()
    assert raw.getvalue().split() == [
        (tmp_path / f).as_posix().encode() for f in ("test_x.py", "test_y.py")
    ]
