"""Ask AI endpoint: tool loop against a fake Claude client (no network)."""

from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from tests.test_api import A, B
from tests.test_fleet import grid_graph


class FakeMessages:
    """Scripted responses: first asks for compare_route, then answers in text."""

    def __init__(self, script):
        self.script, self.calls = list(script), []

    def create(self, **kw):
        self.calls.append(kw)
        return self.script.pop(0)


def fake_client(script):
    msgs = FakeMessages(script)
    return NS(beta=NS(messages=msgs)), msgs


TOOL_TURN = NS(stop_reason="tool_use", content=[NS(type="tool_use", id="t1", name="compare_route", input={
    "origin_lat": A["lat"], "origin_lon": A["lon"], "dest_lat": B["lat"], "dest_lon": B["lon"],
    "vehicle": "van_diesel", "alpha": None})])
TEXT_TURN = NS(stop_reason="end_turn", content=[NS(type="text", text="R2I saves CO2 here.")])


@pytest.fixture()
def ask():
    def make(script):
        llm, msgs = fake_client(script)
        client = TestClient(create_app(graph=grid_graph(), llm=lambda: llm))
        return client, msgs
    return make


def test_ask_runs_tool_and_returns_route_artifact(ask):
    client, msgs = ask([TOOL_TURN, TEXT_TURN])
    with client:
        r = client.post("/ask", json={"messages": [{"role": "user", "content": "compare"}]})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "R2I saves CO2 here."
    assert body["artifacts"][0]["type"] == "route"
    assert len(body["artifacts"][0]["r2i"]["path"]) >= 2
    # tool result was fed back to the model
    last = msgs.calls[1]["messages"][-1]["content"][0]
    assert last["type"] == "tool_result" and last["tool_use_id"] == "t1"


def test_ask_uses_claude_opus_with_tools(ask):
    client, msgs = ask([TEXT_TURN])
    with client:
        client.post("/ask", json={"messages": [{"role": "user", "content": "hi"}]})
    kw = msgs.calls[0]
    assert kw["model"] == "claude-opus-5-5"
    assert {t["name"] for t in kw["tools"]} >= {"compare_route", "find_place", "fleet_summary"}


def test_ask_bad_tool_input_is_error_result_not_500(ask):
    bad = NS(stop_reason="tool_use", content=[NS(type="tool_use", id="t2", name="compare_route",
                                                 input={"vehicle": "zeppelin"})])
    client, msgs = ask([bad, TEXT_TURN])
    with client:
        r = client.post("/ask", json={"messages": [{"role": "user", "content": "x"}]})
    assert r.status_code == 200
    assert msgs.calls[1]["messages"][-1]["content"][0]["is_error"] is True


def test_ask_refusal_returns_message(ask):
    client, _ = ask([NS(stop_reason="refusal", content=[])])
    with client:
        r = client.post("/ask", json={"messages": [{"role": "user", "content": "x"}]})
    assert r.status_code == 200 and r.json()["answer"]


def test_ask_without_credentials_is_503():
    def boom():
        raise RuntimeError("no credentials")
    with TestClient(create_app(graph=grid_graph(), llm=boom)) as c:
        r = c.post("/ask", json={"messages": [{"role": "user", "content": "x"}]})
    assert r.status_code == 503


def test_ask_rejects_empty_history():
    llm, _ = fake_client([])
    with TestClient(create_app(graph=grid_graph(), llm=lambda: llm)) as c:
        assert c.post("/ask", json={"messages": []}).status_code == 422


def test_ask_unresolved_auth_at_request_time_is_503():
    class NoAuth:
        def create(self, **kw):
            raise TypeError('"Could not resolve authentication method. Expected one of api_key"')
    llm = NS(beta=NS(messages=NoAuth()))
    with TestClient(create_app(graph=grid_graph(), llm=lambda: llm)) as c:
        r = c.post("/ask", json={"messages": [{"role": "user", "content": "x"}]})
    assert r.status_code == 503


def test_ask_uses_inference_cloud_when_configured(monkeypatch):
    """OpenAI-compatible provider: tool call -> engine -> final answer."""
    import json as _json
    calls = []

    class Resp:
        def __init__(self, body): self.body = body
        def raise_for_status(self): pass
        def json(self): return self.body

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(json)
        if len(calls) == 1:
            return Resp({"choices": [{"finish_reason": "tool_calls", "message": {"role": "assistant", "content": "",
                "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "compare_route", "arguments": _json.dumps({
                    "origin_lat": A["lat"], "origin_lon": A["lon"], "dest_lat": B["lat"], "dest_lon": B["lon"],
                    "vehicle": "van_diesel", "alpha": None})}}]}}]})
        return Resp({"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "Done."}}]})

    monkeypatch.setenv("INFERENCE_CLOUD_API_KEY", "test-key")
    monkeypatch.setenv("INFERENCE_CLOUD_ENDPOINT", "https://example.invalid/v2")
    import requests
    monkeypatch.setattr(requests, "post", fake_post)
    with TestClient(create_app(graph=grid_graph())) as c:
        r = c.post("/ask", json={"messages": [{"role": "user", "content": "compare"}]})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "Done." and body["artifacts"][0]["type"] == "route"
    assert calls[0]["model"] == "Llama-3.3-70B"
    assert calls[1]["messages"][-1]["role"] == "tool"


def test_inference_cloud_parses_text_form_tool_calls():
    """Llama sometimes writes <|python_tag|>{"name":..,"parameters":..} as text instead of tool_calls."""
    from api.assistant import parse_text_tool_calls, clean_answer
    text = ('<|python_tag|>{"name": "find_place", "parameters": "{\\"query\\": \\"HSR Layout\\"}"}<|eom_id|>'
            '<|start_header_id|>assistant<|end_header_id|>\n\n<|python_tag|>import requests\n')
    calls = parse_text_tool_calls(text)
    assert [c["function"]["name"] for c in calls] == ["find_place"]
    assert '"HSR Layout"' in calls[0]["function"]["arguments"]
    assert clean_answer("Hello<|eot_id|> world<|python_tag|>x") == "Hello world"


def test_inference_cloud_sends_one_tool_call_per_message(monkeypatch):
    import json as _json
    import requests
    sent = []

    class Resp:
        def __init__(self, body): self.body = body
        def raise_for_status(self): pass
        def json(self): return self.body

    def fake_post(url, headers=None, json=None, timeout=None):
        sent.append(_json.loads(_json.dumps(json)))
        if len(sent) == 1:
            calls = [{"id": f"c{i}", "type": "function", "function": {"name": "vehicle_classes", "arguments": "{}"}} for i in range(2)]
            return Resp({"choices": [{"message": {"role": "assistant", "content": "", "tool_calls": calls}}]})
        return Resp({"choices": [{"message": {"role": "assistant", "content": "ok"}}]})

    monkeypatch.setenv("INFERENCE_CLOUD_API_KEY", "k")
    monkeypatch.setattr(requests, "post", fake_post)
    with TestClient(create_app(graph=grid_graph())) as c:
        c.post("/ask", json={"messages": [{"role": "user", "content": "x"}]})
    assistants = [m for m in sent[1]["messages"] if m["role"] == "assistant"]
    assert len(assistants) == 2 and all(len(m["tool_calls"]) == 1 for m in assistants)
