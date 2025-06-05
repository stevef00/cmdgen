import sys
import pathlib
TEST_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(TEST_DIR / "stubs"))
sys.path.insert(0, str(TEST_DIR.parent))
from typer.testing import CliRunner
import cmdgen
import signal

runner = CliRunner()


def dummy_load_api_key(settings):
    return "testkey"


class DummyHistory:
    def append_string(self, text):
        pass


class DummySession:
    def __init__(self, inputs):
        self.history = DummyHistory()
        self.inputs = inputs
        self.index = 0

    def prompt(self, *args, **kwargs):
        if self.index >= len(self.inputs):
            raise EOFError
        value = self.inputs[self.index]
        self.index += 1
        return value


def setup_common(monkeypatch, inputs=None):
    monkeypatch.setattr(cmdgen, "load_api_key", dummy_load_api_key)
    if inputs is None:
        inputs = []
    monkeypatch.setattr(cmdgen, "setup_prompt_session",
                       lambda settings, persistent=False: DummySession(inputs))
    monkeypatch.setattr(cmdgen.signal, "signal", lambda *a, **k: None)


def test_prompt_interactive_mutual_exclusion(monkeypatch):
    setup_common(monkeypatch)
    result = runner.invoke(cmdgen.app, ["-p", "hi", "-i"])
    assert result.exit_code == 1
    assert "mutually exclusive" in result.stdout


def test_cli_invokes_repl_when_interactive(monkeypatch):
    setup_common(monkeypatch)
    called = {}
    monkeypatch.setattr(cmdgen, "run_repl", lambda s, a, lvl, q, t, x: called.setdefault("lvl", lvl))
    result = runner.invoke(cmdgen.app, ["-i"])
    assert result.exit_code == 0
    assert called["lvl"] is None


def test_cli_invokes_repl_by_default(monkeypatch):
    setup_common(monkeypatch)
    called = {}
    monkeypatch.setattr(cmdgen, "run_repl", lambda s, a, lvl, q, t, x: called.setdefault("lvl", lvl))
    result = runner.invoke(cmdgen.app, [])
    assert result.exit_code == 0
    assert "lvl" in called


def test_repl_stats_output(monkeypatch, tmp_path):
    usage = {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3, "cached_tokens": 0}
    inputs = ["foo", "exit"]
    setup_common(monkeypatch, inputs)
    stats_calls = []
    monkeypatch.setattr(cmdgen, "display_stats", lambda u, lvl: stats_calls.append((u, lvl)))

    def fake_api_request(settings, api_key, prompt):
        if isinstance(prompt, str):
            return cmdgen.APIResponse(output=[{"content": [{"text": "summary"}]}])
        return cmdgen.APIResponse(output=[{"content": [{"text": "cmd"}]}], usage=usage)

    monkeypatch.setattr(cmdgen, "make_api_request", fake_api_request)
    settings = cmdgen.Settings(history_file=tmp_path / "hist")
    cmdgen.run_repl(settings, "key", "basic", True, False, False)
    assert stats_calls == [(usage, "basic"), (usage, "basic")]


def test_repl_meta_stats(monkeypatch, tmp_path):
    inputs = [":stats", "exit"]
    setup_common(monkeypatch, inputs)
    calls = []
    monkeypatch.setattr(cmdgen, "display_stats", lambda u, lvl: calls.append((u, lvl)))
    monkeypatch.setattr(cmdgen, "make_api_request", lambda *a, **k: (_ for _ in ()).throw(Exception("should not call")))
    settings = cmdgen.Settings(history_file=tmp_path / "hist")
    cmdgen.run_repl(settings, "key", "basic", True, False, False)
    assert calls == [({}, "basic")]


def test_repl_meta_undo(monkeypatch, tmp_path):
    inputs = ["foo", ":undo", "exit"]
    setup_common(monkeypatch, inputs)
    count = {"calls": 0}

    def fake_api_request(settings, api_key, prompt):
        if isinstance(prompt, list):
            count["calls"] += 1
            return cmdgen.APIResponse(output=[{"content": [{"text": "cmd"}]}])
        return cmdgen.APIResponse(output=[{"content": [{"text": "summary"}]}])

    monkeypatch.setattr(cmdgen, "make_api_request", fake_api_request)
    settings = cmdgen.Settings(history_file=tmp_path / "hist")
    cmdgen.run_repl(settings, "key", None, True, False, False)
    assert count["calls"] == 1


def test_repl_meta_help(monkeypatch, tmp_path):
    inputs = [":help", "exit"]
    setup_common(monkeypatch, inputs)
    printed = []
    monkeypatch.setattr(cmdgen.console, "print", lambda msg, *a, **k: printed.append(str(msg)))
    monkeypatch.setattr(cmdgen, "make_api_request", lambda *a, **k: cmdgen.APIResponse(output=[{"content": [{"text": ""}]}]))
    settings = cmdgen.Settings(history_file=tmp_path / "hist")
    cmdgen.run_repl(settings, "key", None, True, False, False)
    assert any(":stats" in p for p in printed)


def test_repl_history_summary_written(monkeypatch, tmp_path):
    inputs = ["foo", "exit"]
    setup_common(monkeypatch, inputs)

    def fake_api_request(settings, api_key, prompt):
        if isinstance(prompt, list) and any(
            "Summarize" in p.get("content", "") for p in prompt if isinstance(p, dict)
        ):
            return cmdgen.APIResponse(output=[{"content": [{"text": "summary line"}]}])
        return cmdgen.APIResponse(output=[{"content": [{"text": "cmd"}]}])

    monkeypatch.setattr(cmdgen, "make_api_request", fake_api_request)
    settings = cmdgen.Settings(history_file=tmp_path / "hist")
    cmdgen.run_repl(settings, "key", None, True, False, False)
    lines = settings.history_file.read_text().splitlines()
    assert lines[0] == ""
    assert lines[1].startswith("# ")
    assert lines[2] == "+summary line"


def test_repl_summary_uses_context(monkeypatch, tmp_path):
    inputs = ["foo", "exit"]
    setup_common(monkeypatch, inputs)

    calls = []

    def fake_api_request(settings, api_key, prompt):
        calls.append(prompt)
        if len(calls) == 1:
            assert isinstance(prompt, list)
            return cmdgen.APIResponse(output=[{"content": [{"text": "cmd"}]}])
        elif len(calls) == 2:
            assert isinstance(prompt, list)
            # ensure summary prompt includes instruction
            assert "Summarize" in prompt[-1]["content"]
            return cmdgen.APIResponse(output=[{"content": [{"text": "summary"}]}])
        else:
            raise AssertionError("Unexpected API call")

    monkeypatch.setattr(cmdgen, "make_api_request", fake_api_request)
    settings = cmdgen.Settings(history_file=tmp_path / "hist")
    cmdgen.run_repl(settings, "key", None, True, False, False)
    assert len(calls) == 2

