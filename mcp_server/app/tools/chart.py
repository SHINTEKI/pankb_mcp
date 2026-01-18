"""
Visualization Tools for PanKB MCP Server

These tools return Plotly-compatible JSON data for interactive chart rendering.
"""
from typing import Optional
import json
import logging

from fastmcp import FastMCP

from app.config import Config
from app.utils.connections import mongo_client

logger = logging.getLogger(__name__)

# Color schemes
PANGENOME_COLORS = {'Core': '#2ecc71', 'Accessory': '#f39c12', 'Rare': '#e74c3c'}

COG_NAMES = {
    'J': 'Translation', 'A': 'RNA processing', 'K': 'Transcription',
    'L': 'Replication', 'B': 'Chromatin', 'D': 'Cell cycle',
    'Y': 'Nuclear structure', 'V': 'Defense', 'T': 'Signal transduction',
    'M': 'Cell wall', 'N': 'Cell motility', 'Z': 'Cytoskeleton',
    'W': 'Extracellular', 'U': 'Secretion', 'O': 'PTM/chaperones',
    'C': 'Energy production', 'G': 'Carbohydrate metabolism',
    'E': 'Amino acid metabolism', 'F': 'Nucleotide metabolism',
    'H': 'Coenzyme metabolism', 'I': 'Lipid metabolism',
    'P': 'Inorganic ion transport', 'Q': 'Secondary metabolites',
    'R': 'General function', 'S': 'Function unknown', '-': 'Not in COG'
}


def make_chart_response(chart_type: str, title: str, data: dict, layout: dict = None) -> str:
    """Create a standardized chart response in JSON format"""
    response = {
        "type": "chart",
        "chart_type": chart_type,
        "title": title,
        "data": data,
        "layout": layout or {}
    }
    return json.dumps(response)


mcp = FastMCP(name="ChartTools")


@mcp.tool()
def plot_gene_frequency_histogram(pangenome_analysis: str) -> str:
    """
    Generate gene frequency histogram (U-shape curve) for a species.
    Returns Plotly-compatible JSON data for interactive visualization.

    Args:
        pangenome_analysis: Species pangenome analysis name (e.g., 'Escherichia_coli')
    """
    collection = mongo_client.get_collection(Config.COLLECTIONS["gene_annotations"])

    pipeline = [
        {"$match": {"pangenome_analysis": pangenome_analysis}},
        {"$group": {"_id": "$frequency", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}}
    ]
    results = list(collection.aggregate(pipeline))

    if not results:
        return f"No data found for {pangenome_analysis}"

    frequencies = [r["_id"] for r in results]
    counts = [r["count"] for r in results]

    return make_chart_response(
        chart_type="bar",
        title=f"Gene Frequency Distribution - {pangenome_analysis.replace('_', ' ')}",
        data={
            "x": frequencies,
            "y": counts,
            "labels": {"x": "Gene Frequency (number of genomes)", "y": "Number of Genes"}
        },
        layout={
            "yaxis_type": "log",
            "bargap": 0,
            "color": "steelblue"
        }
    )


@mcp.tool()
def plot_pangenome_class_distribution(pangenome_analysis: str) -> str:
    """
    Generate pie chart showing Core/Accessory/Rare gene distribution for a species.
    Returns Plotly-compatible JSON data for interactive visualization.

    Args:
        pangenome_analysis: Species pangenome analysis name (e.g., 'Bacillus_subtilis')
    """
    collection = mongo_client.get_collection(Config.COLLECTIONS["gene_annotations"])

    pipeline = [
        {"$match": {"pangenome_analysis": pangenome_analysis}},
        {"$group": {"_id": "$pangenomic_class", "count": {"$sum": 1}}}
    ]
    results = list(collection.aggregate(pipeline))

    if not results:
        return f"No data found for {pangenome_analysis}"

    class_counts = {r["_id"]: r["count"] for r in results}
    labels = []
    values = []
    colors = []

    for cls in ['Core', 'Accessory', 'Rare']:
        if cls in class_counts:
            labels.append(cls)
            values.append(class_counts[cls])
            colors.append(PANGENOME_COLORS.get(cls, 'gray'))

    return make_chart_response(
        chart_type="pie",
        title=f"Pangenome Class Distribution - {pangenome_analysis.replace('_', ' ')}",
        data={
            "labels": labels,
            "values": values,
            "colors": colors
        },
        layout={}
    )


@mcp.tool()
def plot_cog_category_distribution(pangenome_analysis: str, top_n: int = 15) -> str:
    """
    Generate bar chart showing COG functional category distribution for a species.
    Returns Plotly-compatible JSON data for interactive visualization.

    Args:
        pangenome_analysis: Species pangenome analysis name
        top_n: Number of top categories to show (default: 15)
    """
    collection = mongo_client.get_collection(Config.COLLECTIONS["gene_annotations"])

    pipeline = [
        {"$match": {"pangenome_analysis": pangenome_analysis}},
        {"$group": {"_id": "$cog_category", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": top_n}
    ]
    results = list(collection.aggregate(pipeline))

    if not results:
        return f"No data found for {pangenome_analysis}"

    categories = [r["_id"] if r["_id"] else "-" for r in results]
    counts = [r["count"] for r in results]
    labels = [f"{cat}: {COG_NAMES.get(cat, 'Unknown')}" for cat in categories]

    return make_chart_response(
        chart_type="bar_horizontal",
        title=f"COG Category Distribution - {pangenome_analysis.replace('_', ' ')}",
        data={
            "x": counts,
            "y": labels,
            "labels": {"x": "Number of Genes", "y": "COG Category"}
        },
        layout={
            "color": "viridis"
        }
    )


@mcp.tool()
def plot_species_comparison(family: str, top_n: int = 10) -> str:
    """
    Generate stacked bar chart comparing Core/Accessory/Rare genes across species in a family.
    Returns Plotly-compatible JSON data for interactive visualization.

    Args:
        family: Family name to compare species (e.g., 'Bacillaceae')
        top_n: Number of top species to show (default: 10)
    """
    collection = mongo_client.get_collection(Config.COLLECTIONS["organisms"])

    results = list(collection.find(
        {"family": {"$regex": family, "$options": "i"}},
        {"species": 1, "gene_class_distribution": 1, "genomes_num": 1}
    ).sort("genomes_num", -1).limit(top_n))

    if not results:
        return f"No species found for family: {family}"

    species_names = []
    core_counts = []
    accessory_counts = []
    rare_counts = []

    for r in results:
        species_names.append(r.get("species", "Unknown").replace("_", " "))
        dist = r.get("gene_class_distribution", [0, 0, 0])
        if isinstance(dist, list) and len(dist) >= 3:
            core_counts.append(dist[0])
            accessory_counts.append(dist[1])
            rare_counts.append(dist[2])
        else:
            core_counts.append(0)
            accessory_counts.append(0)
            rare_counts.append(0)

    return make_chart_response(
        chart_type="bar_stacked",
        title=f"Pangenome Composition by Species - Family: {family}",
        data={
            "x": species_names,
            "series": [
                {"name": "Core", "values": core_counts, "color": PANGENOME_COLORS['Core']},
                {"name": "Accessory", "values": accessory_counts, "color": PANGENOME_COLORS['Accessory']},
                {"name": "Rare", "values": rare_counts, "color": PANGENOME_COLORS['Rare']}
            ],
            "labels": {"x": "Species", "y": "Number of Genes"}
        },
        layout={}
    )


@mcp.tool()
def plot_genome_count_by_family(family: Optional[str] = None, top_n: int = 15) -> str:
    """
    Generate bar chart showing genome counts across families or species.
    Returns Plotly-compatible JSON data for interactive visualization.

    Args:
        family: Optional: filter by family name to show species within
        top_n: Number of top entries to show (default: 15)
    """
    collection = mongo_client.get_collection(Config.COLLECTIONS["organisms"])

    if family:
        pipeline = [
            {"$match": {"family": {"$regex": family, "$options": "i"}}},
            {"$sort": {"genomes_num": -1}},
            {"$limit": top_n},
            {"$project": {"name": "$species", "count": "$genomes_num"}}
        ]
        title = f"Genome Count by Species - Family: {family}"
    else:
        pipeline = [
            {"$group": {"_id": "$family", "count": {"$sum": "$genomes_num"}}},
            {"$sort": {"count": -1}},
            {"$limit": top_n},
            {"$project": {"name": "$_id", "count": 1}}
        ]
        title = "Genome Count by Family"

    results = list(collection.aggregate(pipeline))

    if not results:
        return "No data found"

    names = [r.get("name", "Unknown").replace("_", " ") for r in results]
    counts = [r.get("count", 0) for r in results]

    return make_chart_response(
        chart_type="bar_horizontal",
        title=title,
        data={
            "x": counts,
            "y": names,
            "labels": {"x": "Number of Genomes", "y": ""}
        },
        layout={
            "color": "steelblue"
        }
    )


@mcp.tool()
def plot_gc_content_distribution(pangenome_analysis: str) -> str:
    """
    Generate histogram of GC content distribution for genomes in a species.
    Returns Plotly-compatible JSON data for interactive visualization.

    Args:
        pangenome_analysis: Species pangenome analysis name
    """
    collection = mongo_client.get_collection(Config.COLLECTIONS["genome_info"])

    results = list(collection.find(
        {"pangenome_analysis": pangenome_analysis},
        {"gc_content": 1}
    ))

    if not results:
        return f"No data found for {pangenome_analysis}"

    gc_values = [r.get("gc_content", 0) * 100 for r in results if r.get("gc_content")]

    if not gc_values:
        return f"No GC content data for {pangenome_analysis}"

    mean_gc = sum(gc_values) / len(gc_values)

    return make_chart_response(
        chart_type="histogram",
        title=f"GC Content Distribution - {pangenome_analysis.replace('_', ' ')}",
        data={
            "values": gc_values,
            "labels": {"x": "GC Content (%)", "y": "Number of Genomes"},
            "mean": mean_gc
        },
        layout={
            "nbins": 30,
            "color": "steelblue",
            "vline": {"x": mean_gc, "color": "red", "label": f"Mean: {mean_gc:.2f}%"}
        }
    )


@mcp.tool()
def plot_geographic_distribution(pangenome_analysis: Optional[str] = None, top_n: int = 20) -> str:
    """
    Generate bar chart showing geographic distribution of genomes by country.
    Returns Plotly-compatible JSON data for interactive visualization.

    Args:
        pangenome_analysis: Optional: filter by species pangenome analysis name
        top_n: Number of top countries to show (default: 20)
    """
    if pangenome_analysis:
        genome_collection = mongo_client.get_collection(Config.COLLECTIONS["genome_info"])
        pipeline = [
            {"$match": {"pangenome_analysis": pangenome_analysis}},
            {
                "$lookup": {
                    "from": Config.COLLECTIONS["isolation_info"],
                    "localField": "genome_id",
                    "foreignField": "genome_id",
                    "as": "isolation"
                }
            },
            {"$unwind": {"path": "$isolation", "preserveNullAndEmptyArrays": False}},
            {"$group": {"_id": "$isolation.country_standard", "count": {"$sum": 1}}},
            {"$match": {"_id": {"$ne": None, "$ne": "missing", "$ne": "Missing"}}},
            {"$sort": {"count": -1}},
            {"$limit": top_n}
        ]
        results = list(genome_collection.aggregate(pipeline))
        title = f"Geographic Distribution - {pangenome_analysis.replace('_', ' ')}"
    else:
        collection = mongo_client.get_collection(Config.COLLECTIONS["isolation_info"])
        pipeline = [
            {"$group": {"_id": "$country_standard", "count": {"$sum": 1}}},
            {"$match": {"_id": {"$ne": None, "$ne": "missing", "$ne": "Missing"}}},
            {"$sort": {"count": -1}},
            {"$limit": top_n}
        ]
        results = list(collection.aggregate(pipeline))
        title = "Geographic Distribution of Genomes"

    if not results:
        return "No geographic data found"

    countries = [r["_id"] if r["_id"] else "Unknown" for r in results]
    counts = [r["count"] for r in results]

    return make_chart_response(
        chart_type="bar_horizontal",
        title=title,
        data={
            "x": counts,
            "y": countries,
            "labels": {"x": "Number of Genomes", "y": "Country"}
        },
        layout={
            "color": "Blues"
        }
    )


@mcp.tool()
def plot_isolation_source_distribution(pangenome_analysis: Optional[str] = None, top_n: int = 10) -> str:
    """
    Generate pie chart showing distribution of isolation sources for genomes.
    Returns Plotly-compatible JSON data for interactive visualization.

    Args:
        pangenome_analysis: Optional: filter by species pangenome analysis name
        top_n: Number of top sources to show (default: 10)
    """
    if pangenome_analysis:
        genome_collection = mongo_client.get_collection(Config.COLLECTIONS["genome_info"])
        pipeline = [
            {"$match": {"pangenome_analysis": pangenome_analysis}},
            {
                "$lookup": {
                    "from": Config.COLLECTIONS["isolation_info"],
                    "localField": "genome_id",
                    "foreignField": "genome_id",
                    "as": "isolation"
                }
            },
            {"$unwind": {"path": "$isolation", "preserveNullAndEmptyArrays": False}},
            {"$group": {"_id": "$isolation.isolation_source", "count": {"$sum": 1}}},
            {"$match": {"_id": {"$nin": [None, "Missing", "missing", "", "-", "Not available", "not available"]}}},
            {"$sort": {"count": -1}},
            {"$limit": top_n}
        ]
        results = list(genome_collection.aggregate(pipeline))
        title = f"Isolation Source Distribution - {pangenome_analysis.replace('_', ' ')}"
    else:
        collection = mongo_client.get_collection(Config.COLLECTIONS["isolation_info"])
        pipeline = [
            {"$group": {"_id": "$isolation_source", "count": {"$sum": 1}}},
            {"$match": {"_id": {"$nin": [None, "Missing", "missing", "", "-", "Not available", "not available"]}}},
            {"$sort": {"count": -1}},
            {"$limit": top_n}
        ]
        results = list(collection.aggregate(pipeline))
        title = "Isolation Source Distribution"

    if not results:
        return "No isolation source data found"

    sources = [r["_id"] if r["_id"] else "Unknown" for r in results]
    counts = [r["count"] for r in results]

    return make_chart_response(
        chart_type="pie",
        title=title,
        data={
            "labels": sources,
            "values": counts
        },
        layout={}
    )


@mcp.tool()
def plot_phylogroup_distribution(pangenome_analysis: str) -> str:
    """
    Generate bar chart showing phylogroup distribution for a species.
    Returns Plotly-compatible JSON data for interactive visualization.

    Args:
        pangenome_analysis: Species pangenome analysis name
    """
    collection = mongo_client.get_collection(Config.COLLECTIONS["genome_info"])

    pipeline = [
        {"$match": {"pangenome_analysis": pangenome_analysis}},
        {"$group": {"_id": "$phylo_group", "count": {"$sum": 1}}},
        {"$match": {"_id": {"$ne": None}}},
        {"$sort": {"count": -1}}
    ]
    results = list(collection.aggregate(pipeline))

    if not results:
        return f"No phylogroup data found for {pangenome_analysis}"

    phylogroups = [r["_id"] if r["_id"] else "Unknown" for r in results]
    counts = [r["count"] for r in results]

    return make_chart_response(
        chart_type="bar",
        title=f"Phylogroup Distribution - {pangenome_analysis.replace('_', ' ')}",
        data={
            "x": phylogroups,
            "y": counts,
            "labels": {"x": "Phylogroup", "y": "Number of Genomes"}
        },
        layout={
            "color": "tab10"
        }
    )


@mcp.tool()
def plot_pangenome_openness(family: Optional[str] = None, top_n: int = 20) -> str:
    """
    Generate chart comparing pangenome openness (Open/Closed) across species.
    Returns Plotly-compatible JSON data for interactive visualization.

    Args:
        family: Optional: filter by family name
        top_n: Number of species to show (default: 20)
    """
    collection = mongo_client.get_collection(Config.COLLECTIONS["organisms"])

    query = {}
    if family:
        query["family"] = {"$regex": family, "$options": "i"}

    results = list(collection.find(
        query,
        {"species": 1, "openness": 1, "genomes_num": 1}
    ).sort("genomes_num", -1).limit(top_n))

    if not results:
        return "No species data found"

    species_names = []
    openness_values = []
    colors = []

    openness_colors = {
        'Open': '#e74c3c',
        'Intermediate Open': '#f39c12',
        'Closed': '#2ecc71'
    }

    for r in results:
        species_names.append(r.get("species", "Unknown").replace("_", " "))
        openness = r.get("openness", "Unknown")
        openness_values.append(openness)
        colors.append(openness_colors.get(openness, 'gray'))

    title = "Pangenome Openness by Species"
    if family:
        title += f" - Family: {family}"

    return make_chart_response(
        chart_type="bar_categorical",
        title=title,
        data={
            "y": species_names,
            "categories": openness_values,
            "colors": colors,
            "legend": [
                {"label": "Closed", "color": "#2ecc71"},
                {"label": "Intermediate Open", "color": "#f39c12"},
                {"label": "Open", "color": "#e74c3c"}
            ]
        },
        layout={}
    )


@mcp.tool()
def plot_phylon_heatmap(pangenome_analysis: str, max_genomes: int = 50) -> str:
    """
    Generate heatmap showing phylon weights for genomes in a species.
    Returns Plotly-compatible JSON data for interactive visualization.

    Args:
        pangenome_analysis: Species pangenome analysis name
        max_genomes: Maximum number of genomes to show (default: 50)
    """
    collection = mongo_client.get_collection(Config.COLLECTIONS["genome_phylons"])

    results = list(collection.find(
        {"pangenome_analysis": pangenome_analysis},
        {"genome_id": 1, "phylon_weights": 1}
    ).limit(max_genomes))

    if not results:
        return f"No phylon data found for {pangenome_analysis}"

    genome_ids = []
    weight_matrix = []
    phylon_keys = None

    for r in results:
        weights_dict = r.get("phylon_weights", {})
        if weights_dict and isinstance(weights_dict, dict):
            if phylon_keys is None:
                phylon_keys = sorted(weights_dict.keys(), key=lambda x: int(x) if x.isdigit() else x)

            weights = [weights_dict.get(k, 0) for k in phylon_keys]
            genome_ids.append(r.get("genome_id", "Unknown")[:15])
            weight_matrix.append(weights)

    if not weight_matrix:
        return f"No phylon weights found for {pangenome_analysis}"

    return make_chart_response(
        chart_type="heatmap",
        title=f"Phylon Weight Heatmap - {pangenome_analysis.replace('_', ' ')}",
        data={
            "z": weight_matrix,
            "x": [f"P{k}" for k in phylon_keys],
            "y": genome_ids,
            "labels": {"x": "Phylon", "y": "Genome"}
        },
        layout={
            "colorscale": "YlOrRd"
        }
    )
