import logging
import os

from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.server.auth import StaticTokenVerifier
from fastmcp.utilities.logging import configure_logging

load_dotenv()

# Configure logging: FastMCP's RichHandler for console + FileHandler for file
configure_logging(level="INFO")

# Add file handler for persistent logs
os.makedirs('logs', exist_ok=True)
file_handler = logging.FileHandler('logs/mcp_server.log')
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(file_handler)

# Silence noisy third-party modules
for module in ['mcp', 'httpx', 'httpcore', 'matplotlib', 'pymongo', 'azure', 'fakeredis', 'docket']:
    logging.getLogger(module).setLevel(logging.WARNING)

from app.prompts.templates import mcp as templates_mcp
from app.resources.data import mcp as data_mcp
from app.tools.analysis import mcp as analysis_mcp

# Import mcp instances from each module
from app.tools.chart import mcp as chart_mcp
from app.tools.query import mcp as query_mcp
from app.tools.rag import mcp as rag_mcp

# Bearer Token authentication for internal service communication
# MCP_API_KEY is used by the Streamlit client to authenticate
MCP_API_KEY = os.getenv("MCP_API_KEY", "")

# Create token verifier with the API key
# The token maps to client metadata (client_id, scopes)
token_auth = StaticTokenVerifier(
    tokens={
        MCP_API_KEY: {
            "client_id": "streamlit-client",
            "scopes": ["read", "write"],
        }
    }
)

logger = logging.getLogger(__name__)

# Main server
mcp = FastMCP(
    name="PanKB-MCP",
    instructions="PanKB MCP Server - Provides genomic data query, analysis, visualization and RAG capabilities",
    auth=token_auth,
)

# Mount sub-servers
mcp.mount(chart_mcp)
mcp.mount(analysis_mcp)
mcp.mount(query_mcp)
mcp.mount(rag_mcp) 
mcp.mount(data_mcp)
mcp.mount(templates_mcp)


# Create HTTP app (module level, supports uvicorn --reload)
app = mcp.http_app()


if __name__ == "__main__":
    import uvicorn
    if MCP_API_KEY:
        logger.info("Starting server with Bearer token authentication")
    else:
        logger.warning("MCP_API_KEY not set - authentication will fail")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
