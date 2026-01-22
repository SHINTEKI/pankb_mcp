"""
MCP Client: Connect to MCP Server, convert tools to OpenAI function calling format
(Streaming version)
"""
import json
from dataclasses import dataclass
from typing import AsyncGenerator

from fastmcp import Client
from openai import AsyncOpenAI


@dataclass
class AgentEvent:
    """Event yielded during chat processing"""
    type: str  # "tool_start", "tool_result", "text"
    content: str | None = None  # text content or tool result string
    tool_name: str | None = None
    tool_args: dict | None = None
    result_type: str | None = None  # "chart", "table", or None
    parsed_data: dict | None = None


class MCPClient:
    def __init__(
        self,
        mcp_server_url: str,
        openai_api_key: str,
        model: str = "gpt-4o-mini",
        auth=None,
        system_prompt: str | None = None,
    ):
        if not mcp_server_url:
            raise ValueError("mcp_server_url is required")
        if not openai_api_key:
            raise ValueError("openai_api_key is required")
        if not auth:
            raise ValueError("auth is required (use BearerAuth)")

        self.mcp_server_url = mcp_server_url
        self.model = model
        self.auth = auth
        self.openai = AsyncOpenAI(api_key=openai_api_key)
        self.tools_cache: list[dict] = []
        self.messages: list[dict] = []
        if system_prompt:
            self.messages.append({"role": "system", "content": system_prompt})

    def _create_mcp_client(self) -> Client:
        return Client(self.mcp_server_url, auth=self.auth)

    def clear_history(self, keep_system_prompt: bool = True):
        """Clear conversation history, optionally keeping system prompt"""
        if keep_system_prompt:
            system_msg = next((m for m in self.messages if m["role"] == "system"), None)
            self.messages = [system_msg] if system_msg else []
        else:
            self.messages = []

    # def _trim_messages(self, max_messages: int = 40):
    #     """Keep system prompt + most recent messages to avoid context overflow"""
    #     if len(self.messages) <= max_messages:
    #         return
    #
    #     system_msg = self.messages[0] if self.messages[0]["role"] == "system" else None
    #     recent = self.messages[-max_messages:]
    #     self.messages = [system_msg] + recent if system_msg else recent

    async def connect(self):
        """Connect to MCP Server and fetch tools"""
        async with self._create_mcp_client() as client:
            mcp_tools = await client.list_tools()
            self.tools_cache = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description or "",
                        "parameters": t.inputSchema or {"type": "object", "properties": {}}
                    }
                }
                for t in mcp_tools
            ]

    def _parse_result(self, result_str: str) -> tuple[str | None, dict | None]:
        """Parse tool result for chart/table data"""
        try:
            data = json.loads(result_str)
            if isinstance(data, dict) and data.get("type") in ("chart", "table", "string"):
                return data["type"], data
        except (json.JSONDecodeError, TypeError):
            pass
        return None, None

    async def _call_tool(self, name: str, args: dict) -> tuple[str, str | None, dict | None, str | None]:
        """
        Call MCP tool and return (result_str, result_type, parsed_data, image_base64)

        Handles MCP standard format where tool may return multiple content blocks:
        - ImageContent: base64 image for AI understanding
        - TextContent: JSON data for rendering
        """
        try:
            async with self._create_mcp_client() as client:
                result = await client.call_tool(name, args)

                result_str = ""
                image_base64 = None
                result_type = None
                parsed_data = None

                # Process all content blocks
                for content in result.content:
                    if hasattr(content, "text"):
                        # TextContent - could be JSON data
                        result_str = content.text
                        result_type, parsed_data = self._parse_result(result_str)
                    elif hasattr(content, "data") and hasattr(content, "mimeType"):
                        # ImageContent - base64 image
                        if content.mimeType.startswith("image/"):
                            image_base64 = content.data

                return result_str, result_type, parsed_data, image_base64
        except Exception as e:
            return f"Error: {e}", None, None, None

    async def chat(self, user_message: str) -> AsyncGenerator[AgentEvent, None]:
        """
        Process user message and yield events (streaming).

        Yields:
            AgentEvent(type="tool_start") - tool is being called
            AgentEvent(type="tool_result") - tool finished with result
            AgentEvent(type="text") - streaming text chunk (one per chunk)
        """
        # self._trim_messages()  # TODO: fix trim logic for tool messages
        self.messages.append({"role": "user", "content": user_message})

        while True:
            # Streaming call
            stream = await self.openai.chat.completions.create(
                model=self.model,
                messages=self.messages,
                tools=self.tools_cache or None,
                stream=True,
                temperature=0,  # Deterministic output for strict instruction following
            )

            # Collect streamed content
            full_content = ""
            tool_calls_map: dict[int, dict] = {}  # index -> {id, name, arguments}

            async for chunk in stream:
                delta = chunk.choices[0].delta

                # Stream text content immediately
                if delta.content:
                    full_content += delta.content
                    yield AgentEvent(type="text", content=delta.content)

                # Collect tool calls (need to reassemble from chunks)
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_map:
                            tool_calls_map[idx] = {"id": "", "name": "", "arguments": ""}
                        if tc.id:
                            tool_calls_map[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_calls_map[idx]["name"] = tc.function.name
                            if tc.function.arguments:
                                tool_calls_map[idx]["arguments"] += tc.function.arguments

            # Handle tool calls if any
            if tool_calls_map:
                # Build tool_calls list for messages
                tool_calls_list = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": tc["arguments"]}
                    }
                    for tc in tool_calls_map.values()
                ]
                self.messages.append({
                    "role": "assistant",
                    "content": full_content or None,
                    "tool_calls": tool_calls_list
                })

                # Execute each tool
                for tc in tool_calls_map.values():
                    name = tc["name"]
                    args = json.loads(tc["arguments"])

                    yield AgentEvent(type="tool_start", tool_name=name, tool_args=args)

                    result_str, result_type, parsed_data, image_base64 = await self._call_tool(name, args)

                    # Add image_base64 to parsed_data for frontend rendering
                    if parsed_data and image_base64:
                        parsed_data["image_base64"] = image_base64

                    yield AgentEvent(
                        type="tool_result",
                        content=result_str,
                        tool_name=name,
                        tool_args=args,
                        result_type=result_type,
                        parsed_data=parsed_data
                    )

                    # For chart results with image, send image to LLM for understanding
                    if result_type == "chart" and image_base64:
                        llm_content = (
                            f"[Chart rendered successfully: {parsed_data.get('title', 'Untitled')}]\n"
                            "The interactive chart is already visible to the user above. "
                            "Describe the key patterns or insights from this visualization in plain text. "
                            "NEVER use markdown image syntax like ![...](...) in your response."
                        )
                    elif result_type == "table" and parsed_data:
                        row_count = parsed_data.get("row_count", len(parsed_data.get("rows", [])))
                        llm_content = f"[Table displayed: {parsed_data.get('title', 'Data')} - {row_count} rows]"
                    else:
                        llm_content = result_str

                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": llm_content,  # For LLM (image or summary)
                        # Full data for UI rendering (OpenAI ignores extra fields)
                        "tool_name": name,
                        "tool_args": args,
                        "result_type": result_type,
                        "parsed_data": parsed_data  # Contains data + image_base64 for frontend
                    })

                    # Add instruction for RAG tool results
                    if name == "search_pangenome_literature":
                        self.messages.append({
                            "role": "system",
                            "content": (
                                "INSTRUCTION: Answer the user's question based ONLY on the documents above. "
                                "Do NOT use your own knowledge. Summarize key points and cite sources with titles/URLs. "
                                "If the documents don't contain relevant information, say 'I don't have information about this in my knowledge base.'"
                            )
                        })
                continue

            # No tool calls - save content and done
            if full_content:
                self.messages.append({"role": "assistant", "content": full_content})
            break