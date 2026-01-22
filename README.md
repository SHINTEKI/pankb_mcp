## Project Background
PanKB is a comprehensive pangenome knowledge base containing rich datasets across genes, genomes, species and families. However, users currently can only access pre-built analyses through the web frontend, limiting the custom exploration access.   
        
To address this, we developed an MCP (Model Context Protocol) server that exposes PanKB's live data to external AI clients. This enables:     
- **Flexible data access**: Users can connect their own MCP-compatible clients (Claude Desktop, ChatGPT, etc.) or use our hosted Streamlit interface on PanKB website.   
- **Natural language interaction**: With LLM assistance, users can query and analyze pangenomic data through plain language.     
- **Real-time results**: Direct connection to PanKB database ensures up-to-date information.    



## MCP System Architecture
![MCP](docs/mcp.svg)

## Pankb Overall Architecture
![Pankb](docs/architecture.svg)

## Tools

### Query Tools
| Tool | Description |
|------|-------------|
| `query_families` | Query microbial families with species count and genome statistics |
| `query_species` | Search species/pangenomes with Core/Accessory/Rare gene distribution |
| `query_genomes` | Find genomes by species, country, or isolation source |
| `query_genes` | Search genes by name, function, COG category, or pangenomic class |
| `query_pathways` | Search KEGG pathways by ID or name |
| `query_stats` | Get database statistics (summary, by family, or by country) |

### Visualization Tools
| Tool | Description |
|------|-------------|
| `plot_gene_frequency_histogram` | Gene frequency U-shaped curve for a species |
| `plot_pangenome_class_distribution` | Core/Accessory/Rare pie chart |
| `plot_cog_category_distribution` | COG functional category bar chart |
| `plot_species_comparison` | Compare pangenome composition across species in a family |
| `plot_genome_count_by_family` | Genome counts by family or species |
| `plot_gc_content_distribution` | GC content histogram for a species |
| `plot_geographic_distribution` | Geographic distribution of genomes by country |
| `plot_isolation_source_distribution` | Isolation source pie chart |
| `plot_phylogroup_distribution` | Phylogroup distribution bar chart |
| `plot_pangenome_openness` | Open/Closed pangenome status comparison |
| `plot_phylon_heatmap` | Phylon weight heatmap for genomes |

### RAG Tools
| Tool | Description |
|------|-------------|
| `search_pangenome_literature` | Search scientific literature about microbial pangenomics using RAG (VoyageAI embedding + Cohere reranking) |



## Connection 
1. https://pankb.org/mcp/ (localhost for developer to do testing)
2. claude_desktop_config.json ()


## Roadmap

- [x] initialize codebase, use uv for env control, follow microservice structure to separate server and client apps into two directories, but track them using one repo 
- [x] write tools based on research papers, design tool categories
- [x] reuse previous RAG and add to tools
- [ ] design and write resources (optional)
- [x] design and write prompts 
- [x] write server app using FastMCP and uvicorn (to enable hot-reload for development), mount all server-side components
- [x] write client app, initiate client instance, import openai llm, write interaction loop between user, client, server and llm
- [x] write streamlit app, create session state to store conversation within sessions, design welcome messages to guide usage
- [x] write dockerfiles to containerize server and client, write docker-compose to orchestrate
- [ ] add logs for both server and client apps
- [x] add CI/CD workflows and use self-hosted runner
- [x] design authorization methods, user-client (OpenID Connect), server-client
- [ ] design a panel on the streamlit front page to display past conversations and available tools 
- [x] build a SQL database to store user info, token usage and past conversations 
- [ ] apply for a certificate from Let's Encrypt and use nginx for reverse proxy, connect to prod server and publish to MCP server registry
- [x] add export function for PNG/SVG and CSV
- [ ] set up a monitoring and alerting system 