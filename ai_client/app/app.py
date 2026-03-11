"""
Streamlit Chat App with MCP Tools
"""
import asyncio
import json
import os
import uuid
from pathlib import Path

import streamlit as st
from openai import AsyncOpenAI, OpenAI
from db import (
    generate_conversation_title,
    get_conversation,
    get_or_create_user,
    get_user_conversations,
    record_token_usage,
    save_conversation,
)
from dotenv import load_dotenv
from fastmcp.client.auth import BearerAuth
from mcp_client_stream import AgentEvent, MCPClient
from render import render_tool_call, render_tool_request, render_tool_response

load_dotenv(Path(__file__).parent.parent / ".env")

# Configuration
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL")
MCP_API_KEY = os.getenv("MCP_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL = os.getenv("OPENAI_MODEL")
SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT")


@st.cache_resource
def get_async_openai_client() -> AsyncOpenAI:
    """Get cached AsyncOpenAI client (shared across all sessions)"""
    return AsyncOpenAI(api_key=OPENAI_API_KEY)


@st.cache_resource
def get_sync_openai_client() -> OpenAI:
    """Get cached sync OpenAI client for title generation (shared across all sessions)"""
    return OpenAI(api_key=OPENAI_API_KEY)

# Page configuration
st.set_page_config(
    page_title="PanKB AI Assistant",
    page_icon="🧬",
    layout="wide"
)

# OpenID Connect 
if not st.user.is_logged_in:
    st.title("🧬 PanKB AI Assistant")
    st.markdown("Please log in to enjoy better service.")
    st.button("Log in with Google", on_click=st.login, args=["google"])
    st.stop()

# User database setup; implement when user logs in 
if "db_user" not in st.session_state:
    try:
        st.session_state.db_user = get_or_create_user(
            oauth_provider="google",
            email=st.user.email,
            display_name=st.user.name,
            avatar_url=getattr(st.user, 'picture', None)
        )
    except Exception as e:
        st.error(f"Database connection error: {str(e)}")
        st.session_state.db_user = None

# Initialize session state with MCP client
if "client" not in st.session_state:
    st.session_state.client = None
    st.session_state.connected = False

async def init_client():
    """Initialize and connect MCP client"""
    client = MCPClient(
        mcp_server_url=MCP_SERVER_URL,
        openai_client=get_async_openai_client(),
        model=MODEL,
        auth=BearerAuth(token=MCP_API_KEY),
        system_prompt=SYSTEM_PROMPT
    )
    await client.connect()
    return client
    
# Connect to MCP Server
if not st.session_state.connected:
    try:
        st.session_state.client = asyncio.run(init_client()) # MCPClient instance
        st.session_state.connected = True
        st.rerun()
    except Exception as e:
        st.error(f"Failed to connect to MCP Server: {str(e)}")
        st.stop()

if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = str(uuid.uuid4())
    
# Main interface
st.title("🧬 PanKB AI Assistant")
     
# Sidebar
with st.sidebar:
    st.markdown(f"**Welcome, {st.user.name}!**")
    st.caption(f"Email: {st.user.email}")
    st.button("Log out", on_click=st.logout)
    st.toggle("📚 Search Literature", key="literature_mode", help="Answer questions based on pangenome research papers")

    st.divider()

    # New chat button
    if st.button("+ New Chat", width="stretch"):
        st.session_state.conversation_id = str(uuid.uuid4())
        st.session_state.client.clear_history() # 看这一页会怎么重新渲染
        st.rerun()

    # Conversation history list
    if st.session_state.db_user: # Could be None if DB connection error
        conversations = get_user_conversations(st.session_state.db_user["id"], limit=10)
        if conversations:
            st.markdown("**Recent Chats**")
            for conv in conversations:
                conv_id = str(conv["conversation_id"])
                title = conv["title"] or "Untitled"
                is_current = conv_id == st.session_state.conversation_id

                if st.button(
                    f"{'▶ ' if is_current else ''}{title}",
                    key=f"conv_{conv_id}",
                    width="stretch",
                    disabled=is_current
                ):
                    # Switch to this conversation
                    st.session_state.conversation_id = conv_id
                    # Load conversation messages into client
                    conv_data = get_conversation(conv_id)
                    if conv_data and st.session_state.client: 
                        st.session_state.client.messages = conv_data["messages"]
                    st.rerun()

# Helper: check if conversation has started
def has_conversation():
    if not st.session_state.client:
        return False
    return any(m["role"] == "user" for m in st.session_state.client.messages)

# Welcome message (only show if no conversation yet)
if not has_conversation():
    st.markdown("I can help you explore PanKB's pangenomic data. Here are the available tools:")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
**🔍 Query Tools**
| Tool | Description |
|------|-------------|
| `query_families` | List microbial families |
| `query_species` | Search species/pangenomes |
| `query_genomes` | Find genomes by species/country |
| `query_genes` | Search genes by name/function |
| `query_pathways` | Search KEGG pathways |
| `query_stats` | Database statistics |
        """)
    with col2:
        st.markdown("""
**📈 Visualization Tools**
| Tool | Description |
|------|-------------|
| `plot_gene_frequency_histogram` | U-shaped gene frequency curve |
| `plot_pangenome_class_distribution` | Core/Accessory/Rare pie chart |
| `plot_cog_category_distribution` | COG functional categories |
| `plot_species_comparison` | Compare species in a family |
| `plot_genome_count_by_family` | Genome counts bar chart |
| `plot_gc_content_distribution` | GC content histogram |
| `plot_geographic_distribution` | Genome locations by country |
| `plot_isolation_source_distribution` | Sample sources pie chart |
| `plot_phylogroup_distribution` | Phylogroup bar chart |
| `plot_pangenome_openness` | Open/Closed pangenome status |
| `plot_heaps_law` | Pangenome growth curve |
| `plot_dn_ds_ratio` | Selection pressure distribution |
        """)

    st.markdown("---")

# Display conversation history from client.messages
def render_conversation_history():
    """Render conversation from client.messages"""
    messages = st.session_state.client.messages
    i = 0
    while i < len(messages):
        msg = messages[i]

        # Skip: system messages, Responses API internal items
        if msg.get("role") == "system" or msg.get("type") in ("function_call", "function_call_output"):
            i += 1
            continue

        elif msg.get("role") == "user":
            with st.chat_message("user"):
                content = msg["content"]
                if content.startswith("[search_pangenome_literature] "):
                    content = content[len("[search_pangenome_literature] "):]
                st.markdown(content)
            i += 1

        elif msg.get("role") == "tool":
            with st.chat_message("assistant"):
                render_tool_call(
                    name=msg["tool_name"],
                    arguments=msg["tool_args"],
                    result=msg.get("content", ""),
                    result_type=msg.get("result_type"),
                    parsed_data=msg.get("parsed_data")
                )
                # Check if next message is assistant response (render together)
                if i + 1 < len(messages) and messages[i + 1].get("role") == "assistant":
                    st.markdown(messages[i + 1].get("content"))
                    i += 1
            i += 1

        else:  # assistant
            # Skip if already rendered with previous tool message
            if i > 0 and messages[i - 1].get("role") == "tool":
                i += 1
                continue
            with st.chat_message("assistant"):
                st.markdown(msg.get("content", ""))
            i += 1



render_conversation_history()

# Process chat with streaming updates
async def process_chat(client: MCPClient, user_prompt: str, text_placeholder, tool_container):
    """Process chat and update UI. Returns (llm_text, tool_calls, usage)"""
    llm_text = ""
    tool_calls = []
    usage = None

    async for event in client.chat(user_prompt):
        if event.type == "tool_start":
            with tool_container:
                render_tool_request(event.tool_name, event.tool_args)

        elif event.type == "tool_result":
            tool_calls.append({
                "name": event.tool_name,
                "arguments": event.tool_args,
                "result": event.content,
                "result_type": event.result_type,
                "parsed_data": event.parsed_data
            })
            with tool_container:
                render_tool_response(
                    name=event.tool_name,
                    result=event.content,
                    result_type=event.result_type,
                    parsed_data=event.parsed_data
                )

        elif event.type == "text":
            llm_text += event.content
            text_placeholder.markdown(llm_text + "▌")

        elif event.type == "usage":
            usage = {"tokens_in": event.tokens_in, "tokens_out": event.tokens_out}

    return llm_text, tool_calls, usage


# User input
if prompt := st.chat_input("What species are included PanKB?"):
    display_prompt = prompt  # What user sees
    if st.session_state.get("literature_mode", False):
        user_prompt = f"[search_pangenome_literature] {prompt}"
    else:
        user_prompt = prompt

    # Display user message 
    with st.chat_message("user"):
        st.markdown(display_prompt)

    # Get AI response
    with st.chat_message("assistant"):
        tool_container = st.container()
        text_placeholder = st.empty()

        llm_text, tool_calls, usage = asyncio.run(
            process_chat(
                st.session_state.client,
                user_prompt,
                text_placeholder,
                tool_container
            )
        )

        text_placeholder.markdown(llm_text)

    # Save conversation and record token usage
    if st.session_state.db_user and st.session_state.client:
        try:
            save_conversation(
                user_id=st.session_state.db_user["id"],
                conversation_id=st.session_state.conversation_id,
                messages=st.session_state.client.messages,
                openai_client=get_sync_openai_client()
            )
            # Record token usage if available
            if usage:
                record_token_usage(
                    user_id=st.session_state.db_user["id"],
                    tokens_in=usage["tokens_in"],
                    tokens_out=usage["tokens_out"],
                    model=MODEL,
                    conversation_id=st.session_state.conversation_id
                )
        except Exception:
            pass

    st.rerun()
