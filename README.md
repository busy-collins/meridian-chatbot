---
title: Meridian Electronics Support
emoji: 💬
colorFrom: blue
colorTo: indigo
sdk: gradio
app_file: app.py
pinned: false
python_version: "3.12"
---

# Meridian Electronics — Customer Support Chatbot

> AI-powered customer support prototype built for Meridian Electronics using OpenAI Agents SDK and Model Context Protocol (MCP).

[![Live Demo](https://img.shields.io/badge/Live-HuggingFace-yellow)](https://huggingface.co/spaces/busy-collins/meridian-support)
[![Python](https://img.shields.io/badge/Python-3.12-blue)](https://python.org)
[![OpenAI](https://img.shields.io/badge/OpenAI-Agents%20SDK-green)](https://github.com/openai/openai-agents-python)

---

## The Business Problem

Meridian Electronics handles all customer inquiries manually via phone and email. This prototype demonstrates whether an AI-powered chatbot can handle the four most common customer workflows — product discovery, authentication, order history, and order placement — without human intervention.

---

## Live Demo

Visit: https://huggingface.co/spaces/busycollins/meridian-space

---

## What It Does

| Workflow | Tools Used | Auth Required |
|----------|-----------|---------------|
| Browse products | list_products, search_products | No |
| Get product details | get_product | No |
| View order history | list_orders, get_order | Yes |
| Place an order | create_order | Yes |
| Authenticate customer | verify_customer_pin | — |

---

## Architecture
Customer
↓
Gradio Chat UI (app.py)
↓
Authentication Gate
↓ (if authed)
OpenAI Agent (agent.py)
↓
MCPServerStreamableHttp
↓
https://order-mcp-74afyau24q-uc.a.run.app/mcp
(8 business tools — products, orders, customers)

---

## Key Technical Decisions

### Authentication at the Application Layer
Authentication is enforced in `app.py` using regex intent detection — not left to the AI agent. AI is non-deterministic and could skip credential checks depending on how the customer phrases their request. The gate is deterministic and cannot be bypassed.

### Streamable HTTP Transport
The MCP server is hosted remotely on Google Cloud Run. `MCPServerStreamableHttp` is the correct transport for remote servers. `MCPServerStdio` only works for local subprocess servers — choosing the wrong transport means nothing works.

### Session State Management
After successful `verify_customer_pin`, the customer ID is stored in Gradio session state and injected into every subsequent agent message. The customer authenticates once per session and never has to repeat their credentials.

### Cost-Effective Model
GPT-4o-mini is used throughout — accurate enough for customer support queries at a fraction of GPT-4o cost. The business case only works if per-conversation costs stay low.

---

## Project Structure
meridian-chatbot/
├── agent.py          # OpenAI Agent + MCP connection + tracing
├── app.py            # Gradio UI + auth gate + session state
├── requirements.txt  # Dependencies
├── .env.example      # Environment variable template
└── README.md
---

## Setup

```bash
git clone https://github.com/busy-collins/meridian-chatbot.git
cd meridian-chatbot

pip install -r requirements.txt

cp .env.example .env
# Fill in your values

python app.py
# Visit http://localhost:7860
```

---

## Environment Variables
---

## Limitations and Next Steps

| Limitation | Fix |
|-----------|-----|
| Session lost on restart | Redis session store |
| 25s timeout for complex queries | Streaming responses |
| Default Gradio UI | Next.js branded frontend |
| No human escalation | Handoff to live agent |

---

## Author

**Nwaogugu Chibuike Collins**
Andela AI Engineering Bootcamp — Final Assessment