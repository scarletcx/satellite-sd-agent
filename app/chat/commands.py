"""斜杠命令：不经过模型，直接执行系统能力（/compact、/model、/missions…）。"""
from __future__ import annotations

from app.chat import context as context_store
from app.chat import memory as memory_store
from app.db import new_session
from app.models import ChatSession
from app.services import missions as mission_service
from app.tools.kb import store as kb_store

HELP = """可用命令：
/compact               手动压缩上下文
/context               查看上下文用量
/model [供应商] [模型]  查看或切换会话模型
/effort [low|medium|high|off]  查看或设置推理强度
/missions              查看任务列表
/mission <任务编号>     查看任务状态
/kb                    列出本地知识库
/kb store              把本会话附件存入知识库
/kb delete <文档id>     从知识库删除文档
/remember <内容>        写入长期记忆
/memory                查看长期记忆
/forget <编号>          删除一条长期记忆
/help                  显示本帮助
"""


def is_command(text: str) -> bool:
    return (text or "").strip().startswith("/")


def execute(session_id: str, text: str) -> dict:
    parts = (text or "").strip()[1:].split(maxsplit=1)
    name = parts[0].lower() if parts else ""
    argument = parts[1].strip() if len(parts) > 1 else ""

    if name in ("help", ""):
        return {"content": HELP, "meta": {"command": "help"}}

    if name == "compact":
        snapshot = context_store.compact(session_id, force=True)
        return {"content": (f"上下文已压缩：折叠 {snapshot['compacted_messages']} 条消息，"
                            f"当前使用约 {snapshot['percent']}%（{snapshot['used_tokens']}"
                            f"/{snapshot['window']} tokens）。"),
                "meta": {"command": "compact", "context": snapshot}}

    if name == "context":
        snapshot = context_store.context_snapshot(session_id)
        return {"content": (f"上下文用量：约 {snapshot['percent']}%"
                            f"（{snapshot['used_tokens']}/{snapshot['window']} tokens）；"
                            f"未折叠消息 {snapshot['pending_messages']} 条，"
                            f"摘要 {snapshot['summary_chars']} 字；"
                            f"自动压缩 {'开启' if snapshot['auto_compact'] else '关闭'}"
                            f"（阈值 {snapshot['threshold_pct']}%）。"),
                "meta": {"command": "context", "context": snapshot}}

    if name == "model":
        if argument:
            pieces = argument.split()
            provider_id = pieces[0]
            model = pieces[1] if len(pieces) > 1 else None
            with new_session() as session:
                chat = session.get(ChatSession, session_id)
                if chat is None:
                    return {"content": "会话不存在。", "meta": {"command": "model"}}
                chat.provider_id = provider_id
                chat.model = model
                session.commit()
            return {"content": f"已切换会话模型：{provider_id}"
                                f"{(' / ' + model) if model else ''}。",
                    "meta": {"command": "model", "provider_id": provider_id, "model": model}}
        with new_session() as session:
            chat = session.get(ChatSession, session_id)
            if chat is None:
                return {"content": "会话不存在。", "meta": {"command": "model"}}
            current = f"{chat.provider_id or '自动'}"
            if chat.model:
                current += f" / {chat.model}"
        return {"content": f"当前会话模型：{current}。用法：/model <供应商id> [模型名]",
                "meta": {"command": "model"}}

    if name == "effort":
        if argument:
            effort = argument.lower()
            if effort in ("off", "none", "default"):
                effort = None
            if effort not in (None, "low", "medium", "high"):
                return {"content": "推理强度可选：low / medium / high / off。",
                        "meta": {"command": "effort"}}
            with new_session() as session:
                chat = session.get(ChatSession, session_id)
                if chat is not None:
                    chat.reasoning_effort = effort
                    session.commit()
            return {"content": f"推理强度已设置为：{effort or '默认'}。",
                    "meta": {"command": "effort", "reasoning_effort": effort}}
        with new_session() as session:
            chat = session.get(ChatSession, session_id)
            current = (chat.reasoning_effort if chat else None) or "默认"
        return {"content": f"当前推理强度：{current}。用法：/effort low|medium|high|off",
                "meta": {"command": "effort"}}

    if name == "missions":
        items = mission_service.list_missions(limit=30)
        if not items:
            return {"content": "当前没有任务。", "meta": {"command": "missions", "tasks": []}}
        lines = [f"- {item['task_id']}｜{item['title']}｜{item['status']}" for item in items]
        return {"content": "任务列表：\n" + "\n".join(lines),
                "meta": {"command": "missions", "tasks": items}}

    if name == "mission":
        if not argument:
            return {"content": "用法：/mission <任务编号>", "meta": {"command": "mission"}}
        try:
            snapshot = mission_service.mission_snapshot(argument)
        except mission_service.MissionError as exc:
            return {"content": str(exc), "meta": {"command": "mission", "error": True}}
        gates = snapshot.get("pending_gates") or []
        content = (f"任务 {snapshot['task_id']}「{snapshot['title']}」：{snapshot['status']}，"
                   f"当前步骤 {snapshot['current_step'] or '-'}")
        if gates:
            content += "；待处理门禁：" + "、".join(
                gate.get("param_id") or gate.get("type") for gate in gates)
        return {"content": content, "meta": {"command": "mission", "mission": snapshot}}

    if name == "kb":
        sub = argument.split(maxsplit=1)
        action = sub[0].lower() if sub else "list"
        target = sub[1].strip() if len(sub) > 1 else ""
        if action == "delete":
            if not target:
                return {"content": "用法：/kb delete <文档id>", "meta": {"command": "kb"}}
            try:
                kb_store.delete_document(target, reviewer="chat-command")
            except Exception as exc:  # noqa: BLE001
                return {"content": f"删除失败：{exc}", "meta": {"command": "kb", "error": True}}
            return {"content": f"已删除文档：{target}", "meta": {"command": "kb", "deleted": target}}
        if action == "store":
            from app.chat.tools import execute as run_tool

            result = run_tool("kb_store", {}, session_id)
            return {**result, "meta": {**result.get("meta", {}), "command": "kb"}}
        data = kb_store.list_documents(page_size=50)
        items = data.get("items", [])
        if not items:
            return {"content": "本地知识库目前没有文档。", "meta": {"command": "kb", "documents": []}}
        lines = [f"- {item['doc_id']}｜{item['title']}" for item in items]
        return {"content": "本地知识库：\n" + "\n".join(lines),
                "meta": {"command": "kb", "documents": items}}

    if name == "remember":
        if not argument:
            return {"content": "用法：/remember <要记住的内容>", "meta": {"command": "remember"}}
        result = memory_store.add_memory(argument, "preference", session_id)
        if result and result.get("duplicate"):
            return {"content": "这条信息已经在长期记忆里了。", "meta": {"command": "remember"}}
        return {"content": f"已记住：{argument}", "meta": {"command": "remember", "memory": result}}

    if name == "memory":
        items = memory_store.list_memories()
        if not items:
            return {"content": "目前没有长期记忆。", "meta": {"command": "memory", "memories": []}}
        lines = [f"- #{item['id']}｜{item['content']}" for item in items]
        return {"content": "长期记忆：\n" + "\n".join(lines),
                "meta": {"command": "memory", "memories": items}}

    if name == "forget":
        if not argument.isdigit():
            return {"content": "用法：/forget <记忆编号>", "meta": {"command": "forget"}}
        deleted = memory_store.delete_memory(int(argument))
        return {"content": "已删除该记忆。" if deleted else "没有找到该记忆。",
                "meta": {"command": "forget", "deleted": deleted}}

    return {"content": f"未知命令 /{name}。输入 /help 查看可用命令。",
            "meta": {"command": name, "error": True}}
