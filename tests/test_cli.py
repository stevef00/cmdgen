import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from typer.testing import CliRunner
import cmdgen

runner = CliRunner()

def dummy_load_api_key(settings):
    return "testkey"

def dummy_make_api_request(settings, api_key, prompt):
    return cmdgen.APIResponse(output=[{"content": [{"text": "echo test"}]}])

class DummyHistory:
    def append_string(self, text):
        pass

class DummySession:
    def __init__(self):
        self.history = DummyHistory()
    def prompt(self, *args, **kwargs):
        return "test"

def dummy_setup_prompt_session(settings):
    return DummySession()

def setup(monkeypatch):
    monkeypatch.setattr(cmdgen, "load_api_key", dummy_load_api_key)
    monkeypatch.setattr(cmdgen, "make_api_request", dummy_make_api_request)
    monkeypatch.setattr(cmdgen, "setup_prompt_session", dummy_setup_prompt_session)


def test_quiet_flag(monkeypatch):
    setup(monkeypatch)
    result = runner.invoke(cmdgen.app, ["--quiet", "--prompt", "test"])
    assert result.exit_code == 0


def test_quiet_output(monkeypatch):
    setup(monkeypatch)
    result = runner.invoke(cmdgen.app, ["--quiet", "--prompt", "test"])
    assert "echo test" in result.stdout


class CallCounter:
    def __init__(self):
        self.count = 0

    def __call__(self, *args, **kwargs):
        self.count += 1


def test_trim_history_called_with_prompt(monkeypatch):
    setup(monkeypatch)
    counter = CallCounter()
    monkeypatch.setattr(cmdgen, "trim_history", counter)
    runner.invoke(cmdgen.app, ["--prompt", "test"])
    assert counter.count == 1


def test_trim_history_called_interactive(monkeypatch):
    setup(monkeypatch)
    counter = CallCounter()
    monkeypatch.setattr(cmdgen, "trim_history", counter)
    runner.invoke(cmdgen.app, [])
    assert counter.count == 1
