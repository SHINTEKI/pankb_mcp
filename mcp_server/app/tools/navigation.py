"""
URL Navigation Tools for PanKB MCP Server

Generate direct links to PanKB website pages based on data queries.
"""
import json

from fastmcp import FastMCP

mcp = FastMCP(name="NavigationTools")

# Base URL for PanKB website
PANKB_BASE_URL = "https://pankb.org"


def make_url_response(title: str, url: str, description: str = "") -> str:
    """Create a standardized URL response"""
    response = {
        "type": "url",
        "title": title,
        "url": url,
        "description": description
    }
    return json.dumps(response)


@mcp.tool()
def get_family_url(family: str) -> str:
    """
    Get the PanKB website URL for a specific microbial family.

    Args:
        family: Family name (e.g., 'Enterobacteriaceae', 'Bacillaceae')

    Returns:
        URL to the family page on pankb.org
    """
    url = f"{PANKB_BASE_URL}/organisms/?family={family}"
    return make_url_response(
        title=f"Family: {family}",
        url=url,
        description=f"View all species in the {family} family"
    )


@mcp.tool()
def get_species_url(
    species: str,
    section: str = "overview"
) -> str:
    """
    Get the PanKB website URL for a species pangenome analysis.
    Default section is 'overview' if user doesn't specify what information they want.

    Available sections:
    - 'overview': Pangenome overview with gene class distribution (core/shell/cloud) and statistics
    - 'gene_annotation': Gene annotation table with functional information and COG categories
    - 'genome': Genome list with metadata, GC content, and isolation info
    - 'phylogenetic_tree': Phylogenetic tree visualization with strain relationships

    Args:
        species: Species/pangenome analysis name (e.g., 'Escherichia_coli', 'Bacillus_subtilis')
        section: Page section (default: 'overview')

    Returns:
        URL to the species page on pankb.org
    """
    # Normalize species name: replace spaces with underscores
    species = species.replace(" ", "_")

    valid_sections = ["overview", "gene_annotation", "genome", "phylogenetic_tree"]
    if section not in valid_sections:
        section = "overview"

    url = f"{PANKB_BASE_URL}/pangenome_analyses/{section}/?species={species}"

    section_descriptions = {
        "overview": "Pangenome overview with gene class distribution and statistics",
        "gene_annotation": "Gene annotation table with functional information",
        "genome": "Genome list with metadata and isolation info",
        "phylogenetic_tree": "Phylogenetic tree visualization"
    }

    return make_url_response(
        title=f"Species: {species.replace('_', ' ')} - {section.replace('_', ' ').title()}",
        url=url,
        description=section_descriptions.get(section, "")
    )


@mcp.tool()
def get_genome_url(genome_id: str) -> str:
    """
    Get the PanKB website URL for a specific genome's detail page.
    Use this when user wants to see detailed information about a single genome.

    Args:
        genome_id: Specific genome ID (e.g., 'GCF_000009045.1')

    Returns:
        URL to the genome detail page on pankb.org
    """
    url = f"{PANKB_BASE_URL}/gene_function/genome_info/?genome_id={genome_id}"
    return make_url_response(
        title=f"Genome: {genome_id}",
        url=url,
        description=f"Detailed information for genome {genome_id}"
    )


# @mcp.tool()
# def get_genome_gene_url(genome_id: str, gene: str) -> str:
#     """
#     Get the PanKB website URL for a specific gene within a specific genome.
#     Use this when user specifies BOTH genome ID and gene name.

#     Args:
#         genome_id: Specific genome ID (e.g., 'GCF_040629865.1')
#         gene: Gene name (e.g., 'COQ3_3', 'dnaA')

#     Returns:
#         URL to the genome-gene detail page on pankb.org
#     """
#     url = f"{PANKB_BASE_URL}/gene_function/genome_gene_info/?genome_id={genome_id}&gene={gene}"
#     return make_url_response(
#         title=f"Gene: {gene} in Genome: {genome_id}",
#         url=url,
#         description=f"Detailed information for gene {gene} in genome {genome_id}"
#     )
    
    
@mcp.tool()
def get_gene_url_with_species_specified(species: str, gene: str) -> str:
    """
    Get the PanKB website URL for a specific gene in a specific species.
    ONLY use this when user EXPLICITLY specifies BOTH species and gene name in their request.

    Args:
        species: Species/pangenome analysis name (e.g., 'Bacillus_subtilis', 'Escherichia_coli')
        gene: Gene name (e.g., 'BH0395', 'dnaA')

    Returns:
        URL to the gene detail page on pankb.org
    """
    # Normalize species name: replace spaces with underscores
    species = species.replace(" ", "_")
    url = f"{PANKB_BASE_URL}/gene_function/gene_info/?species={species}&gene={gene}"
    return make_url_response(
        title=f"Gene: {gene} ({species.replace('_', ' ')})",
        url=url,
        description=f"Detailed information for gene {gene} in {species.replace('_', ' ')}"
    )


@mcp.tool()
def get_gene_url_with_species_unspecified(gene: str, limit: int = 100) -> str:
    """
    Search for a gene across all species and return URLs for each.
    Use this when user ONLY provides gene name WITHOUT explicitly specifying species.
    DO NOT guess or infer species from conversation context - if user didn't explicitly
    say the species name, use this tool to show them all available options.

    Args:
        gene: Gene name (e.g., 'BH0395', 'dnaA', 'COQ5_1')
        limit: Maximum number of species to return (default: 100)

    Returns:
        Table with species names and clickable URLs for user to choose from
    """
    from app.config import Config
    from app.utils.connections import mongo_client

    collection = mongo_client.get_collection(Config.MONGODB_COLLECTIONS["gene_annotations"])

    # Find all species that have this gene
    results = list(collection.find(
        {"gene": gene},
        {"species": 1, "pangenome_analysis": 1, "_id": 0}
    ).limit(limit * 2))  # Fetch extra to handle duplicates

    if not results:
        return json.dumps({
            "type": "string",
            "content": f"Gene '{gene}' not found in PanKB database.",
            "format": "text"
        })

    # Build table with species and URLs (deduplicated)
    rows = []
    seen_species = set()
    for r in results:
        if len(rows) >= limit:
            break
        species = r.get("pangenome_analysis") or r.get("species", "").replace(" ", "_")
        if species and species not in seen_species:
            seen_species.add(species)
            url = f"{PANKB_BASE_URL}/gene_function/gene_info/?species={species}&gene={gene}"
            rows.append({
                "species": species.replace("_", " "),
                "url": url
            })

    return json.dumps({
        "type": "table",
        "title": f"Gene: {gene}",
        "columns": ["species", "url"],
        "rows": rows,
        "summary": f"Found {gene} in {len(rows)} species. Click a URL to view gene details.",
        "row_count": len(rows)
    })


@mcp.tool()
def get_search_url(query: str) -> str:
    """
    Get the PanKB website search URL for a query.
    Searches across: Families, Species, Pathways, Genomes, and Genes.
    Note: Does NOT search publications - use get_publication_url for literature.

    Args:
        query: Search term (gene name, species name, pathway, protein function, etc.)

    Returns:
        URL to the search results page on pankb.org
    """
    # Replace spaces with + for URL
    encoded_query = query.replace(" ", "+")
    url = f"{PANKB_BASE_URL}/search/?q={encoded_query}"
    return make_url_response(
        title=f"Search: {query}",
        url=url,
        description=f"Search PanKB data (families, species, pathways, genomes, genes) for '{query}'"
    )


