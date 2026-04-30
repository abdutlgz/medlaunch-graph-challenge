# Graph Edge Schema

## Purpose

The `graph_edges` collection materializes relationships between healthcare quality management entities stored in MongoDB. The source entity collections (`findings`, `action_items`, `policies`, `standards`, `quality_objectives`, and `events`) already contain reference arrays such as `standardRefs`, `policyRefs`, and `actionItemRefs`, but those references are embedded inside documents and are not ideal for graph traversal.

The `graph_edges` collection turns those embedded references into explicit edge documents. This supports:

- directional traversal
- reverse traversal
- org-scoped graph queries
- separation of operational vs analytical relationships
- future extension to semantic relationships

## Edge Classes

Each edge belongs to exactly one class:

- `operational`: explicit relationships created by users or extracted from source data
- `semantic`: reserved for future meaning-based associations
- `analytical`: system-generated relationships such as similarity or recurrence

## Origin Values

Each edge records where it came from:

- `user`: created directly by a user action
- `ingestion`: extracted from seed/source documents during ingestion
- `system-batch`: created by a batch process such as similarity enrichment

## Edge Document Schema

A single edge document has the following structure:

```json
{
  "_id": "operational|ORG-MCLEOD-MAIN|finding|FND-001|CITES_STANDARD|standard|STD-001",
  "orgId": "ORG-MCLEOD-MAIN",
  "edgeClass": "operational",
  "origin": "ingestion",
  "type": "CITES_STANDARD",
  "from": {
    "entityType": "finding",
    "entityId": "FND-001"
  },
  "to": {
    "entityType": "standard",
    "entityId": "STD-001"
  }
}
```

## Field-by-Field Definition

### `_id`

A deterministic string identifier for the edge.

Format:

```text
{edgeClass}|{orgId}|{from.entityType}|{from.entityId}|{type}|{to.entityType}|{to.entityId}
```

Why it exists:

- guarantees idempotency
- prevents duplicate edges on rerun
- makes upserts simple and predictable

### `orgId`

The tenant/org scope of the edge.

Why it exists:

- every query in this challenge must be org-scoped
- prevents cross-tenant leakage
- supports efficient filtering during traversal

### `edgeClass`

The high-level category of the edge.

Allowed values:

- `operational`
- `semantic`
- `analytical`

Why it exists:

- allows graph traversals to include or exclude certain layers
- separates source-of-truth relationships from computed relationships

### `origin`

How the edge was created.

Allowed values:

- `user`
- `ingestion`
- `system-batch`

Why it exists:

- supports auditing
- distinguishes data-ingested edges from batch-generated edges
- makes debugging and maintenance easier

### `type`

The semantic relationship label.

Examples:

- `CITES_STANDARD`
- `HAS_ACTION_ITEM`
- `GOVERNED_BY_POLICY`
- `TRACKS_FINDING`
- `SIMILAR_TO`

Why it exists:

- preserves relationship meaning
- allows queries to reason about relationship semantics rather than generic references

### `from`

The source side of the directed edge.

Fields:

- `from.entityType`
- `from.entityId`

Why it exists:

- stores the origin node of the relationship
- supports forward traversal

### `to`

The target side of the directed edge.

Fields:

- `to.entityType`
- `to.entityId`

Why it exists:

- stores the destination node of the relationship
- supports reverse traversal when indexed properly

## Current Operational Relationship Types

### From `findings`

- `standardRefs` -> `CITES_STANDARD`
- `actionItemRefs` -> `HAS_ACTION_ITEM`
- `policyRefs` -> `GOVERNED_BY_POLICY`

### From `action_items`

- `findingRefs` -> `ADDRESSES_FINDING`
- `policyRefs` -> `IMPLEMENTS_POLICY`
- `standardRefs` -> `IMPLEMENTS_STANDARD`

### From `policies`

- `standardRefs` -> `ALIGNS_WITH_STANDARD`

### From `quality_objectives`

- `findingRefs` -> `TRACKS_FINDING`
- `policyRefs` -> `SUPPORTS_POLICY`
- `standardRefs` -> `TARGETS_STANDARD`

### From `events`

- `findingRefs` -> `RELATES_TO_FINDING`
- `actionItemRefs` -> `RELATES_TO_ACTION_ITEM`
- `policyRefs` -> `RELATES_TO_POLICY`
- `standardRefs` -> `RELATES_TO_STANDARD`

## Recommended Index Strategy

### 1. Unique index on `_id`

MongoDB already indexes `_id` uniquely.

Why it matters:

- prevents duplicates
- supports idempotent inserts/upserts
- makes reruns safe

### 2. Forward traversal index

```js
{ orgId: 1, "from.entityType": 1, "from.entityId": 1, edgeClass: 1, type: 1 }
```

Why:

- supports queries that start from an entity and follow outgoing edges
- useful for neighborhood discovery and traversal expansion
- keeps org filter first for tenant isolation

### 3. Reverse traversal index

```js
{ orgId: 1, "to.entityType": 1, "to.entityId": 1, edgeClass: 1, type: 1 }
```

Why:

- supports reverse lookups such as “what points to this standard?”
- important for impact analysis and blast-radius queries

### 4. Org-scoped edge extraction index

```js
{ orgId: 1, edgeClass: 1, type: 1 }
```

Why:

- supports queries that extract a subgraph for a single org
- helps filter operational vs analytical edges quickly
- useful for dashboards and summary analytics

### 5. Analytical similarity index

```js
{ orgId: 1, edgeClass: 1, type: 1, "from.entityType": 1 }
```

Why:

- supports clustering and similarity analysis
- makes it easier to isolate `SIMILAR_TO` analytical edges
- helpful for batch processing and connected-component logic

## Multi-Tenancy Design Choice

Each edge is stored with one `orgId`, and every query must filter by org. This keeps graph traversals tenant-safe and prevents users from seeing data belonging only to another facility.

This design favors safety and query simplicity over maximum flexibility. In a more advanced production design, there might also be edge visibility metadata derived from `dataOrgIds` or `applicableOrgIds`, but for this challenge the main rule is that graph access must remain org-scoped.

## Tradeoffs vs a Native Graph Database

MongoDB can represent graph relationships effectively, but it does not give graph features for free.

### What MongoDB handles well

- flexible document schema
- easy co-location of source entities and edge documents
- good support for tenant scoping with compound indexes
- straightforward ingestion pipelines in Python

### What is harder in MongoDB

- recursive traversal is more awkward than in a graph database
- performance depends more on careful index design
- connected-component and graph analytics are less natural
- relationship semantics and reverse traversal must be engineered manually

### What a graph database would give more naturally

A native graph database such as Neo4j or Amazon Neptune would provide:

- first-class nodes and edges
- native traversal engines optimized for multi-hop exploration
- simpler pattern-matching queries
- graph algorithms like connected components more directly
- less manual work around reverse traversal and traversal indexes

### Why MongoDB still works here

MongoDB is still a reasonable choice for this challenge because the graph is moderate in size, the source data is already document-oriented, and the assignment is specifically testing the ability to engineer a graph access layer on top of a document store.

## Summary

The `graph_edges` schema is designed to support:

- explicit directed relationships
- org-scoped graph traversal
- idempotent ingestion
- future analytical and semantic edges
- forward and reverse query patterns

This design makes MongoDB behave like a lightweight graph layer while preserving the document-oriented structure of the original healthcare quality management data.
