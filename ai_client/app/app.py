"""
Streamlit Chat App with MCP Tools
"""
import os
import uuid
import asyncio
import streamlit as st
from mcp_client_stream import MCPClient, AgentEvent
from fastmcp.client.auth import BearerAuth
from dotenv import load_dotenv
from db import get_or_create_user, save_chat_message
from render import render_tool_call, render_tool_request, render_tool_response

load_dotenv()

# Configuration
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL")
MCP_API_KEY = os.getenv("MCP_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL = os.getenv("OPENAI_MODEL")
SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT")

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

if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = str(uuid.uuid4())

# Sidebar
with st.sidebar:
    st.markdown(f"**Welcome, {st.user.name}!**")
    st.caption(f"Email: {st.user.email}")
    st.button("Log out", on_click=st.logout)

# Initialize session state with messages and MCP client
if "messages" not in st.session_state:
    st.session_state.messages = []

if "client" not in st.session_state:
    st.session_state.client = None
    st.session_state.connected = False

async def init_client():
    """Initialize and connect MCP client"""
    client = MCPClient(
        mcp_server_url=MCP_SERVER_URL,
        openai_api_key=OPENAI_API_KEY,
        model=MODEL,
        auth=BearerAuth(token=MCP_API_KEY),
        system_prompt=SYSTEM_PROMPT
    )
    await client.connect()
    return client

# Main interface
st.title("🧬 PanKB AI Assistant")

# Connect to MCP Server
if not st.session_state.connected:
    try:
        st.session_state.client = asyncio.run(init_client())
        st.session_state.connected = True
        st.rerun()
    except Exception as e:
        st.error(f"Failed to connect to MCP Server: {str(e)}")
        st.stop()

# Welcome message
if not st.session_state.messages:
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

# Display conversation history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        for tc in message.get("tool_calls", []):
            render_tool_call(
                name=tc["name"],
                arguments=tc["arguments"],
                result=tc["result"],
                result_type=tc.get("result_type"),
                parsed_data=tc.get("parsed_data")
            )
        if message["content"]:
            st.markdown(message["content"])

# Process chat with streaming updates
async def process_chat(client: MCPClient, user_prompt: str, text_placeholder, tool_container):
    """Process chat and update UI. Returns (llm_text, tool_calls)"""
    llm_text = ""
    tool_calls = []

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

    return llm_text, tool_calls


# User input
if prompt := st.chat_input("What species are in PanKB?"):
    st.session_state.messages.append({"role": "user", "content": prompt, "tool_calls": []})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Save user message
    if st.session_state.db_user:
        try:
            save_chat_message(
                user_id=st.session_state.db_user["id"],
                role="user",
                content=prompt,
                conversation_id=st.session_state.conversation_id
            )
        except Exception:
            pass

    # Get AI response
    with st.chat_message("assistant"):
        tool_container = st.container()
        text_placeholder = st.empty()

        llm_text, tool_calls = asyncio.run(
            process_chat(
                st.session_state.client,
                prompt,
                text_placeholder,
                tool_container
            )
        )

        text_placeholder.markdown(llm_text)

        st.session_state.messages.append({
            "role": "assistant",
            "content": llm_text,
            "tool_calls": tool_calls
        })

        # Save to database
        if st.session_state.db_user:
            try:
                save_chat_message(
                    user_id=st.session_state.db_user["id"],
                    role="assistant",
                    content=llm_text,
                    conversation_id=st.session_state.conversation_id
                )
            except Exception:
                pass

    st.rerun()
