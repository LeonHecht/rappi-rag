from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from typing import List, Dict, Any
from pydantic import BaseModel
from typing import Any
import re
import json
import textwrap
import os
from pathlib import Path
from openai import OpenAI
from backend.app.core.config import settings
from backend.app.services.search import search_engine
from backend.app.dependencies import get_current_user

from dataclasses import dataclass, field
from typing import Any, List, Dict, Optional

@dataclass
class AgentConfig:
    model: str
    system_prompt: str
    tools: list
    max_iterations: int = 10
    parallel_tool_calls: bool = False
    reasoning_effort: str = "medium"
    reasoning_summary: str = "detailed"

@dataclass
class AgentContext:
    space: str
    openai_messages: List[Dict[str, Any]] = field(default_factory=list)
    last_user_msg: str = ""
    title: Optional[str] = None
    citations: List[Dict[str, str]] = field(default_factory=list)
    trace: List[Dict[str, Any]] = field(default_factory=list)
    iteration_count: int = 0
    final_answer: str = ""
    keep_reasoning: bool = True


class AgenticChatRequest(BaseModel):
    space: str
    messages: list[dict[str, Any]]   # role/content pairs
    state: str | None = None


router = APIRouter()
# Lazy OpenAI client initialization to avoid startup failures when OPENAI_API_KEY is missing
client: OpenAI | None = None
PROMPTS_DIR = Path(__file__).resolve().parents[3] / "prompts"
SYSTEM_PROMPT = (PROMPTS_DIR / "system_prompt.md").read_text(encoding="utf-8").strip()

def get_openai_client() -> OpenAI | None:
    """Return a cached OpenAI client if OPENAI_API_KEY is configured, else None."""
    global client
    if client is not None:
        return client
    api_key = settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        client = OpenAI(api_key=api_key)
        return client
    except Exception:
        return None

emit_msg_tool = {
  "type": "function",
  "name": "emit_event",
  "description": "Emit a short, user-visible reasoning note (user's goal, plan, decision, progress).",
  "parameters": {
    "type": "object",
    "properties": {
      "kind": { "type": "string", "enum": ["user_goal_plan","decision","note","progress"] },
      "message": { "type": "string" },
    },
    "required": ["message"]
  }
}

retrieval_tools = [
    {
        "type": "function",
        "name": "search_documents",
        "description": "Lexical keyword search over indexed documents in the selected space.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "User intent expressed as concise search keywords."},
                "filters": {
                    "type": "object",
                    "properties": {
                        "year_from": { "type": "integer" },
                        "year_to":   { "type": "integer" },
                        "court":     { "type": "string" },
                        "matter":    { "type": "string" }
                    },
                    "additionalProperties": False
                },
                "top_k": { "type": "integer", "default": 5, "minimum": 1, "maximum": 50 },
            },
            "required": ["query"]
        }
    },
    {
        "type": "function",
        "name": "fetch_passages",
        "description": "Return top passages for selected doc IDs (ordered).",
        "parameters": {
        "type":"object",
        "properties":{
            "ids":{"type":"array","items":{"type":"string"},"minItems":1,"maxItems":20},
            "per_id":{"type":"integer","default":3,"minimum":1,"maximum":10},
            "max_tokens":{"type":"integer","default":350,"minimum":64,"maximum":512},
        },
        "required":["ids"]
        }
    },
    {
        "type": "function",
        "name": "fetch_document",
            "description": "Return a full text document. Costly; avoid unless the full document is needed.",
        "parameters": {
            "type":"object",
            "properties":{
            "id":{"type":"string"},
            "max_tokens":{"type":"integer","default":2048,"minimum":512,"maximum":4096}
            },
            "required":["id"]
        }
    }
]

tools = [emit_msg_tool, *retrieval_tools] if settings.TOOL_RETRIEVAL else [emit_msg_tool]

def sanitize_output_items(raw_items):
    """Convert SDK output items to API-acceptable input items."""
    sanitized = []
    for it in raw_items or []:
        obj = it.model_dump() if hasattr(it, "model_dump") else it
        t = obj.get("type")

        if t == "function_call":
            sanitized.append({
                "type": "function_call",
                "name": obj.get("name"),
                # must be a JSON STRING, not dict
                "arguments": obj.get("arguments") or "{}",
                "call_id": obj.get("call_id"),
            })
        elif t == "function_call_output":
            sanitized.append({
                "type": "function_call_output",
                "call_id": obj.get("call_id"),
                "output": obj.get("output", ""),
            })
        elif t == "message":
            # keep only role+content (optional; you can drop messages entirely)
            role = obj.get("role")
            parts = obj.get("content") or []
            text = ""
            if isinstance(parts, list):
                text = "".join(p.get("text","") for p in parts if isinstance(p, dict))
            elif isinstance(parts, str):
                text = parts
            if role in ("user","assistant","system"):
                sanitized.append({"role": role, "content": text})
        else:
            # drop 'reasoning' and anything else
            continue
    return sanitized

def log_tool_call(step: int, name: str, args: dict, result: Any):
    # keep logs readable & bounded
    args_preview = json.dumps(args, ensure_ascii=False)[:1000]
    if isinstance(result, (dict, list)):
        # count-y summary to avoid dumping full payloads
        if isinstance(result, list):
            result_info = f"list(len={len(result)})"
        else:
            result_info = f"dict(keys={list(result.keys())[:6]})"
    else:
        result_info = str(result)
    print(textwrap.dedent(f"""
    🧰 Tool Step {step}
    ├─ name: {name}
    ├─ args: {args_preview}
    └─ result: {result_info}
    """).rstrip())

def search_documents(query: str, space: str = "", filters: Dict[str, Any] = {}, top_k: int = 5) -> List[Dict[str, Any]]:
    """ query OpenSearch and return compact hits (IDs + short snippets + meta)
    """
    # perform search; Filters will be implemented lateron (TODO)
    hits = search_engine.search(query=query, top_k=top_k, space=space)

    # hits has [{"id", "title", "score", "snippet", "download_url"}]
    return hits

def fetch_passages(query: str, ids: List[str], space: str = "", per_id: int = 3, max_tokens: int = 350) -> List[Dict[str, Any]]:
    """Return top passages for selected hit IDs (ordered). """
    passages = []

    for id in ids:
        top_passages_for_id = search_engine.fetch_passages(space=space,
                                                            doc_id=id,
                                                            query=query,
                                                            per_id=per_id,
                                                            max_tokens=max_tokens)
        passages.extend(top_passages_for_id)
    
    return passages

def fetch_document(id: str, space: str = "", max_tokens: int = 2048) -> Dict[str, Any]:
    doc = search_engine.get_document_by_id(space=space, doc_id=id)
    if doc is None:
        print("[fetch_document] Document not found:", id)
    elif doc.get("text") == "":
        print("[fetch_document] Document has empty text:", id)
    return doc if doc is not None else {}

def clip(s, max_chars=16000):
    return s if len(s)<=max_chars else s[:max_chars]

def sse(event: str, data: Dict[str, Any]) -> str:
    return f"event: {event}\n" + f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

def normalize_title(raw: str | None, fallback: str | None) -> str | None:
    """Trim quotes/whitespace and cap to 5 words. Fallback to first 5 words of user msg if empty."""
    t = (raw or "").strip().strip('"').strip("'")
    t = re.sub(r"\s+", " ", t)
    if not t and fallback:
        t = " ".join((fallback or "").split()[:5]).strip()
    if t:
        t = " ".join(t.split()[:5])
        return t or None
    return None

def extract_inline_citations(text: str):
    # Parse inline [DocID §citation] markers from the final answer so the UI can place citations exactly inline.
    # Matches [DocID] or [DocID §hint]; DocID excludes closing bracket and whitespace
    # Examples: [38949], [38949 §sentencia condenatoria]
    pattern = re.compile(r"\[([^\]\s]+)(?:\s*§\s*([^\]]+))?\]")
    occ = []
    for m in pattern.finditer(text or ""):
        doc_id = (m.group(1) or "").strip()
        cite = (m.group(2) or "").strip() if m.lastindex and m.group(2) else ""
        occ.append({
            "doc_id": doc_id,
            "cite": cite,
            "start": m.start(),
            "end": m.end(),
        })
    return occ

def get_title_for_chat(last_user_msg):
    try:
        # print("\n📝 **Generating Chat Title**")
        oc = get_openai_client()
        if oc is None:
            raise RuntimeError("OPENAI_API_KEY not configured")
        response = oc.responses.create(
            model="gpt-4.1-nano",
            instructions="Given this user's request, give the Chat a title that will be shown in the list of chats. Return a string of max 5 words. Don't return any additional content, just the title.",
            input=[{"role": "user", "content": last_user_msg[:200]}],
            # reasoning={"effort": "low"},
        )
        raw_title = response.output_text
        title = normalize_title(raw_title, last_user_msg)
        # print(f"Generated title: {title}")
    except Exception as e:
        print(f"[title] generation failed: {e}")
        title = normalize_title("", last_user_msg)
    return title

def is_respond_fast(last_user_msg):
    try:
        instruction = """
You have the task to decide whether the user's request requires a reasoning model with access to the configured document knowledge base, or if a fast model without access to tools is enough.
Return 'reasoning_model' if the user's request is complex and requires deep thinking.
Also return 'reasoning_model' if the user's request requires external knowledge from the configured document knowledge base.
Return 'fast_model' if the user's request is rather simple or a general knowledge question not requiring external facts or data.
"""
        # print("\n📝 **Deciding if to respond fast**")
        oc = get_openai_client()
        if oc is None:
            return False
        response = oc.responses.create(
            model="gpt-4.1-mini",
            instructions=instruction,
            input=[{"role": "user", "content": f"User request:\n{last_user_msg}"}],
            # reasoning={"effort": "low"},
        )
        # print("response:", response.output_text)
        if "fast_model" in response.output_text.strip().lower():
            print("Decided to respond fast.")
            return True
        elif "reasoning_model" in response.output_text.strip().lower():
            print("Decided to use full reasoning.")
            return False
        else:
            print("Could not decide; defaulting to full reasoning.")
            return False
    except Exception as e:
        return False
        
def run_tool(ctx: AgentContext, tool_name, tool_args) -> str:
    """ do before: tool_args = json.loads(item.arguments) """
    
    def push_trace(evt):  # uniform schema for UI
        # evt: {type, step, tool?, args?, message?, status?, result_count?}
        ctx.trace.append(evt)
    
    if tool_name == "emit_event":
        # result to be ack'd back into openai_messages later
        result = json.dumps({"ok": True})
        
        push_trace({
            "type": "reasoning",
            "step": ctx.iteration_count,
            "message": tool_args.get("message",""),
            "kind": tool_args.get("kind","note"),
        })

        log_tool_call(ctx.iteration_count, tool_name, tool_args, "emitted")
    
    elif tool_name == "search_documents":
        query = tool_args.get("query", ctx.last_user_msg)
        filters = tool_args.get("filters", {})
        top_k = int(tool_args.get("top_k", 5))

        push_trace({"type":"tool_start","step":ctx.iteration_count,"tool":"search_documents","args":{"query": query,"filters":filters,"top_k":top_k}})
        result = search_documents(query=query, space=ctx.space, filters=filters, top_k=top_k)
        push_trace({"type":"tool_result","step":ctx.iteration_count,"tool":"search_documents","result_count":len(result)})
        log_tool_call(ctx.iteration_count, tool_name, tool_args, result)

    elif tool_name == "fetch_passages":
        ids = tool_args.get("ids", [])
        per_id = int(tool_args.get('per_id', 3))
        max_tokens = int(tool_args.get('max_tokens', 350))

        push_trace({"type":"tool_start","step":ctx.iteration_count,"tool":"fetch_passages","args":{"ids":ids,"per_id":per_id,"max_tokens":max_tokens}})
        result = fetch_passages(query=ctx.last_user_msg, ids=ids, space=ctx.space, per_id=per_id, max_tokens=max_tokens)
        try:
            for p in result or []:
                did = (p or {}).get("doc_id") or (p or {}).get("id")
                if did:
                    snip = (p or {}).get("passage") or (p or {}).get("snippet") or ""
                    ctx.citations.append({"doc_id": did, "snippet": snip[:400]})
        except Exception as _e:
            pass
        push_trace({"type":"tool_result","step":ctx.iteration_count,"tool":"fetch_passages","result_count":len(result)})
        log_tool_call(ctx.iteration_count, tool_name, tool_args, result)
    
    elif tool_name == "fetch_document":                    
        doc_id = tool_args.get("id", "")
        max_tokens = int(tool_args.get("max_tokens", 2048))

        push_trace({"type":"tool_start","step":ctx.iteration_count,"tool":"fetch_document","args":{"id":doc_id,"max_tokens":max_tokens}})
        result = fetch_document(id=doc_id, space=ctx.space, max_tokens=max_tokens)
        try:
            if isinstance(result, dict):
                did = result.get("id") or doc_id
                txt = (result.get("text") or "")
                if did and txt:
                    ctx.citations.append({"doc_id": did, "snippet": txt[:240]})
        except Exception as _e:
            pass
        push_trace({"type":"tool_result","step":ctx.iteration_count,"tool":"fetch_document","result_count":1 if result else 0})
        log_tool_call(ctx.iteration_count, tool_name, tool_args, result)            
    
    else:
        print(f"❌ **Unknown tool name: {tool_name}**")
        result = "Unknown tool"

    return result

def dedupe_citations(cites: list[dict]) -> list[dict]:
    seen = set(); out=[]
    for c in cites:
        did = c.get("doc_id")
        if did and did not in seen:
            out.append(c); seen.add(did)
    return out

import asyncio
import json

@router.post("/chat/agentic/stream")
async def chat_agentic_stream(req: AgenticChatRequest):
    
    openai_messages: list[dict[str, Any]] = []
    if req.state:
        try:
            s = json.loads(req.state)
            if isinstance(s, list):
                openai_messages = s
        except Exception as e:
            print("bad state:", e)

    last_user_msg = req.messages[-1]['content']
    openai_messages.append({"role": "user", "content": last_user_msg})
    # print(f"openai_messages: {openai_messages}")

    ctx = AgentContext(space=req.space, openai_messages=openai_messages, last_user_msg=last_user_msg)
    cfg = AgentConfig(model=settings.OPENAI_CHAT_MODEL, system_prompt=SYSTEM_PROMPT, tools=tools)

    # final_answer = ""
    # citations: list[dict[str, str]] = []
    # keep_reasoning = True
    # max_iterations = 10
    # iteration_count = 0
    # trace: list[dict[str, Any]] = []

    # title: str | None = None
    if len(openai_messages) == 1:
        set_title = True
    else:
        set_title = False

    async def event_stream():
        nonlocal ctx, cfg

        # helper to emit SSE json with a custom event name
        async def emit(event: str, obj: dict):
            yield f"event: {event}\n".encode("utf-8")
            yield f"data: {json.dumps(obj, ensure_ascii=False)}\n\n".encode("utf-8")


        while ctx.keep_reasoning and ctx.iteration_count < cfg.max_iterations:
            ctx.iteration_count += 1
            # print(f"\n🔄 **Reasoning Iteration {ctx.iteration_count}**")

            if ctx.iteration_count == cfg.max_iterations:
                extra_finalize_note = (
                    "You have reached the maximum reasoning iterations. "
                    "Do NOT call more tools. Produce the final answer now. If you still couldn't gather enough information, state that clearly in your answer. It is better to be honest than to invent information."
                )
                final_instructions = f"{cfg.system_prompt}\n\n[control] {extra_finalize_note}"
            else:
                final_instructions = cfg.system_prompt

            oc = get_openai_client()
            if oc is None:
                # If OpenAI is not configured, fail fast with a clear SSE message
                async for chunk in emit("response.completed", {"answer": "OpenAI is not configured.", "citations": [], "trace": [], "trace_len": 0, "agent_state": "[]"}):
                    yield chunk
                return
            stream = oc.responses.create(
                model=cfg.model,
                instructions=final_instructions,
                input=ctx.openai_messages,
                tools=cfg.tools,
                parallel_tool_calls=cfg.parallel_tool_calls,
                reasoning={"effort": cfg.reasoning_effort, "summary": cfg.reasoning_summary},
                max_tool_calls=cfg.max_iterations,
                tool_choice="auto",
                stream=True,
            )

            # Local accumulators for this streamed turn
            acc_text: list[str] = []
            
            final_tool_calls = {}
            for ev in stream:
                t = getattr(ev, "type", None)

                # Output Item
                if t == "response.output_item.added":
                    if ev.item.type == "function_call":
                        final_tool_calls[ev.output_index] = ev.item
                    elif ev.item.type == "reasoning":
                        pass  # no action needed

                # Reasoning (UI)
                if t == "response.reasoning_summary_text.delta":
                    pass
                if t == "response.reasoning_text.delta":
                    pass
                if t == "response.reasoning_summary_part.added":
                    pass

                # Function tools
                if t == "response.function_call_arguments.delta":
                    index = ev.output_index
                    if final_tool_calls[index]:
                        final_tool_calls[index].arguments += ev.delta

                if t == "response.function_call_arguments.done":
                    index = ev.output_index
                    tool_call = final_tool_calls[index]
                    tool_name = getattr(tool_call, "name")
                    tool_args = json.loads(getattr(tool_call, "arguments"))

                    if tool_name == "emit_event":
                        msg = tool_args.get("message", "Pensando")
                    elif tool_name == "search_documents":
                        query = tool_args.get("query", "[Consulta no disponible.]")
                        msg = f"Buscando documentos relevantes a la siguiente consulta: {query}..."
                    elif tool_name == "fetch_passages":
                        msg = "Recuperando pasajes relevantes..."
                    elif tool_name == "fetch_document":
                        msg = "Recuperando documentos relevantes..."
                    else:
                        break
                    
                    await asyncio.sleep(0)  # optional, helps flush
                    async for chunk in emit("response.emit_message", {"step": ctx.iteration_count, "msg": msg}):
                        yield chunk
                    
                    break
                
                # Output text
                if t == "response.output_text.delta":
                    d = getattr(ev, "delta", "") or ""
                    acc_text.append(d)
                    await asyncio.sleep(0)  # optional, helps flush
                    async for chunk in emit("response.output_text.delta", {"step": ctx.iteration_count, "delta": d}):
                        yield chunk
                if t == "response.output_text.done":
                    txt = getattr(ev, "text", "") or ""
                    ctx.final_answer = txt or "".join(acc_text)
                    await asyncio.sleep(0)  # optional, helps flush
                    async for chunk in emit("response.output_text.done", {"step": ctx.iteration_count, "text": ctx.final_answer}):
                        yield chunk

                    if ctx.final_answer:
                        ctx.openai_messages.append({
                            "role": "assistant",
                            "content": ctx.final_answer
                        })
                    ctx.keep_reasoning = False

                # Completion
                if t == "response.completed":
                    pass

            stream.close()

            for tool_call_index in final_tool_calls:
                tool_call = final_tool_calls[tool_call_index]
                    
                tool_name = getattr(tool_call, "name")
                tool_args = json.loads(getattr(tool_call, "arguments"))
                call_id = getattr(tool_call, "call_id")

                ctx.openai_messages.append({
                    "type": "function_call",
                    "name": tool_name,
                    "arguments": json.dumps(tool_args, ensure_ascii=False),
                    "call_id": call_id
                })

                result = run_tool(ctx, tool_name, tool_args)

                # clip result to prevent context balooning (cost management)
                result = clip(str(result))

                print(f"🛠️ **Tool {tool_name} returned result (start): {result}**")

                # Append tool call and observation to messages for next iteration
                ctx.openai_messages.append({
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": str(result),
                })
            
            continue  # next reasoning iteration

        if ctx.final_answer == "":
            ctx.final_answer = (
                "No pude completar el razonamiento completo para contestar su pregunta. "
                "¿Te parece bien que resuma los resultados encontrados hasta ahora?"
            )

        inline_occurrences = extract_inline_citations(ctx.final_answer)

        if set_title and not ctx.title:
            ctx.title = get_title_for_chat(last_user_msg)

        completed_payload = {
            "answer": ctx.final_answer,
            "title": ctx.title,
            "citations": dedupe_citations(ctx.citations),
            "inline_citations": inline_occurrences,
            "trace_len": len(ctx.openai_messages),
            "trace": ctx.trace,
            "agent_state": json.dumps(ctx.openai_messages),
        }

        # Final summary event (mirrors your non-stream return payload)
        async for chunk in emit("response.completed", completed_payload):
            yield chunk
    
    return StreamingResponse(event_stream(), media_type="text/event-stream")
