"""对话编排（LangGraph）：plan → (retrieve) → answer。

记忆由自建 SQLite 表承载（chat_messages 短期、chat_sessions.summary 长期），
前端直接读取渲染；图本身不持有跨请求状态，每次以数据库快照调用。
"""
from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.providers import chat_json
from app.tools.kb import store


class ChatState(TypedDict, total=False):
    session_id: str
    question: str
    history: list[dict]
    summary: str
    plan: dict
    citations: list[dict]
    answer: str
    used_citations: list[str]
    index_mode: str


def _plan_node(state: ChatState) -> dict:
    payload = chat_json("CHAT_PLAN", {
        "task_id": state["session_id"],
        "question": state["question"],
        "history": state.get("history", []),
        "summary": state.get("summary", ""),
        "retry_hint": "",
    })
    return {"plan": payload}


def _retrieve_node(state: ChatState) -> dict:
    plan = state.get("plan") or {}
    query = str(plan.get("query") or state["question"]).strip() or state["question"]
    # 会话检索偏召回：阈值放宽，证据不足由回答节点明确说明（引用仍带分数）
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
        "question": state["question"],
        "history": state.get("history", []),
        "summary": state.get("summary", ""),
        "evidence": state.get("citations", []),
        "retry_hint": "",
    })
    return {
        "answer": str(payload.get("answer") or ""),
        "used_citations": [str(item) for item in payload.get("used_citations") or []],
    }


def _route(state: ChatState) -> str:
    return "retrieve" if (state.get("plan") or {}).get("action") == "search" else "answer"


def build_graph():
    graph = StateGraph(ChatState)
    graph.add_node("plan", _plan_node)
    graph.add_node("retrieve", _retrieve_node)
    graph.add_node("answer", _answer_node)
    graph.add_edge(START, "plan")
    graph.add_conditional_edges("plan", _route, {"retrieve": "retrieve", "answer": "answer"})
    graph.add_edge("retrieve", "answer")
    graph.add_edge("answer", END)
    return graph.compile()


_graph = None


def run_agent(session_id: str, question: str, history: list[dict], summary: str) -> dict:
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph.invoke({
        "session_id": session_id,
        "question": question,
        "history": history,
        "summary": summary,
    })
