"""
MCP Client: Connect to MCP Server, convert tools to OpenAI function calling format
(Streaming version)
"""
import json
from typing import AsyncGenerator
from dataclasses import dataclass
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

    async def _call_tool(self, name: str, args: dict) -> tuple[str, str | None, dict | None]:
        """Call MCP tool and return (result_str, result_type, parsed_data)"""
        try:
            async with self._create_mcp_client() as client:
                result = await client.call_tool(name, args)
                result_str = result.content[0].text if result.content else ""
                result_type, parsed_data = self._parse_result(result_str)
                return result_str, result_type, parsed_data
        except Exception as e:
            return f"Error: {e}", None, None

    async def chat(self, user_message: str) -> AsyncGenerator[AgentEvent, None]:
        """
        Process user message and yield events (streaming).

        Yields:
            AgentEvent(type="tool_start") - tool is being called
            AgentEvent(type="tool_result") - tool finished with result
            AgentEvent(type="text") - streaming text chunk (one per chunk)
        """
        self.messages.append({"role": "user", "content": user_message})

        while True:
            # Streaming call
            stream = await self.openai.chat.completions.create(
                model=self.model,
                messages=self.messages,
                tools=self.tools_cache or None,
                stream=True,
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

                    result_str, result_type, parsed_data = await self._call_tool(name, args)

                    yield AgentEvent(
                        type="tool_result",
                        content=result_str,
                        tool_name=name,
                        tool_args=args,
                        result_type=result_type,
                        parsed_data=parsed_data
                    )

                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result_str
                    })
                continue

            # No tool calls - save content and done
            if full_content:
                self.messages.append({"role": "assistant", "content": full_content})
            break
