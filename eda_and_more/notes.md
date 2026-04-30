# EDA Notes

## Scope

This folder captures lightweight exploratory analysis of the seed data before implementation.

The analysis covers:

- How many entities are in each seed file?
- Which fields contain references?
- Which references become graph edges?
- Which organizations can see which entities?
- Which entities behave like hubs?

## Notebook Sequence

1. `01_data_inventory.ipynb`
2. `02_reference_map.ipynb`
3. `03_graph_visualization.ipynb`

## Reference Examples

- `FND-002 -> STD-002`
- `FND-002 -> STD-007`
- `FND-002 -> AI-003`
- `FND-002 -> POL-002`

## Purpose

These notebooks document the structure of the raw data, the reference-to-edge mapping, and the main connectivity patterns used in the graph design.
