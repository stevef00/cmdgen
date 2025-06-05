import sys
import pathlib
TEST_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(TEST_DIR / "stubs"))
sys.path.insert(0, str(TEST_DIR.parent))
import cmdgen

class DummyResponse:
    def __init__(self):
        self.called = False
    def model_dump(self):
        return {"output": [{"content": [{"text": "cmd"}]}], "usage": {"tokens": 1}}

class DummyClient:
    def __init__(self):
        self.responses = self
        self.created_with = None
    def create(self, **kwargs):
        self.created_with = kwargs
        return DummyResponse()

def test_make_api_request_uses_openai(monkeypatch):
    dummy_client = DummyClient()
    def openai_factory(**kwargs):
        return dummy_client
    monkeypatch.setattr(cmdgen.openai, "OpenAI", openai_factory)
    resp = cmdgen.make_api_request(cmdgen.Settings(api_url="url", model="model"), "key", "prompt")
    assert isinstance(resp, cmdgen.APIResponse)
    assert dummy_client.created_with["model"] == "model"
    assert dummy_client.created_with["input"][1]["content"] == "prompt"

