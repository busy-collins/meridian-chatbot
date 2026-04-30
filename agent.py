"""
Meridian Electronics Customer Support Agent
"""
import os
import time
import json
import uuid
import logging
import asyncio
from typing import Optional, Any
import dotenv

from agents import Agent, Runner, OpenAIChatCompletionsModel
from agents.mcp import MCPServerStreamableHttp, MCPServerStreamableHttpParams
from openai import AsyncOpenAI

dotenv.load_dotenv(override=True)

logger = logging.getLogger("meridian")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL") or "https://order-mcp-74afyau24q-uc.a.run.app/mcp" 
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
MAX_TURNS = int(os.getenv("MAX_TURNS", "10"))
TIMEOUT_S = float(os.getenv("AGENT_TIMEOUT_S", "25"))

INSTRUCTIONS = """
You are a customer support assistant for Meridian Electronics,
a company that sells computer products including monitors,
keyboards, printers, networking gear, and accessories.

You help customers with four workflows:

1. PRODUCT DISCOVERY
   Use list_products, search_products, get_product
   Help customers find what they need and check availability

2. CUSTOMER AUTHENTICATION
   Use verify_customer_pin with email and 4-digit PIN
   Always authenticate before placing orders or showing order history
   Ask for email first, then PIN

3. ORDER HISTORY
   Use list_orders with customer_id after authentication
   Use get_order for specific order details

4. ORDER PLACEMENT
   Use create_order after authentication
   Confirm product SKU, quantity, and price before placing
   Use get_product to confirm current price before ordering

Rules:
- Always verify customer identity before order actions
- Never guess product SKUs — always search first
- Confirm order details with customer before submitting
- Be concise, professional, and helpful
- If something fails, explain clearly and offer alternatives
"""

def _now_ms() -> int:
    return int(time.time() * 1000)

def history_to_text(history: Any) -> str:
    """
    Gradio history can be different shapes depending on version/config:
    - list[tuple[user, assistant]]
    - list[dict{role, content}]
    - mixed
    Normalize to a plain transcript string.
    """
    if not history:
        return ""

    lines = []
    for h in history:
        # tuple/list: (user, assistant)
        if isinstance(h, (list, tuple)) and len(h) == 2:
            user, assistant = h
            lines.append(f"Customer: {user}")
            lines.append(f"Agent: {assistant}")
            continue

        # dict: {"role": "...", "content": "..."}
        if isinstance(h, dict) and "role" in h and "content" in h:
            role = h.get("role")
            content = h.get("content")
            if role == "user":
                lines.append(f"Customer: {content}")
            elif role == "assistant":
                lines.append(f"Agent: {content}")
            else:
                lines.append(f"{str(role).capitalize()}: {content}")
            continue

        # fallback
        lines.append(str(h))

    return "\n".join(lines) + "\n\n"

async def _run_agent_inner(message: str, history: Any, trace_id: str) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error(json.dumps({"trace": trace_id, "event": "missing_openai_key"}))
        return f"Server misconfigured: missing OPENAI_API_KEY. (trace: {trace_id})"

    if not MCP_SERVER_URL:
        logger.error(json.dumps({"trace": trace_id, "event": "missing_mcp_server_url"}))
        return f"Server misconfigured: missing MCP_SERVER_URL. (trace: {trace_id})"

    client = AsyncOpenAI(api_key=api_key)

    # Build plain transcript + current message
    full_input = history_to_text(history) + f"Customer: {message}"

    logger.info(json.dumps({"trace": trace_id, "event": "agent_start"}))

    t_mcp0 = _now_ms()
    params = MCPServerStreamableHttpParams(url=MCP_SERVER_URL)

    async with MCPServerStreamableHttp(params=params) as mcp:
        logger.info(json.dumps({"trace": trace_id, "event": "mcp_connected", "ms": _now_ms() - t_mcp0}))

        agent = Agent(
            name="Meridian Support Agent",
            instructions=INSTRUCTIONS,
            model=OpenAIChatCompletionsModel(model=OPENAI_MODEL, openai_client=client),
            mcp_servers=[mcp],
        )

        t_run0 = _now_ms()
        result = await Runner.run(agent, input=full_input, max_turns=MAX_TURNS)
        out = result.final_output or ""

        logger.info(json.dumps({
            "trace": trace_id,
            "event": "agent_done",
            "agent_ms": _now_ms() - t_run0,
            "output_chars": len(out),
        }))
        return out

async def run_support_agent(message: str, history: Any = None, trace_id: Optional[str] = None) -> str:
    """
    Public API used by app.py.
    Adds timeout + end-to-end timing and keeps response user-friendly.
    """
    trace_id = trace_id or str(uuid.uuid4())[:8]
    t0 = _now_ms()

    try:
        out = await asyncio.wait_for(_run_agent_inner(message, history, trace_id), timeout=TIMEOUT_S)
        logger.info(json.dumps({"trace": trace_id, "event": "request_end", "total_ms": _now_ms() - t0}))
        return out
    except asyncio.TimeoutError:
        logger.warning(json.dumps({"trace": trace_id, "event": "agent_timeout", "total_ms": _now_ms() - t0}))
        return f"Our support tools are taking too long to respond. Please try again shortly. (trace: {trace_id})"
    except Exception as e:
        logger.exception(json.dumps({
            "trace": trace_id,
            "event": "agent_error",
            "total_ms": _now_ms() - t0,
            "err_type": type(e).__name__,
            "message": str(e)[:300],
        }))
        return f"Sorry — I couldn’t complete that right now. Please try again. (trace: {trace_id})"