"""
Prompts: Preset prompt templates
"""
from fastmcp import FastMCP

mcp = FastMCP(name="PromptTemplates")

# Right now OpenAI doesn't support prompt templates, so we define system prompt from the client side