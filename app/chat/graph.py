"""对话编排（LangGraph）：plan → tool / retrieve → answer。

- 全量消息保存在 SQLite；这里只拿「压缩摘要 + 未折叠消息」；
- 工具动作（任务/评审/知识库/记忆）由 tool 节点执行，直接产出可读结果；
- 流式模式下图在检索后结束（由 service 调用文本流式接口逐块下发）。
"""
from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.chat import tools
from app.providers import chat_json
from app.tools.kb import store


class ChatState(TypedDict, total=False):
    session_id: str
    question: str
    history: list[dict]
    summary: str
    memories: str
    options: dict
    plan: dict
    citations: list[dict]
    index_mode: str
    answer: str
    used_citations: list[str]
    tool_result: dict


def _plan_node(state: ChatState) -> dict:
    payload = chat_json("CHAT_PLAN", {
        "task_id": state["session_id"],
        "provider_id": (state.get("options") or {}).get("provider_id"),
        "question": state["question"],
        "history": state.get("history", []),
        "summary": state.get("summary", ""),
        "memories": state.get("memories", "（暂无）"),
        "retry_hint": "",
    }, options=state.get("options"))
    return {"plan": payload}


def _tool_node(state: ChatState) -> dict:
    plan = state.get("plan") or {}
    params = {"goal": plan.get("goal")}
    params.update(plan.get("args") or {})
    try:
        result = tools.execute(str(plan.get("action")), params, state["session_id"])
        return {"answer": result["content"], "tool_result": result.get("meta") or {}}
    except tools.ToolError as exc:
        return {"answer": f"操作失败：{exc}", "tool_result": {"error": str(exc)}}


def _retrieve_node(state: ChatState) -> dict:
    plan = state.get("plan") or {}
    query = str(plan.get("query") or state["question"]).strip() or state["question"]
    result = store.search(query, filters={"session_id": state["session_id"]},
                          top_k=4, min_score=0.18)
    citations: list[dict] = []
    for index, item in enumerate(result.get("results", []), start=1):
        citation = dict(item.get("citation") or {})
        citation["id"] = f"S{index}"
        citation["snippet"] = (item.get("text") or "")[:300]
        citation["score"] = item.get("score")
        citations.append(citation)
    return {"citations": citations, "index_mode": result.get("index_mode", "scan")}


def _answer_node(state: ChatState) -> dict:
    plan = state.get("plan") or {}
    if plan.get("action") == "answer" and plan.get("answer"):
        return {"answer": str(plan["answer"]), "used_citations": []}
    payload = chat_json("CHAT_ANSWER", {
        "task_id": state["session_id"],
        "provider_id": (state.get("options") or {}).get("provider_id"),
        "question": state["question"],
        "history": state.get("history", []),
        "summary": state.get("summary", ""),
        "memories": state.get("memories", "（暂无）"),
        "evidence": state.get("citations", []),
        "retry_hint": "",
    }, options=state.get("options"))
    return {
        "answer": str(payload.get("answer") or ""),
        "used_citations": [str(item) for item in payload.get("used_citations") or []],
    }


def _route(state: ChatState) -> str:
    action = str((state.get("plan") or {}).get("action") or "answer")
    if action in tools.TOOL_ACTIONS:
        return "tool"
    if action == "search":
        return "retrieve"
    return "answer"


_graphs: dict[bool, object] = {}


def _build(streaming: bool):
    graph = StateGraph(ChatState)
    graph.add_node("plan", _plan_node)
    graph.add_node("tool", _tool_node)
    graph.add_node("retrieve", _retrieve_node)
    graph.add_node("answer", _answer_node)
    graph.add_edge(START, "plan")
    graph.add_conditional_edges("plan", _route,
                                {"tool": "tool", "retrieve": "retrieve", "answer": "answer"})
    graph.add_edge("tool", END)
    graph.add_edge("retrieve", "answer" if not streaming else END)
    graph.add_edge("answer", END)
    return graph.compile()


def run_agent(session_id: str, question: str, history: list[dict], summary: str,
              memories: str, options: dict, *, streaming: bool = False) -> dict:
    if streaming not in _graphs:
        _graphs[streaming] = _build(streaming)
    return _graphs[streaming].invoke({
        "session_id": session_id,
        "question": question,
        "history": history,
        "summary": summary,
        "memories": memories,
        "options": options or {},
    })
