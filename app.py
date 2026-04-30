import os
import gradio as gr
from dotenv import load_dotenv
from agent import run_support_agent

load_dotenv()

def new_session():
    return {"authed": False, "customer_id": None, "email": None}

def session_label(session):
    if session and session.get("authed"):
        return f"Session: Authenticated ({session.get('email', '')})"
    return "Session: Not authenticated"

async def respond(message, history, session):
    session = session or new_session()
    reply   = await run_support_agent(message, history)
    history = history + [
        {"role": "user",      "content": message},
        {"role": "assistant", "content": reply}
    ]
    return "", history, session, session_label(session)

def do_clear():
    return "", [], new_session(), session_label(new_session())

with gr.Blocks(title="Meridian Electronics Support") as demo:
    gr.Markdown(
        "# Meridian Electronics — Customer Support\n"
        "I can help with **product availability**, **order history**, "       "**placing orders**, and **account queries**."
    )

    session   = gr.State(new_session())
    status_md = gr.Markdown(session_label(new_session()))
    chatbot   = gr.Chatbot(height=500)

    with gr.Row():
        msg  = gr.Textbox(
            placeholder = "e.g. What monitors do you have in stock?",
            container   = False,
            scale       = 8
        )
        send = gr.Button("Send", variant="primary", scale=1)

    clear = gr.Button("Clear Chat")

    gr.Examples(
        examples = [
            "What monitors do you have available?",
            "I want to check my order history",
            "Can you help me place an order for a keyboard?",
            "Search for wireless products",
        ],
        inputs = [msg]
    )

    gr.Markdown("---\n*Powered by OpenAI Agents SDK + MCP | Meridian Electronics 2026*")

    ins  = [msg, chatbot, session]
    outs = [msg, chatbot, session, status_md]

    send.click(respond,  inputs=ins, outputs=outs)
    msg.submit(respond,  inputs=ins, outputs=outs)
    clear.click(do_clear, outputs=outs)

if __name__ == "__main__":
    demo.launch(
        server_name = "0.0.0.0",
        server_port = int(os.getenv("PORT", "7860")),
        share       = False,
        theme       = gr.themes.Soft(),
    )
