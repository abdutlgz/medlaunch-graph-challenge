# Medlaunch Graph Challenge

Python implementation of a MongoDB-based graph layer for healthcare quality management data.

## Overview

This project models relationships between healthcare quality entities using a `graph_edges` collection in MongoDB. The source collections contain findings, action items, standards, policies, quality objectives, and events. Embedded references in those documents are materialized into explicit directed edges so the data can be queried as a graph.

The project includes:

- idempotent seed loading of all entity collections
- operational edge creation from embedded references
- traversal and analysis queries
- analytical `SIMILAR_TO` edge generation
- connected-component clustering from analytical edges

## Tech Stack

- Python 3
- MongoDB Atlas or local MongoDB
- `pymongo`
- `python-dotenv`

## Project Structure

```text
medlaunch-graph-challenge/
├── README.md
├── SCHEMA.md
├── seed-data/
│   ├── standards.json
│   ├── findings.json
│   ├── action_items.json
│   ├── policies.json
│   ├── quality_objectives.json
│   └── events.json
├── src/
│   ├── seed.py
│   ├── queries.py
│   ├── batch.py
│   └── cluster.py
├── eda_and_more/
│   ├── 01_data_inventory.ipynb
│   ├── 02_reference_map.ipynb
│   ├── 03_graph_visualization.ipynb
│   └── notes.md
├── output/
│   ├── clusters.json
│   ├── query1_multi_hop_fnd_002.json
│   ├── query2_standard_impact_std_002.json
│   ├── query3_org_scoped_subgraph_dillon.json
│   └── query4_fan_out_by_edge_class.json
├── requirements.txt
├── .env.example
└── .gitignore
```

## Setup

1. Create and activate a Python environment if desired.
2. Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

3. Create a local `.env` file with your MongoDB connection string:

```env
MONGODB_URI=mongodb+srv://<username>:<password>@<cluster-url>/medlaunch_challenge?retryWrites=true&w=majority
```

The scripts also default to:

```text
mongodb://localhost:27017/medlaunch_challenge
```

if `MONGODB_URI` is not set.

## Running the Pipeline

### 1. Seed entities and operational edges

```bash
python3 src/seed.py
```

What it does:

- loads all 43 seed entities into MongoDB
- creates operational edges from reference arrays
- validates references before creating edges
- prints a seed summary

### 2. Run traversal and analysis queries

```bash
python3 src/queries.py
```

What it does:

- Query 1: Multi-hop neighbor discovery from `FND-002`
- Query 2: Standard impact analysis for `STD-002`
- Query 3: Org-scoped subgraph extraction for `ORG-MCLEOD-DILLON`
- Query 4: Fan-out by edge class

Results are exported to the `output/` directory as JSON.

### 3. Generate analytical similarity edges

```bash
python3 src/batch.py
```

What it does:

- evaluates same-type entity pairs
- requires at least 2 shared tags and 1 shared standard
- creates analytical `SIMILAR_TO` edges
- removes stale similarity edges from prior runs
- is idempotent on rerun

### 4. Build clusters from similarity edges

```bash
python3 src/cluster.py
```

What it does:

- reads analytical `SIMILAR_TO` edges
- computes connected components
- rebuilds the `clusters` collection
- prints cluster count and size distribution
- writes `output/clusters.json`

## Current Outputs

The current query outputs are stored in `output/`:

- `clusters.json`
- `query1_multi_hop_fnd_002.json`
- `query2_standard_impact_std_002.json`
- `query3_org_scoped_subgraph_dillon.json`
- `query4_fan_out_by_edge_class.json`


## Notes on Design

- All graph edges are directional.
- All queries are designed around org scoping.
- The seed and batch scripts are rerunnable.
- Operational and analytical relationships are separated using `edgeClass` and `origin`.

Additional schema details and index strategy are documented in `SCHEMA.md`.
