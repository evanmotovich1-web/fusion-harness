from _isolated import run_file, value


def test_count_basic():
    assert value("wordstats", "count", "hello world\nsecond line\n") == {"lines": 2, "words": 4, "chars": 24}


def test_count_empty_and_unterminated():
    assert value("wordstats", "count", "") == {"lines": 0, "words": 0, "chars": 0}
    assert value("wordstats", "count", "a b\nc") == {"lines": 2, "words": 3, "chars": 5}


def test_count_unicode_is_characters():
    assert value("wordstats", "count", "héllo wörld 👋\n") == {"lines": 1, "words": 3, "chars": 14}


def test_cli_stdin_exact_output():
    result = run_file("wordstats.py", stdin="hello world\n")
    assert result.returncode == 0
    assert result.stdout == "Lines: 1\nWords: 2\nCharacters: 12\n"


def test_cli_file(tmp_path):
    path = tmp_path / "f.txt"
    path.write_text("x y z\n", encoding="utf-8")
    result = run_file("wordstats.py", [str(path)])
    assert result.returncode == 0
    assert result.stdout.splitlines() == ["Lines: 1", "Words: 3", "Characters: 6"]


def test_cli_missing_file_exit_2():
    result = run_file("wordstats.py", ["/definitely/not/here.txt"])
    assert result.returncode == 2
    assert result.stderr.strip()
