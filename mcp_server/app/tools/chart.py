"""
Visualization Tools for PanKB MCP Server

These tools return Plotly-compatible JSON data for interactive chart rendering.
Data sources: MongoDB (realtime queries) and Azure Blob Storage (pre-computed analysis).
"""
import json
import logging
import math
import re
from collections import Counter
from typing import Literal, Optional

import requests
from fastmcp import FastMCP

from app.config import Config
from app.utils.connections import blob_client, mongo_client

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
    """
    Create a chart response as JSON data points for client-side rendering.
    The client rebuilds the Plotly figure from these fields.
    """
    return json.dumps({
        "type": "chart",
        "chart_type": chart_type,
        "title": title,
        "data": data,
        "layout": layout or {}
    })


mcp = FastMCP(name="ChartTools")


@mcp.tool()
def plot_gene_frequency_histogram(pangenome_analysis: str):
    """
    Generate gene frequency histogram (U-shape curve) for a species.
    Returns Plotly-compatible JSON data for interactive visualization.

    Args:
        pangenome_analysis: Species pangenome analysis name (e.g., 'Escherichia_coli')
    """
    # Normalize species name: replace spaces with underscores
    pangenome_analysis = pangenome_analysis.replace(" ", "_")

    collection = mongo_client.get_collection(Config.MONGODB_COLLECTIONS["gene_annotations"])

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
            "color": "#4a90d9"
        }
    )


@mcp.tool()
def plot_pangenome_class_distribution(pangenome_analysis: str):
    """
    Generate pie chart showing Core/Accessory/Rare gene distribution for a species.
    Returns Plotly-compatible JSON data for interactive visualization.

    Args:
        pangenome_analysis: Species pangenome analysis name (e.g., 'Bacillus_subtilis')
    """
    # Normalize species name: replace spaces with underscores
    pangenome_analysis = pangenome_analysis.replace(" ", "_")

    collection = mongo_client.get_collection(Config.MONGODB_COLLECTIONS["gene_annotations"])

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
def plot_cog_category_distribution(pangenome_analysis: str, top_n: Optional[int] = None):
    """
    Generate bar chart showing COG functional category distribution for a species.
    Returns Plotly-compatible JSON data for interactive visualization.

    Args:
        pangenome_analysis: Species pangenome analysis name
        top_n: Optional: limit number of categories shown (default: show all)
    """
    # Normalize species name: replace spaces with underscores
    pangenome_analysis = pangenome_analysis.replace(" ", "_")

    collection = mongo_client.get_collection(Config.MONGODB_COLLECTIONS["gene_annotations"])

    pipeline = [
        {"$match": {"pangenome_analysis": pangenome_analysis}},
        {"$group": {"_id": "$cog_category", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    if top_n:
        pipeline.append({"$limit": top_n})
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
            "color": "#4a90d9"
        }
    )


@mcp.tool()
def plot_species_comparison(family: str, top_n: Optional[int] = None):
    """
    Generate stacked bar chart comparing Core/Accessory/Rare genes across species in a family.
    Returns Plotly-compatible JSON data for interactive visualization.

    Args:
        family: Family name to compare species (e.g., 'Bacillaceae')
        top_n: Optional: limit number of species shown (default: show all)
    """
    collection = mongo_client.get_collection(Config.MONGODB_COLLECTIONS["organisms"])

    query = collection.find(
        {"family": {"$regex": family, "$options": "i"}},
        {"species": 1, "gene_class_distribution": 1, "genomes_num": 1}
    ).sort("genomes_num", -1)
    if top_n:
        query = query.limit(top_n)
    results = list(query)

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
def plot_genome_count_by_family(family: Optional[str] = None, top_n: Optional[int] = None):
    """
    Generate bar chart showing genome counts across families or species.
    Returns Plotly-compatible JSON data for interactive visualization.

    Args:
        family: Optional: filter by family name to show species within
        top_n: Optional: limit number of entries shown (default: show all)
    """
    collection = mongo_client.get_collection(Config.MONGODB_COLLECTIONS["organisms"])

    if family:
        pipeline = [
            {"$match": {"family": {"$regex": family, "$options": "i"}}},
            {"$sort": {"genomes_num": -1}},
        ]
        if top_n:
            pipeline.append({"$limit": top_n})
        pipeline.append({"$project": {"name": "$species", "count": "$genomes_num"}})
        title = f"Genome Count by Species - Family: {family}"
    else:
        pipeline = [
            {"$group": {"_id": "$family", "count": {"$sum": "$genomes_num"}}},
            {"$sort": {"count": -1}},
        ]
        if top_n:
            pipeline.append({"$limit": top_n})
        pipeline.append({"$project": {"name": "$_id", "count": 1}})
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
            "color": "#4a90d9"
        }
    )


@mcp.tool()
def plot_gc_content_distribution(pangenome_analysis: str):
    """
    Generate histogram of GC content distribution for genomes in a species.
    Returns Plotly-compatible JSON data for interactive visualization.

    Args:
        pangenome_analysis: Species pangenome analysis name
    """
    # Normalize species name: replace spaces with underscores
    pangenome_analysis = pangenome_analysis.replace(" ", "_")

    collection = mongo_client.get_collection(Config.MONGODB_COLLECTIONS["genome_info"])

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
            "color": "#4a90d9",
            "vline": {"x": mean_gc, "color": "red", "label": f"Mean: {mean_gc:.2f}%"}
        }
    )


@mcp.tool()
def plot_geographic_distribution(pangenome_analysis: Optional[str] = None, top_n: Optional[int] = None):
    """
    Generate bar chart showing geographic distribution of genomes by country.
    Returns Plotly-compatible JSON data for interactive visualization.

    Args:
        pangenome_analysis: Optional: filter by species pangenome analysis name
        top_n: Optional: limit number of countries shown (default: show all)
    """
    # Normalize species name: replace spaces with underscores
    if pangenome_analysis:
        pangenome_analysis = pangenome_analysis.replace(" ", "_")

    if pangenome_analysis:
        genome_collection = mongo_client.get_collection(Config.MONGODB_COLLECTIONS["genome_info"])
        pipeline = [
            {"$match": {"pangenome_analysis": pangenome_analysis}},
            {
                "$lookup": {
                    "from": Config.MONGODB_COLLECTIONS["isolation_info"],
                    "localField": "genome_id",
                    "foreignField": "genome_id",
                    "as": "isolation"
                }
            },
            {"$unwind": {"path": "$isolation", "preserveNullAndEmptyArrays": False}},
            {"$group": {"_id": "$isolation.country", "count": {"$sum": 1}}},
            {"$match": {"_id": {"$nin": [None, "", "?", "missing", "Missing", "Unknown", "unknown"]}}},
            {"$sort": {"count": -1}},
        ]
        if top_n:
            pipeline.append({"$limit": top_n})
        results = list(genome_collection.aggregate(pipeline))
        title = f"Geographic Distribution - {pangenome_analysis.replace('_', ' ')}"
    else:
        collection = mongo_client.get_collection(Config.MONGODB_COLLECTIONS["isolation_info"])
        pipeline = [
            {"$group": {"_id": "$country", "count": {"$sum": 1}}},
            {"$match": {"_id": {"$nin": [None, "", "?", "missing", "Missing", "Unknown", "unknown"]}}},
            {"$sort": {"count": -1}},
        ]
        if top_n:
            pipeline.append({"$limit": top_n})
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
            "color": "#4a90d9"
        }
    )


@mcp.tool()
def plot_isolation_source_distribution(pangenome_analysis: Optional[str] = None, top_n: Optional[int] = None):
    """
    Generate pie chart showing distribution of isolation sources for genomes.
    Returns Plotly-compatible JSON data for interactive visualization.

    Args:
        pangenome_analysis: Optional: filter by species pangenome analysis name
        top_n: Optional: limit number of sources shown (default: show all)
    """
    # Normalize species name: replace spaces with underscores
    if pangenome_analysis:
        pangenome_analysis = pangenome_analysis.replace(" ", "_")

    if pangenome_analysis:
        genome_collection = mongo_client.get_collection(Config.MONGODB_COLLECTIONS["genome_info"])
        pipeline = [
            {"$match": {"pangenome_analysis": pangenome_analysis}},
            {
                "$lookup": {
                    "from": Config.MONGODB_COLLECTIONS["isolation_info"],
                    "localField": "genome_id",
                    "foreignField": "genome_id",
                    "as": "isolation"
                }
            },
            {"$unwind": {"path": "$isolation", "preserveNullAndEmptyArrays": False}},
            {"$group": {"_id": "$isolation.isolation_source", "count": {"$sum": 1}}},
            {"$match": {"_id": {"$nin": [None, "Missing", "missing", "", "-", "Not available", "not available"]}}},
            {"$sort": {"count": -1}},
        ]
        if top_n:
            pipeline.append({"$limit": top_n})
        results = list(genome_collection.aggregate(pipeline))
        title = f"Isolation Source Distribution - {pangenome_analysis.replace('_', ' ')}"
    else:
        collection = mongo_client.get_collection(Config.MONGODB_COLLECTIONS["isolation_info"])
        pipeline = [
            {"$group": {"_id": "$isolation_source", "count": {"$sum": 1}}},
            {"$match": {"_id": {"$nin": [None, "Missing", "missing", "", "-", "Not available", "not available"]}}},
            {"$sort": {"count": -1}},
        ]
        if top_n:
            pipeline.append({"$limit": top_n})
        results = list(collection.aggregate(pipeline))
        title = "Isolation Source Distribution"

    if not results:
        return "No isolation source data found"

    # Default to top 10 for pie chart readability, group the rest as "Other"
    display_n = top_n if top_n else 10
    if len(results) > display_n:
        top_results = results[:display_n]
        other_count = sum(r["count"] for r in results[display_n:])
        sources = [r["_id"] if r["_id"] else "Unknown" for r in top_results] + ["Other"]
        counts = [r["count"] for r in top_results] + [other_count]
    else:
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
def plot_phylogroup_distribution(pangenome_analysis: str):
    """
    Generate bar chart showing phylogroup distribution for a species.
    Returns Plotly-compatible JSON data for interactive visualization.

    Args:
        pangenome_analysis: Species pangenome analysis name
    """
    # Normalize species name: replace spaces with underscores
    pangenome_analysis = pangenome_analysis.replace(" ", "_")

    collection = mongo_client.get_collection(Config.MONGODB_COLLECTIONS["genome_info"])

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
            "color": "#4a90d9"
        }
    )


@mcp.tool()
def plot_pangenome_openness(family: Optional[str] = None, top_n: Optional[int] = None):
    """
    Generate chart comparing pangenome openness (Open/Closed) across species.
    Returns Plotly-compatible JSON data for interactive visualization.

    Args:
        family: Optional: filter by family name
        top_n: Optional: limit number of species shown (default: show all)
    """
    collection = mongo_client.get_collection(Config.MONGODB_COLLECTIONS["organisms"])

    query = {}
    if family:
        query["family"] = {"$regex": family, "$options": "i"}

    cursor = collection.find(
        query,
        {"species": 1, "openness": 1, "genomes_num": 1}
    ).sort("genomes_num", -1)
    if top_n:
        cursor = cursor.limit(top_n)
    results = list(cursor)

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
def plot_phylon_heatmap(pangenome_analysis: str, max_genomes: int = 50):
    """
    Generate heatmap showing phylon weights for genomes in a species.
    Returns Plotly-compatible JSON data for interactive visualization.

    Args:
        pangenome_analysis: Species pangenome analysis name
        max_genomes: Maximum number of genomes to show (default: 50)
    """
    # Normalize species name: replace spaces with underscores
    pangenome_analysis = pangenome_analysis.replace(" ", "_")

    collection = mongo_client.get_collection(Config.MONGODB_COLLECTIONS["genome_phylons"])

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


# =============================================================================
# Pre-computed Analysis Charts (from Azure Blob Storage)
# =============================================================================

@mcp.tool()
def plot_heaps_law(species: str):
    """
    Plot Heap's Law curve showing pangenome openness.
    Shows how the number of new genes discovered changes as more genomes are added.
    Open pangenomes show continuous gene discovery.
    Returns Plotly-compatible JSON data for interactive visualization.

    Args:
        species: Species identifier (e.g., 'Escherichia_coli')
    """
    # Normalize species name: replace spaces with underscores
    species = species.replace(" ", "_")

    try:
        data = blob_client.fetch_json(species, "heaps_law.json")
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return f"Data not available for {species}. The species may not have pre-computed analysis data."
        return f"HTTP Error: {str(e)}"

    avg_core = data.get("avg_core", [])
    avg_acc = data.get("avg_acc", [])

    if not avg_core or not avg_acc:
        return "No Heap's law data available for this species"

    x = list(range(1, len(avg_core) + 1))

    return make_chart_response(
        chart_type="line_multi",
        title=f"Heap's Law - {species.replace('_', ' ')}",
        data={
            "x": x,
            "series": [
                {"name": "Core genes", "values": avg_core, "color": "blue"},
                {"name": "Accessory genes", "values": avg_acc, "color": "red"}
            ],
            "labels": {"x": "Number of Genomes", "y": "Number of Genes"},
            "stats": {
                "final_core": avg_core[-1] if avg_core else 0,
                "final_accessory": avg_acc[-1] if avg_acc else 0,
                "num_genomes": len(avg_core)
            }
        },
        layout={}
    )


@mcp.tool()
def plot_cumulative_gene_frequency(species: str):
    """
    Plot cumulative gene frequency curve showing how genes accumulate across genomes.
    Useful for understanding pangenome saturation.
    Returns Plotly-compatible JSON data for interactive visualization.

    Args:
        species: Species identifier (e.g., 'Escherichia_coli')
    """
    # Normalize species name: replace spaces with underscores
    species = species.replace(" ", "_")

    try:
        data = blob_client.fetch_json(species, "cum_freq.json")
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return f"Data not available for {species}."
        return f"HTTP Error: {str(e)}"

    if isinstance(data, dict):
        if 'x' in data and 'y' in data:
            x = data['x']
            y = data['y']
        else:
            x = list(range(len(list(data.values())[0])))
            y = list(data.values())[0]
    else:
        return "Unexpected data format"

    return make_chart_response(
        chart_type="line",
        title=f"Cumulative Gene Frequency - {species.replace('_', ' ')}",
        data={
            "x": x,
            "y": y,
            "labels": {"x": "Gene Frequency (% of genomes)", "y": "Cumulative Gene Count"}
        },
        layout={
            "color": "blue"
        }
    )


@mcp.tool()
def plot_gene_frequency_curve(species: str):
    """
    Plot gene frequency distribution from pre-computed data.
    Shows the classic U-shaped pangenome curve with core genes on the right and rare genes on the left.
    Returns Plotly-compatible JSON data for interactive visualization.

    Args:
        species: Species identifier (e.g., 'Escherichia_coli')
    """
    # Normalize species name: replace spaces with underscores
    species = species.replace(" ", "_")

    try:
        data = blob_client.fetch_json(species, "gene_freq.json")
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return f"Data not available for {species}."
        return f"HTTP Error: {str(e)}"

    frequency = data.get("frequency", [])
    x15 = data.get("x15", 0)
    x99 = data.get("x99", 0)

    if not frequency:
        return "No gene frequency data available"

    freq_counts = Counter(frequency)
    x_vals = sorted(freq_counts.keys())
    y_vals = [freq_counts[x] for x in x_vals]

    total_genes = len(frequency)
    max_freq = max(frequency) if frequency else 0
    rare_genes = sum(1 for f in frequency if f <= x15) if x15 > 0 else 0
    core_genes = sum(1 for f in frequency if f >= x99) if x99 > 0 else 0

    vlines = []
    if x15 > 0:
        vlines.append({"x": x15, "color": "orange", "label": f"15% threshold ({x15})"})
    if x99 > 0:
        vlines.append({"x": x99, "color": "green", "label": f"99% threshold ({x99})"})

    return make_chart_response(
        chart_type="bar",
        title=f"Gene Frequency Distribution - {species.replace('_', ' ')}",
        data={
            "x": x_vals,
            "y": y_vals,
            "labels": {"x": "Gene Frequency (number of genomes)", "y": "Number of Genes"},
            "stats": {
                "total_genes": total_genes,
                "max_frequency": max_freq,
                "rare_genes": rare_genes,
                "core_genes": core_genes
            }
        },
        layout={
            "color": "#4a90d9",
            "bargap": 0,
            "vlines": vlines
        }
    )


@mcp.tool()
def plot_cog_by_gene_class(species: str):
    """
    Plot COG functional category distribution by gene class (Core/Accessory/Rare).
    Shows which functional categories are enriched in each pangenome class.
    Returns Plotly-compatible JSON data for interactive visualization.

    Args:
        species: Species identifier (e.g., 'Escherichia_coli')
    """
    # Normalize species name: replace spaces with underscores
    species = species.replace(" ", "_")

    try:
        data = blob_client.fetch_json(species, "COG_distribution.json")
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return f"Data not available for {species}."
        return f"HTTP Error: {str(e)}"

    categories = data.get("categories", [])
    core = data.get("Core", [])
    accessory = data.get("Accessory", [])
    rare = data.get("Rare", [])

    if not categories:
        return "No COG distribution data available"

    short_labels = [c.split(']')[0] + ']' if ']' in c else c[:20] for c in categories]

    return make_chart_response(
        chart_type="bar_grouped",
        title=f"COG Distribution by Gene Class - {species.replace('_', ' ')}",
        data={
            "x": short_labels,
            "series": [
                {"name": "Core", "values": core, "color": "#2ecc71"},
                {"name": "Accessory", "values": accessory, "color": "#3498db"},
                {"name": "Rare", "values": rare, "color": "#e74c3c"}
            ],
            "labels": {"x": "COG Category", "y": "Number of Genes"},
            "stats": {
                "total_core": sum(core),
                "total_accessory": sum(accessory),
                "total_rare": sum(rare)
            }
        },
        layout={}
    )


@mcp.tool()
def plot_gene_presence_absence_matrix(
    species: str,
    gene_class: Literal["core", "accessory", "rare"],
    max_genomes: int = 100,
    max_genes: int = 500
):
    """
    Plot gene presence/absence matrix as a heatmap.
    Shows which genes are present (1) or absent (0) in each genome.
    Limited to max_genomes x max_genes for performance. View full matrix on PanKB website.

    Args:
        species: Species identifier (e.g., 'Escherichia_coli')
        gene_class: Gene class to visualize: 'core', 'accessory', or 'rare'
        max_genomes: Maximum number of genomes to display (default: 100)
        max_genes: Maximum number of genes to display (default: 500)
    """
    # Normalize species name: replace spaces with underscores
    species = species.replace(" ", "_")

    try:
        data = blob_client.fetch_gzip_json(species, f"heatmap_{gene_class}.json.gz")
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return f"Data not available for {species}."
        return f"HTTP Error: {str(e)}"

    rows = data.get("rows", [])
    cols = data.get("cols", [])
    matrix = data.get("matrix", [])

    if not matrix:
        return f"No matrix data available for {species}"

    n_genomes = len(rows)
    n_genes = len(cols)

    # Limit dimensions for visualization
    display_genomes = min(n_genomes, max_genomes)
    display_genes = min(n_genes, max_genes)

    # Extract subset of data
    genome_names = [r.get("name", "unknown")[:20] for r in rows[:display_genomes]]
    gene_names = [c.get("name", "unknown")[:15] for c in cols[:display_genes]]
    matrix_subset = [row[:display_genes] for row in matrix[:display_genomes]]

    # Website URL for full visualization
    website_url = f"https://pankb.org/pangenome_analyses/overview/?species={species}"

    is_truncated = n_genomes > display_genomes or n_genes > display_genes

    return make_chart_response(
        chart_type="heatmap",
        title=f"Gene Presence/Absence - {species.replace('_', ' ')} ({gene_class.capitalize()})",
        data={
            "z": matrix_subset,
            "x": gene_names,
            "y": genome_names,
            "labels": {"x": "Genes", "y": "Genomes"},
            "stats": {
                "total_genomes": n_genomes,
                "total_genes": n_genes,
                "displayed_genomes": display_genomes,
                "displayed_genes": display_genes,
                "is_truncated": is_truncated
            },
            "website_url": website_url
        },
        layout={
            "colorscale": [[0, "#f0f0f0"], [1, "#2ecc71"]],
            "showscale": False
        }
    )


# @mcp.tool()
def get_phylogenetic_tree(species: str):
    """
    Get phylogenetic tree information for a species.
    Returns tree statistics and a link to view the interactive tree on PanKB website.
    The Newick format is also provided for external visualization tools.

    Args:
        species: Species identifier (e.g., 'Escherichia_coli')
    """
    # Normalize species name: replace spaces with underscores
    species = species.replace(" ", "_")

    try:
        newick = blob_client.fetch_text(species, "phylogenetic_tree.newick")
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return f"Phylogenetic tree not available for {species}."
        return f"HTTP Error: {str(e)}"

    # Extract tip names (genome IDs)
    tips = re.findall(r'([A-Za-z0-9_.-]+):', newick)
    n_tips = len(tips)

    # Calculate tree depth (approximate by counting max nested parentheses)
    max_depth = 0
    current_depth = 0
    for char in newick:
        if char == '(':
            current_depth += 1
            max_depth = max(max_depth, current_depth)
        elif char == ')':
            current_depth -= 1

    # Website URL for interactive tree visualization
    website_url = f"https://pankb.org/pangenome_analyses/overview/?species={species}"

    # Return structured JSON for frontend rendering
    return json.dumps({
        "type": "string",
        "format": "tree_info",
        "content": {
            "species": species.replace('_', ' '),
            "n_tips": n_tips,
            "tree_depth": max_depth,
            "newick_length": len(newick),
            "sample_tips": tips[:10],  # Show first 10 genome IDs
            "website_url": website_url,
            "message": f"Phylogenetic tree with {n_tips} genomes. View the interactive tree on PanKB website."
        }
    })


@mcp.tool()
def plot_dn_ds_ratio(species: str):
    """
    Plot dN/dS ratio distribution from alleleome analysis.
    Shows selection pressure across genes - values < 1 indicate purifying selection, > 1 indicates positive selection.
    Returns Plotly-compatible JSON data for interactive visualization.

    Args:
        species: Species identifier (e.g., 'Escherichia_coli')
    """
    # Normalize species name: replace spaces with underscores
    species = species.replace(" ", "_")

    try:
        data = blob_client.fetch_json(species, "panalleleome/dn_ds.json")
    except requests.exceptions.HTTPError:
        return "dN/dS data not available for this species (panalleleome analysis may not be completed)"
    except Exception as e:
        return f"Error: {str(e)}"

    if isinstance(data, dict):
        if 'dn_ds' in data:
            values = data['dn_ds']
        elif 'values' in data:
            values = data['values']
        else:
            values = list(data.values())[0] if data else []
    elif isinstance(data, list):
        values = data
    else:
        return "Unexpected data format for dN/dS"

    if not values:
        return "No dN/dS values available"

    values = [v for v in values if isinstance(v, (int, float)) and not math.isnan(v) and v < 10]

    mean_val = sum(values) / len(values) if values else 0
    sorted_vals = sorted(values)
    median_val = sorted_vals[len(sorted_vals) // 2] if sorted_vals else 0
    under_purifying = sum(1 for v in values if v < 1)
    under_positive = sum(1 for v in values if v > 1)

    return make_chart_response(
        chart_type="histogram",
        title=f"dN/dS Ratio Distribution - {species.replace('_', ' ')}",
        data={
            "values": values,
            "labels": {"x": "dN/dS Ratio", "y": "Number of Genes"},
            "stats": {
                "total_genes": len(values),
                "mean": mean_val,
                "median": median_val,
                "purifying_selection": under_purifying,
                "positive_selection": under_positive
            }
        },
        layout={
            "nbins": 50,
            "color": "#4a90d9",
            "vline": {"x": 1, "color": "red", "label": "Neutral (dN/dS = 1)"}
        }
    )


# @mcp.tool()
def plot_variant_dominant_frequency(species: str):
    """
    Plot variant dominant frequency from panalleleome analysis.
    Shows allele frequency patterns across the pangenome.
    Returns Plotly-compatible JSON data for interactive visualization.

    Args:
        species: Species identifier (e.g., 'Escherichia_coli')
    """
    # Normalize species name: replace spaces with underscores
    species = species.replace(" ", "_")

    try:
        data = blob_client.fetch_json(species, "panalleleome/step_line.json")
    except requests.exceptions.HTTPError:
        return "Variant frequency data not available for this species"
    except Exception as e:
        return f"Error: {str(e)}"

    if isinstance(data, dict):
        x = data.get('x', data.get('frequency', []))
        y = data.get('y', data.get('count', []))
    else:
        return "Unexpected data format"

    if not x or not y:
        return "No variant frequency data available"

    return make_chart_response(
        chart_type="line_step",
        title=f"Variant Dominant Frequency - {species.replace('_', ' ')}",
        data={
            "x": x,
            "y": y,
            "labels": {"x": "Dominant Variant Frequency", "y": "Number of Genes"}
        },
        layout={
            "color": "#4a90d9"
        }
    )
