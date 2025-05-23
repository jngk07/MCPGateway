# MCPGateway

# 🧠 OpenAPI + MCP Gateway

This project demonstrates how to convert any OpenAPI specification into a live, usable toolset for GenAI models like ChatGPT, Copilot, or Claude — using **FastMCP**.

> 📌 **Goal**: Bridge REST APIs with AI agents using the Model Context Protocol (MCP).

---

## 🔧 Features

- ✅ Converts OpenAPI/Swagger specs into MCP-compatible tools
- ✅ Supports **local and remote OpenAPI specs**
- ✅ Exposes APIs as **SSE endpoints** using Starlette
- ✅ Automatically mounts tools as `/apiName/v1/sse`
- ✅ Designed for use with **Copilot, Claude, ChatGPT**, and other AI systems
- ✅ Built with **FastAPI**, **Starlette**, and **FastMCP**

---

## 🚀 Architecture Overview

```plaintext
[OpenAPI Specs]
      ↓
[OpenAPIParser] -> [config.py Settings]
      ↓
[FastMCP.from_openapi()]
      ↓
[Unified SSE Server on /bikes/v1/sse]
      ↓
[Accessible by Copilot, Claude, ChatGPT] 

## Structure
📁 mcp_gateway_project/
├── main.py                # Entrypoint and server runner
├── config.py              # App configuration using Pydantic
├── openapi_parser.py      # Parses OpenAPI specs and generates tool config
├── api_specs/             # Local OpenAPI YAML/JSON specs
│   ├── bikes/
│   │   └── openapi.yaml
│   └── pets/
│       └── openapi.json
├── requirements.txt
└── README.md

## Requirments
pip install fastapi uvicorn httpx pyyaml fastmcp starlette
