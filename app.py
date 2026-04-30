import os
import re
import gradio as gr
from dotenv import load_dotenv
from agent import run_support_agent

load_dotenv(override=True)

EMAIL_RE     = re.compile(r"[\w\.-]+@[\w\.-]+\.\w+")
PIN_RE       = re.compile(r"\b(\d{4})\b")
ORDER_INTENT = re.compile(
    r"\b(order|orders|history|track|status|purchase|checkout|place|buy)\b",
    re.IGNORECASE,
)

def new_session():
    return {"authed": False, "customer_id": None, "email": None, "pending": None}

def session_label(s):
    if s and s.get("authed"):
        return f"**Session:** Authenticated — {s.get('email', '')}"
    return "**Session:** Not authenticated"

def needs_auth(msg):
    return bool(ORDER_INTENT.search(msg or ""))

def extract_email_pin(msg):
    e = EMAIL_RE.search(msg or "")
    p = PIN_RE.search(msg or "")
    return (e.group(0) if e else None, p.group(1) if p else None)

def content_to_str(content):
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(item.get("text", str(item)))
            elif hasattr(item, "text"):
                parts.append(item.text)
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content)

async def verify_pin_direct(email, pin):
    from agents.mcp import MCPServerStreamableHttp, MCPServerStreamableHttpParams
    mcp_url = os.getenv("MCP_SERVER_URL")
    if not mcp_url:
        return False, None, "Missing MCP_SERVER_URL"
    try:
        params = MCPServerStreamableHttpParams(url=mcp_url)
        async with MCPServerStreamableHttp(params=params) as mcp:
            res  = await mcp.call_tool("verify_customer_pin", {"email": email, "pin": pin})
            raw  = getattr(res, "content", None) or getattr(res, "output", None) or res
            text = content_to_str(raw)
            failed = any(w in text.lower() for w in [
                "invalid", "error", "not found", "incorrect", "wrong", "failed"
            ])
            if failed:
                return False, None, text
            uuid_m = re.search(
                r"\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b",
                text
            )
            customer_id = uuid_m.group(0) if uuid_m else None
            return True, customer_id, text
    except Exception as exc:
        return False, None, str(exc)

def history_to_tuples(history):
    tuples = []
    i = 0
    while i < len(history) - 1:
        h, a = history[i], history[i + 1]
        if (isinstance(h, dict) and h.get("role") == "user"
                and isinstance(a, dict) and a.get("role") == "assistant"):
            tuples.append((h["content"], a["content"]))
            i += 2
        else:
            i += 1
    return tuples

def add(history, role, content):
    return history + [{"role": role, "content": content}]

async def respond(message, history, session):
    if not message.strip():
        return "", history, session, session_label(session)

    session = session or new_session()
    hist    = history_to_tuples(history)

    # Not authenticated + order intent
    if not session["authed"] and needs_auth(message):
        session["pending"] = message
        reply = (
            "I can help with that. To access order information "
            "I need to verify your identity first.\n\n"
            "Please send your **email** and **4-digit PIN** — "
            "for example: `jane@example.com 1234`"
        )
        history = add(add(history, "user", message), "assistant", reply)
        return "", history, session, session_label(session)

    # Awaiting credentials
    if not session["authed"] and session.get("pending"):
        email, pin = extract_email_pin(message)
        if not email or not pin:
            reply = "Please send your email and 4-digit PIN together — e.g. `jane@example.com 1234`"
            history = add(add(history, "user", message), "assistant", reply)
            return "", history, session, session_label(session)

        ok, customer_id, raw = await verify_pin_direct(email, pin)
        if not ok:
            reply = f"Could not verify credentials. Please check and try again.\n\n_{raw[:200]}_"
            history = add(add(history, "user", message), "assistant", reply)
            return "", history, session, session_label(session)

        session["authed"]      = True
        session["customer_id"] = customer_id
        session["email"]       = email
        pending                = session.pop("pending")

        ctx = f" [SYSTEM: Verified. Email: {email}"
        if customer_id:
            ctx += f" Customer ID: {customer_id}"
        ctx += "]"

        agent_reply = await run_support_agent(pending + ctx, hist)
        reply       = f"Identity verified — welcome back!\n\n{agent_reply}"
        history     = add(add(history, "user", message), "assistant", reply)
        return "", history, session, session_label(session)

    # Authenticated
    enriched = message
    if session["authed"] and session.get("customer_id"):
        enriched = (
            f"{message} [SYSTEM: Authenticated. "
            f"Email: {session['email']} "
            f"Customer ID: {session['customer_id']}]"
        )

    reply   = await run_support_agent(enriched, hist)
    history = add(add(history, "user", message), "assistant", reply)
    return "", history, session, session_label(session)

def do_clear():
    s = new_session()
    return "", [], s, session_label(s)

with gr.Blocks(title="Meridian Electronics Support") as demo:

    state  = gr.State(new_session())
    gr.Markdown(
        "# Meridian Electronics — Customer Support\n"
        "I can help with **product availability**, **order history**, "
        "**placing orders**, and **account queries**."
    )
    banner  = gr.Markdown(session_label(new_session()))
    chatbot = gr.Chatbot(height=500)

    with gr.Row():
        box  = gr.Textbox(
            placeholder="e.g. What monitors do you have in stock?",
            container=False, scale=8
        )
        btn  = gr.Button("Send", variant="primary", scale=1)

    clear = gr.Button("Clear Chat")

    gr.Examples(
        examples=[
            "What monitors do you have available?",
            "Search for wireless keyboards",
            "I want to check my order history",
            "I want to place an order",
        ],
        inputs=[box]
    )

    gr.Markdown("---\n*Powered by OpenAI Agents SDK + MCP | Meridian Electronics 2026*")

    ins  = [box, chatbot, state]
    outs = [box, chatbot, state, banner]

    btn.click(respond,   inputs=ins, outputs=outs)
    box.submit(respond,  inputs=ins, outputs=outs)
    clear.click(do_clear, outputs=outs)

if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=int(os.getenv("PORT", "7860")),
        share=False,
        theme=gr.themes.Soft(),
    )