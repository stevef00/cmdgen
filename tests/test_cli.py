import sys
import pathlib
TEST_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(TEST_DIR / "stubs"))
sys.path.insert(0, str(TEST_DIR.parent))
from typer.testing import CliRunner
import cmdgen

runner = CliRunner()

def dummy_load_api_key(settings):
    return "testkey"

def dummy_make_api_request(settings, api_key, prompt):
    return cmdgen.APIResponse(output=[{"content": [{"text": "echo test"}]}], usage={"tokens": 1})

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

def test_quiet_auto_when_not_terminal(monkeypatch):
    setup(monkeypatch)
    monkeypatch.setattr(cmdgen, "is_terminal", lambda: False)
    result = runner.invoke(cmdgen.app, ["--prompt", "test"])
    assert result.exit_code == 0
    assert "echo test" in result.stdout
    assert "Generated Command" not in result.stdout

class CallCounter:
    def __init__(self):
        self.count = 0

    def __call__(self, *args, **kwargs):
        self.count += 1


def test_stats_flag(monkeypatch):
    setup(monkeypatch)
    counter = CallCounter()
    monkeypatch.setattr(cmdgen, "display_stats", counter)
    monkeypatch.setattr(cmdgen, "is_terminal", lambda: True)
    runner.invoke(cmdgen.app, ["--prompt", "test", "--stats"])
    assert counter.count == 1


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
