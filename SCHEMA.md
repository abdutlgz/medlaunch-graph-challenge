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
