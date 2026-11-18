import sys, pathlib, types
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from engine.shared import llm, costlog


class StubClient:
    class messages:
        calls = 0
        @staticmethod
        def create(**kw):
            StubClient.messages.calls += 1
            blk = types.SimpleNamespace(type="text", text="hello")
            return types.SimpleNamespace(content=[blk], usage=types.SimpleNamespace(input_tokens=1000, output_tokens=200))


def test_second_call_is_free():
    llm._client = StubClient
    costlog.new_run()
    prompt = "unique prompt for cache test " + costlog.run_id
    llm.ask("sys", prompt, "extract", "cache-test")
    first = costlog.spent("cache-test")
    llm.ask("sys", prompt, "extract", "cache-test")
    assert first > 0
    assert costlog.spent("cache-test") == first          # nothing added
    assert StubClient.messages.calls == 1
