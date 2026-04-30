"""
Meridian Electronics Customer Support Agent
- Connects to MCP (Streamable HTTP)
- Uses OpenAI Agents SDK
- Provides lightweight tracing logs
"""
import os
import time
import json
import uuid
import asyncio
import logging
from typing import Any, Optional

from dotenv import load_dotenv
from openai import AsyncOpenAI
from agents import Agent, Runner, OpenAIChatCompletionsModel
from agents.mcp import MCPServerStreamableHttp, MCPServerStreamableHttpParams

load_dotenv(override=True)

logger = logging.getLogger("meridian")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL")  # required in HF Secrets
OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
MAX_TURNS      = int(os.getenv("MAX_TURNS", "10"))
TIMEOUT_S      = float(os.getenv("AGENT_TIMEOUT_S", "25"))

INSTRUCTIONS = """
You are a customer support assistant for Meridian Electronics.

You can:
- Product discovery: list_products, search_products, get_product
- Authentication: verify_customer_pin (email + 4-digit PIN)
- Order history: list_orders, get_order (requires auth)
- Place orders: create_order (requires auth)

Rules:
- Always authenticate before order actions.
- Never guess SKUs; use search/get_product.
- Confirm order details before creating an order.
- Be concise, professional, and helpful.
"""

def _now_ms() -> int:
    return int(time.time() * 1000)

def _history_to_text(history: Any) -> str:
    """
    Normalize history from Gradio into a transcript.
    history is typically list[tuple[user, assistant]].
    """
    if not history:
        return ""
    lines = []
    for h in history:
        if isinstance(h, (list, tuple)) and len(h) == 2:
            u, a = h
            lines.append(f"Customer: {u}")
            lines.append(f"Agent: {a}")
    return "\n".join(lines) + "\n\n"

async def _run_agent_inner(message: str, history: Any, trace_id: str) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return f"Server misconfigured: missing OPENAI_API_KEY. (trace: {trace_id})"
    if not MCP_SERVER_URL:
        return f"Server misconfigured: missing MCP_SERVER_URL. (trace: {trace_id})"

    client = AsyncOpenAI(api_key=api_key)
    full_input = _history_to_text(history) + f"Customer: {message}"

    params = MCPServerStreamableHttpParams(url=MCP_SERVER_URL)

    t_mcp0 = _now_ms()
    async with MCPServerStreamableHttp(params=params) as mcp:
        logger.info(json.dumps({"trace": trace_id, "event": "mcp_connected", "ms": _now_ms() - t_mcp0}))

        agent = Agent(
            name="Meridian Support Agent",
            instructions=INSTRUCTIONS,
            model=OpenAIChatCompletionsModel(model=OPENAI_MODEL, openai_client=client),
            mcp_servers=[mcp],
        )

        result = await Runner.run(agent, input=full_input, max_turns=MAX_TURNS)
        return result.final_output or ""

async def run_support_agent(message: str, history: Any = None, trace_id: Optional[str] = None) -> str:
    """
    Main entry used by app.py
    """
    trace_id = trace_id or str(uuid.uuid4())[:8]
    t0 = _now_ms()

    try:
        out = await asyncio.wait_for(_run_agent_inner(message, history, trace_id), timeout=TIMEOUT_S)
        logger.info(json.dumps({"trace": trace_id, "event": "agent_done", "total_ms": _now_ms() - t0}))
        return out
    except asyncio.TimeoutError:
        return f"Our support tools are taking too long right now. Please try again. (trace: {trace_id})"
    except Exception as e:
        logger.exception(json.dumps({"trace": trace_id, "event": "agent_error", "msg": str(e)[:200]}))
        return f"Sorry — I couldn’t complete that right now. Please try again. (trace: {trace_id})"