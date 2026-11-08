"""The timestamped run log used by the daily pipeline."""

from tools.recommendation.runlog import RunLog, new_run_log


def test_runlog_writes_timestamped_lines(tmp_path) -> None:
    path = tmp_path / "nested" / "run.log"
    echoed: list[str] = []
    log = RunLog(path, echo=echoed.append)
    log.line("hello world")
    log.close()

    text = path.read_text(encoding="utf-8")
    assert "hello world" in text
    assert text.startswith("[") and "Z] " in text  # [<iso>Z] prefix
    assert echoed and "hello world" in echoed[0]


def test_runlog_without_path_only_echoes() -> None:
    echoed: list[str] = []
    log = RunLog(None, echo=echoed.append)
    log.line("only echo")
    log.close()

    assert echoed and "only echo" in echoed[0]


def test_new_run_log_creates_timestamped_file(tmp_path) -> None:
    log = new_run_log(tmp_path, label="cli")
    log.line("a")
    path = log.path
    log.close()

    assert path is not None
    assert path.exists()
    assert path.suffix == ".log"
    assert path.name.endswith("-cli.log")
