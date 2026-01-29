"""
MCP Client: Connect to MCP Server, convert tools to OpenAI function calling format, and handle streaming chat with tool calls.
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
        openai_client: AsyncOpenAI,
        model: str = "gpt-4o-mini",
        auth=None,
        system_prompt: str | None = None,
    ):
        if not mcp_server_url:
            raise ValueError("mcp_server_url is required")
        if not openai_client:
            raise ValueError("openai_client is required")
        if not auth:
            raise ValueError("auth is required (use BearerAuth)")

        self.mcp_server_url = mcp_server_url
        self.model = model
        self.auth = auth
        self.openai = openai_client
        self.tools_cache: list[dict] = []
        self.messages: list[dict] = []
        self.system_prompt = system_prompt 

    def _create_mcp_client(self) -> Client:
        return Client(self.mcp_server_url, auth=self.auth)

    def clear_history(self):
        """Clear conversation history"""
        self.messages = []

    async def connect(self):
        """Connect to MCP Server and fetch tools"""
        async with self._create_mcp_client() as client:
            mcp_tools = await client.list_tools()
            self.tools_cache = [
                {
                    "type": "function",
                    "name": t.name,
                    "description": t.description or "",
                    "parameters": t.inputSchema or {"type": "object", "properties": {}},
                    "strict": False,
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
        """
        try:
            async with self._create_mcp_client() as client:
                result = await client.call_tool(name, args)

                result_str = ""
                image_base64 = None
                result_type = None
                parsed_data = None

                for content in result.content:
                    if hasattr(content, "text"):
                        result_str = content.text
                        result_type, parsed_data = self._parse_result(result_str)
                    elif hasattr(content, "data") and hasattr(content, "mimeType"):
                        if content.mimeType.startswith("image/"):
                            image_base64 = content.data

                return result_str, result_type, parsed_data, image_base64
        except Exception as e:
            return f"Error: {e}", None, None, None

    async def chat(self, user_message: str) -> AsyncGenerator[AgentEvent, None]:
        """
        Process user message and yield events (streaming).
        Using OpenAI Responses API.

        Yields:
            AgentEvent(type="tool_start") - tool is being called
            AgentEvent(type="tool_result") - tool finished with result
            AgentEvent(type="text") - streaming text chunk (one per chunk)
        """
        # Add user message to input
        self.messages.append({"role": "user", "content": user_message})

        while True:
            # Filter messages to only include valid API items
            api_input = self._filter_messages_for_api()

            # Streaming call using Responses API
            stream = await self.openai.responses.create(
                model=self.model,
                input=api_input,
                instructions=self.system_prompt,
                tools=self.tools_cache or None,
                store= False,
                stream=True,
                temperature=0,  # Deterministic output for strict instruction following
            )

            # Collect streamed content and final response
            full_content = ""
            function_calls: list[dict] = []

            async for event in stream:
                # Handle text output deltas (for streaming display)
                if event.type == "response.output_text.delta":
                    full_content += event.delta
                    yield AgentEvent(type="text", content=event.delta)

                # Handle tool call output - extract complete function calls
                elif event.type == "response.output_item.done":
                    if hasattr(event.item, "type") and event.item.type == "function_call":
                        function_calls.append({
                            "call_id": event.item.call_id,
                            "name": event.item.name,
                            "arguments": event.item.arguments
                        })

            # Handle function calls if any
            if function_calls:
                # Add function_call items to messages for next API call
                for fc in function_calls:
                    self.messages.append({
                        "type": "function_call",
                        "call_id": fc["call_id"],
                        "name": fc["name"],
                        "arguments": fc["arguments"]
                    })

                # Execute each function
                for fc in function_calls:
                    name = fc["name"]
                    args = json.loads(fc["arguments"]) if fc["arguments"] else {}

                    yield AgentEvent(type="tool_start", tool_name=name, tool_args=args)

                    result_str, result_type, parsed_data, image_base64 = await self._call_tool(name, args)

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

                    # Prepare content for LLM
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

                    # Add function_call_output to messages (Responses API format)
                    self.messages.append({
                        "type": "function_call_output",
                        "call_id": fc["call_id"],
                        "output": llm_content
                    })

                    # Store extra data for UI rendering (we'll need this for history)
                    # Add a marker message for UI (will be filtered when sending to API)
                    self.messages.append({
                        "role": "tool",  # Marker for UI rendering
                        "tool_call_id": fc["call_id"],
                        "content": llm_content,
                        "tool_name": name,
                        "tool_args": args,
                        "result_type": result_type,
                        "parsed_data": parsed_data
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

            # No function calls - save content and done
            if full_content:
                self.messages.append({"role": "assistant", "content": full_content})
            break

    def _filter_messages_for_api(self) -> list[dict]:
        """
        Filter messages to only include items valid for Responses API input.
        Removes UI-only marker messages (role="tool").
        """
        valid_items = []
        for msg in self.messages:
            # Skip UI-only tool marker messages
            if msg.get("role") == "tool":
                continue
            # Responses API items: function_call, function_call_output
            if msg.get("type") in ("function_call", "function_call_output"):
                valid_items.append(msg)
            # Standard message format: user, assistant, system
            elif msg.get("role") in ("user", "assistant", "system"):
                valid_items.append(msg)
        return valid_items
