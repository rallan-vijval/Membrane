"""The agent wrapper, with the HTTP call faked. No network, no key."""
from membrane import agent

TASK = {"customer": {"id": "C-1", "tier": "VIP"},
        "order": {"id": "5530", "amount": 180, "days_since_delivery": 9}, "message": "refund please"}
MEMS = [{"text": "rule one"}, {"text": "rule two"}]


def test_prompt_lists_memories_in_order_and_task_facts():
    system, user = agent.build_prompt(TASK, MEMS)
    assert system.index("1. rule one") < system.index("2. rule two")
    assert "Order 5530" in user and "VIP" in user


def test_views_differ_only_by_the_candidate_line():
    a, _ = agent.build_prompt(TASK, MEMS)
    b, _ = agent.build_prompt(TASK, MEMS + [{"text": "candidate"}])
    assert b == a + "\n3. candidate"


def test_anthropic_tool_call_is_recorded_not_executed(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_API_KEY", "test")
    sent = {}

    def fake_post(url, headers, body):
        sent.update(body)
        return {"content": [{"type": "text", "text": "ok"},
                            {"type": "tool_use", "name": "issue_refund",
                             "input": {"order_id": "5530", "amount": 180, "return_required": True, "reason": "r"}}]}
    monkeypatch.setattr(agent, "_post", fake_post)
    out = agent.run_task(TASK, MEMS)
    assert out["tool_calls"] == [{"name": "issue_refund", "args": {
        "order_id": "5530", "amount": 180, "return_required": True, "reason": "r"}}]
    assert sent["temperature"] == 0 and len(sent["messages"]) == 1  # fresh session, deterministic


def test_openai_tool_call_is_parsed(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_API_KEY", "test")
    monkeypatch.setattr(agent, "_post", lambda *a: {"choices": [{"message": {"content": None, "tool_calls": [
        {"function": {"name": "deny_refund", "arguments": "{\"order_id\": \"8090\", \"reason\": \"late\"}"}}]}}]})
    out = agent.run_task(TASK, MEMS)
    assert out["tool_calls"] == [{"name": "deny_refund", "args": {"order_id": "8090", "reason": "late"}}]
