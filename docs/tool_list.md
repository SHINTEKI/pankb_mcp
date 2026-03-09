# PanKB MCP Server Tool List

## 1. Query Tools

| Tool | Description | Example Query |
|------|-------------|---------------|
| `list_families` | List (all or designated) microbial families with species/genome counts | List all families in PanKB|
| `list_species` | List (all or designated) species with pangenome statistics (core/shell/cloud) | List species in Bacillaceae |
| `list_genomes` | List (all or designated) genomes with GC content, length, and isolation info | List genomes of Escherichia coli |
| `list_genes` | Search genes by name, function, or pangenomic class | Search for gene dnaA in Escherichia coli |
| `get_stats` | Get database-wide statistics | Show database statistics |

## 2. Navigation Tools

| Tool | Description | Example Query |
|------|-------------|---------------|
| `get_family_url` | Link to a family page on pankb.org | Give me the PanKB family page for Bacillaceae |
| `get_species_url` | Link to a species page with section options | Link to species Escherichia coli overview page |
| `get_genome_url` | Link to an individual genome page | Show me genome page for GCF_000005845.2 if it exists |
| `get_gene_url_with_species_specified` | Link to a gene in a specific species | Link to gene dnaA in species Escherichia coli |
| `get_gene_url_with_species_unspecified` | Search a gene across all species | Search gene dnaA across all species and list respective URLs |
| `get_search_url` | General search on pankb.org | Search PanKB for antibiotic resistance |

## 3. Chart Tools

| Tool | Description | Example Query |
|------|-------------|---------------|
| `plot_gene_frequency_histogram` | U-shaped gene frequency distribution | Plot gene frequency histogram for Escherichia coli |
| `plot_pangenome_class_distribution` | Core/Accessory/Rare gene pie chart | Plot pangenome class distribution for Escherichia coli |
| `plot_cog_category_distribution` | COG functional category bar chart | Plot COG category distribution for Escherichia coli |
| `plot_species_comparison` | Compare pangenome composition across species | Compare species in family Bacillaceae |
| `plot_genome_count_by_family` | Genome counts per family bar chart | Plot genome count by family |
| `plot_gc_content_distribution` | GC content histogram for a species | Plot GC content distribution for Escherichia coli |
| `plot_geographic_distribution` | Genome counts by country | Plot geographic distribution for Escherichia coli |
| `plot_isolation_source_distribution` | Isolation source pie chart | Plot isolation source distribution for Escherichia coli |
| `plot_phylogroup_distribution` | Phylogroup bar chart | Plot phylogroup distribution for Escherichia coli |
| `plot_phylon_heatmap` | Phylon weight heatmap across genomes | Plot phylon heatmap for Escherichia coli |
| `plot_heaps_law` | Pangenome growth curve (Heaps' law) | Plot Heaps law curve for Escherichia coli |
| `plot_cumulative_gene_frequency` | Cumulative gene frequency curve | Plot cumulative gene frequency for Escherichia coli |
| `plot_gene_frequency_curve` | Gene frequency distribution curve | Plot gene frequency curve for Escherichia coli |
| `plot_cog_by_gene_class` | COG categories split by gene class | Plot COG by gene class for Escherichia coli |
| `plot_gene_presence_absence_matrix` | Gene presence/absence binary matrix | Plot gene presence absence matrix for Escherichia coli |
| `plot_dn_ds_ratio` | Selection pressure (dN/dS) distribution | Plot dN/dS ratio for Escherichia coli |

## 4. RAG (Literature Search)

> Toggle on the "Search Literature" switch in the sidebar first.

| Tool | Description | Example Query |
|------|-------------|---------------|
| `search_pangenome_literature` | Search pangenome research papers via RAG | What is pangenome openness and how is it measured? |
