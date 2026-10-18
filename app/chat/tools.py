"""聊天工具：把模型规划的动作落到系统能力（任务 / 评审 / 知识库 / 记忆）。"""
from __future__ import annotations

from app.chat import memory as memory_store
from app.db import new_session
from app.models import ChatDocument
from app.services import missions as mission_service
from app.services import reviews as review_service
from app.tools.kb import store as kb_store

TOOL_ACTIONS = {
    "create_mission", "clarify", "update_mission_draft",
    "list_missions", "mission_status", "mission_review", "accept_all",
    "kb_store", "kb_list", "kb_delete",
    "memory_add", "memory_list", "memory_delete",
}

REQUIRED_CONSTRAINTS = (("orbit_type", "轨道类型（SSO / LEO / GEO）"),
                        ("altitude_km", "轨道高度（km）"),
                        ("lifetime_years", "设计寿命（年）"))


def pending_draft(session_id: str) -> dict:
    from app.models import ChatSession

    with new_session() as session:
        chat = session.get(ChatSession, session_id)
        return dict(chat.pending_mission or {}) if chat else {}


def _save_pending(session_id: str, draft: dict) -> None:
    from app.models import ChatSession

    with new_session() as session:
        chat = session.get(ChatSession, session_id)
        if chat is not None:
            chat.pending_mission = draft
            session.commit()


def _clear_pending(session_id: str) -> None:
    _save_pending(session_id, None)


def _draft_summary(draft: dict) -> str:
    constraints = draft.get("constraints") or {}
    labels = {"orbit_type": "轨道", "altitude_km": "高度 km", "lifetime_years": "寿命 年",
              "mass_limit_kg": "质量上限 kg", "payload": "载荷", "data_requirements": "任务需求",
              "ttc_conditions": "测控条件", "notes": "备注"}
    known = "、".join(f"{labels.get(key, key)}={value}" for key, value in constraints.items()
                     if value not in (None, ""))
    missing = [label for key, label in REQUIRED_CONSTRAINTS if not constraints.get(key)]
    lines = [f"任务草案：{draft.get('goal') or '（未命名）'}" + (f"；已知：{known}" if known else "")]
    if missing:
        lines.append("还需补充：" + "、".join(missing) + "。")
    lines.append("可以直接回复参数（如「轨道 SSO，高度 500km，寿命 5 年，质量上限 100kg」），"
                 "或者说「按默认参数创建」；明确回复「确认创建」后我再启动设计任务。")
    return "\n".join(lines)


class ToolError(ValueError):
    """工具执行失败（作为助手消息返回，不抛出到接口）。"""


def _param(params: dict, key: str, default=None):
    if not isinstance(params, dict):
        return default
    if key in params and params[key] not in (None, ""):
        return params[key]
    args = params.get("args")
    if isinstance(args, dict) and args.get(key) not in (None, ""):
        return args[key]
    return default


def execute(action: str, params: dict, session_id: str) -> dict:
    try:
        return _execute(action, params or {}, session_id)
    except ToolError:
        raise
    except Exception as exc:  # noqa: BLE001 —— 工具失败转成可读消息
        raise ToolError(str(exc)) from exc


def _execute(action: str, params: dict, session_id: str) -> dict:
    if action == "clarify":
        message = str(_param(params, "message") or "").strip()
        draft = pending_draft(session_id)
        if not draft:
            draft = {"goal": str(_param(params, "goal") or "").strip(), "constraints": {}}
            _save_pending(session_id, draft)
        content = message or _draft_summary(draft)
        return {"content": content, "meta": {"tool": action, "pending_mission": draft}}

    if action == "update_mission_draft":
        current = pending_draft(session_id)
        goal = str(_param(params, "goal") or current.get("goal") or "").strip()
        incoming = _param(params, "constraints") or {}
        constraints = dict(current.get("constraints") or {})
        if isinstance(incoming, dict):
            for key, value in incoming.items():
                if value not in (None, ""):
                    constraints[key] = value
        title = _param(params, "title") or current.get("title")
        draft = {"goal": goal, "constraints": constraints, "title": title}
        _save_pending(session_id, draft)
        return {"content": _draft_summary(draft),
                "meta": {"tool": action, "pending_mission": draft}}

    if action == "create_mission":
        draft = pending_draft(session_id)
        confirmed = bool(_param(params, "confirmed"))
        if draft and not confirmed:
            return {"content": _draft_summary(draft) + "\n（尚未创建：请明确回复「确认创建」）",
                    "meta": {"tool": "clarify", "pending_mission": draft}}
        goal = str(_param(params, "goal") or draft.get("goal") or "").strip()
        if not goal:
            raise ToolError("缺少任务目标")
        incoming = _param(params, "constraints") or {}
        constraints = dict(draft.get("constraints") or {})
        if isinstance(incoming, dict):
            for key, value in incoming.items():
                if value not in (None, ""):
                    constraints[key] = value
        title = _param(params, "title") or draft.get("title")
        result = mission_service.create_mission(
            goal=goal, constraints=constraints,
            title=str(title) if title else None,
        )
        _clear_pending(session_id)
        return {
            "content": (f"已创建任务 {result['task_id']}「{result['title']}」，"
                        f"正在后台执行。可在「设计任务」页查看：/missions/{result['task_id']}"),
            "meta": {"tool": "create_mission", "task_id": result["task_id"]},
        }

    if action == "list_missions":
        status = _param(params, "status")
        items = mission_service.list_missions(status=str(status) if status else None)
        if not items:
            return {"content": "当前没有任务。", "meta": {"tool": action, "tasks": []}}
        lines = [f"- {item['task_id']}｜{item['title']}｜{item['status']}" for item in items]
        return {"content": "当前任务：\n" + "\n".join(lines),
                "meta": {"tool": action, "tasks": items}}

    if action == "mission_status":
        task_id = str(_param(params, "task_id") or "").strip()
        if not task_id:
            raise ToolError("请提供任务编号（t-YYYYMMDD-NNN）")
        snapshot = mission_service.mission_snapshot(task_id)
        text = (f"任务 {snapshot['task_id']}「{snapshot['title']}」：{snapshot['status']}，"
                f"当前步骤 {snapshot['current_step'] or '-'}")
        gates = snapshot.get("pending_gates") or []
        if gates:
            text += "；待处理门禁：" + "、".join(
                gate.get("param_id") or gate.get("type") for gate in gates)
        return {"content": text, "meta": {"tool": action, "mission": snapshot}}

    if action == "accept_all":
        task_id = str(_param(params, "task_id") or "").strip()
        if not task_id:
            latest = mission_service.list_missions(limit=1)
            if not latest:
                return {"content": "当前没有任务可审核。", "meta": {"tool": action}}
            task_id = latest[0]["task_id"]
        result = review_service.accept_all(
            task_id, reviewer="chat-agent",
            comment=str(_param(params, "comment") or "聊天指令：一键确认全部待处理项"),
        )
        text = (f"已一键确认任务 {task_id}：参数 {result['accepted_parameters']} 个、"
                f"假设 {result['accepted_assumptions']} 条；"
                f"剩余待确认 {result['remaining_confirmations']} 项。")
        if result["revalidation"]["queued"]:
            text += "任务已恢复执行。"
        return {"content": text, "meta": {"tool": action, "task_id": task_id,
                                          "accept_all": result}}

    if action == "mission_review":
        task_id = str(_param(params, "task_id") or "").strip()
        param_id = str(_param(params, "param_id") or "").strip()
        review_action = str(_param(params, "review_action") or "accept")
        if not task_id or not param_id:
            raise ToolError("请提供任务编号与参数 id（可在参数评审页复制）")
        edited_value = _param(params, "edited_value")
        result = review_service.review_parameter(
            task_id, param_id, review_action, reviewer="chat-agent",
            comment=_param(params, "comment"),
            edited_value=float(edited_value) if edited_value is not None else None,
        )
        verb = "通过" if review_action == "accept" else "驳回"
        text = f"已{verb}参数 {param_id}；剩余待确认 {result['remaining_confirmations']} 项。"
        if result["revalidation"]["queued"]:
            text += "任务已恢复执行。"
        return {"content": text, "meta": {"tool": action, "review": result}}

    if action == "kb_store":
        filename = _param(params, "filename")
        with new_session() as session:
            query = (session.query(ChatDocument)
                     .filter(ChatDocument.session_id == session_id,
                             ChatDocument.scope == "session"))
            if filename:
                query = query.filter(ChatDocument.filename.like(f"%{filename}%"))
            link = query.order_by(ChatDocument.id.desc()).first()
            if link is None:
                return {"content": "本会话还没有可入库的附件，请先上传文档。",
                        "meta": {"tool": action, "stored": False}}
            doc_id, name = link.doc_id, link.filename
        kb_store.promote_to_global(doc_id)
        with new_session() as session:
            row = session.query(ChatDocument).filter(ChatDocument.doc_id == doc_id).first()
            if row is not None:
                row.scope = "global"
                session.commit()
        return {"content": f"已将附件「{name}」存入本地知识库（全局可见）。",
                "meta": {"tool": action, "stored": True, "doc_id": doc_id}}

    if action == "kb_list":
        data = kb_store.list_documents(page_size=50)
        items = data.get("items", [])
        if not items:
            return {"content": "本地知识库目前没有文档。", "meta": {"tool": action, "documents": []}}
        lines = [f"- {item['doc_id']}｜{item['title']}（{item['chunks']} 段）" for item in items]
        return {"content": "本地知识库文档：\n" + "\n".join(lines),
                "meta": {"tool": action, "documents": items}}

    if action == "kb_delete":
        target = str(_param(params, "doc_id") or _param(params, "filename") or "").strip()
        if not target:
            raise ToolError("请提供要删除的文档 id 或文件名")
        data = kb_store.list_documents(page_size=100)
        candidates = [item for item in data.get("items", [])
                      if item["doc_id"] == target or target in item["title"]]
        if not candidates:
            return {"content": f"知识库里没有找到「{target}」。", "meta": {"tool": action}}
        removed = []
        for item in candidates:
            kb_store.delete_document(item["doc_id"], reviewer="chat-agent")
            with new_session() as session:
                session.query(ChatDocument).filter(
                    ChatDocument.doc_id == item["doc_id"]).delete()
                session.commit()
            removed.append(item["title"])
        return {"content": "已从知识库删除：" + "、".join(removed),
                "meta": {"tool": action, "deleted": removed}}

    if action == "memory_add":
        content = str(_param(params, "content") or "").strip()
        if not content:
            raise ToolError("缺少要记住的内容")
        result = memory_store.add_memory(
            content, str(_param(params, "category") or "preference"), session_id)
        if result and result.get("duplicate"):
            return {"content": "这条信息已经在长期记忆里了。", "meta": {"tool": action}}
        return {"content": f"已记住：{content}", "meta": {"tool": action, "memory": result}}

    if action == "memory_list":
        items = memory_store.list_memories()
        if not items:
            return {"content": "目前没有长期记忆。可以用 /remember 添加。",
                    "meta": {"tool": action, "memories": []}}
        lines = [f"- #{item['id']}｜{item['content']}" for item in items]
        return {"content": "长期记忆：\n" + "\n".join(lines),
                "meta": {"tool": action, "memories": items}}

    if action == "memory_delete":
        memory_id = _param(params, "memory_id")
        if not memory_id:
            raise ToolError("请提供要删除的记忆编号（/memory 可查看）")
        deleted = memory_store.delete_memory(int(memory_id))
        return {"content": "已删除该记忆。" if deleted else "没有找到该记忆。",
                "meta": {"tool": action, "deleted": deleted}}

    raise ToolError(f"未知工具动作：{action}")
