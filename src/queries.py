import json
import os
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient


BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"

ENTITY_COLLECTION_MAP = {
    "standard": "standards",
    "finding": "findings",
    "action_item": "action_items",
    "policy": "policies",
    "quality_objective": "quality_objectives",
    "event": "events",
}

IMPACT_ENTITY_TYPES = {"finding", "action_item", "policy", "quality_objective"}


def get_database():
    load_dotenv()
    mongo_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017/medlaunch_challenge")
    client = MongoClient(mongo_uri)
    return client.get_default_database()


def ensure_output_directory():
    OUTPUT_DIR.mkdir(exist_ok=True)


def fetch_entity_summary(db, entity_type, entity_id):
    collection_name = ENTITY_COLLECTION_MAP[entity_type]
    document = db[collection_name].find_one({"_id": entity_id})

    if not document:
        return {
            "entityType": entity_type,
            "entityId": entity_id,
            "title": None,
            "orgId": None,
        }

    return {
        "entityType": entity_type,
        "entityId": entity_id,
        "title": document.get("title"),
        "orgId": document.get("orgId"),
    }


def fetch_entity_document(db, entity_type, entity_id):
    collection_name = ENTITY_COLLECTION_MAP[entity_type]
    return db[collection_name].find_one({"_id": entity_id})


def is_entity_visible_to_org(document, org_id):
    # Visibility check
    if not document:
        return False

    if document.get("orgId") == org_id:
        return True

    if org_id in document.get("dataOrgIds", []):
        return True

    if org_id in document.get("applicableOrgIds", []):
        return True

    return False


def query_org_scoped_subgraph(db, org_id):
    edges = list(db["graph_edges"].find({"orgId": org_id}).sort([("_id", 1)]))
    visible_edges = []

    for edge in edges:
        source_document = fetch_entity_document(db, edge["from"]["entityType"], edge["from"]["entityId"])
        target_document = fetch_entity_document(db, edge["to"]["entityType"], edge["to"]["entityId"])

        if not is_entity_visible_to_org(source_document, org_id):
            continue

        if not is_entity_visible_to_org(target_document, org_id):
            continue

        visible_edges.append(
            {
                "edgeId": edge["_id"],
                "orgId": edge["orgId"],
                "edgeClass": edge["edgeClass"],
                "type": edge["type"],
                "source": fetch_entity_summary(db, edge["from"]["entityType"], edge["from"]["entityId"]),
                "target": fetch_entity_summary(db, edge["to"]["entityType"], edge["to"]["entityId"]),
            }
        )

    return {
        "orgId": org_id,
        "edgeCount": len(visible_edges),
        "edges": visible_edges,
    }


def get_node_key(entity_type, entity_id):
    return f"{entity_type}|{entity_id}"


def query_standard_impact_analysis(db, standard_id):
    # Blast radius
    standard_summary = fetch_entity_summary(db, "standard", standard_id)
    edges_collection = db["graph_edges"]

    first_hop_edges = list(
        edges_collection.find(
            {
                "edgeClass": "operational",
                "$or": [
                    {"to.entityType": "standard", "to.entityId": standard_id},
                    {"from.entityType": "standard", "from.entityId": standard_id},
                ],
            }
        )
    )

    impacted_entities = {}
    first_hop_nodes = {}

    for edge in first_hop_edges:
        if edge["from"]["entityType"] == "standard" and edge["from"]["entityId"] == standard_id:
            neighbor = edge["to"]
        else:
            neighbor = edge["from"]

        if neighbor["entityType"] not in IMPACT_ENTITY_TYPES:
            continue

        node_key = get_node_key(neighbor["entityType"], neighbor["entityId"])
        path = [edge["type"]]

        if node_key not in impacted_entities:
            impacted_entities[node_key] = {
                "entity": fetch_entity_summary(db, neighbor["entityType"], neighbor["entityId"]),
                "hopCount": 1,
                "paths": [],
            }

        if path not in impacted_entities[node_key]["paths"]:
            impacted_entities[node_key]["paths"].append(path)

        if node_key not in first_hop_nodes:
            first_hop_nodes[node_key] = {
                "entityType": neighbor["entityType"],
                "entityId": neighbor["entityId"],
                "pathsFromStandard": [],
            }

        if path not in first_hop_nodes[node_key]["pathsFromStandard"]:
            first_hop_nodes[node_key]["pathsFromStandard"].append(path)

    for first_hop_node in first_hop_nodes.values():
        connected_edges = list(
            edges_collection.find(
                {
                    "edgeClass": "operational",
                    "$or": [
                        {
                            "from.entityType": first_hop_node["entityType"],
                            "from.entityId": first_hop_node["entityId"],
                        },
                        {
                            "to.entityType": first_hop_node["entityType"],
                            "to.entityId": first_hop_node["entityId"],
                        },
                    ],
                }
            )
        )

        for edge in connected_edges:
            if (
                edge["from"]["entityType"] == first_hop_node["entityType"]
                and edge["from"]["entityId"] == first_hop_node["entityId"]
            ):
                neighbor = edge["to"]
            else:
                neighbor = edge["from"]

            if neighbor["entityType"] == "standard" and neighbor["entityId"] == standard_id:
                continue

            if neighbor["entityType"] not in IMPACT_ENTITY_TYPES:
                continue

            node_key = get_node_key(neighbor["entityType"], neighbor["entityId"])

            if node_key not in impacted_entities:
                impacted_entities[node_key] = {
                    "entity": fetch_entity_summary(db, neighbor["entityType"], neighbor["entityId"]),
                    "hopCount": 2,
                    "paths": [],
                }

            impacted_entities[node_key]["hopCount"] = min(impacted_entities[node_key]["hopCount"], 2)

            for first_hop_path in first_hop_node["pathsFromStandard"]:
                path = first_hop_path + [edge["type"]]
                if path not in impacted_entities[node_key]["paths"]:
                    impacted_entities[node_key]["paths"].append(path)

    grouped_results = {}
    for entity_type in sorted(IMPACT_ENTITY_TYPES):
        grouped_results[entity_type] = {
            "count": 0,
            "entities": [],
        }

    for impacted in impacted_entities.values():
        entity_type = impacted["entity"]["entityType"]
        grouped_results[entity_type]["entities"].append(impacted)

    for entity_type, group in grouped_results.items():
        group["entities"].sort(key=lambda item: item["entity"]["entityId"])
        group["count"] = len(group["entities"])

    total_impacted_entities = sum(group["count"] for group in grouped_results.values())

    return {
        "standard": standard_summary,
        "totalImpactedEntities": total_impacted_entities,
        "impactedByType": grouped_results,
    }


def query_multi_hop_neighbor_discovery(db, finding_id):
    # Two hops
    finding = db["findings"].find_one({"_id": finding_id})
    if not finding:
        return {
            "findingId": finding_id,
            "error": "Finding not found",
        }

    org_id = finding["orgId"]
    pipeline = [
        {"$match": {"_id": finding_id}},
        {
            "$graphLookup": {
                "from": "graph_edges",
                "startWith": "$_id",
                "connectFromField": "to.entityId",
                "connectToField": "from.entityId",
                "as": "traversedEdges",
                "maxDepth": 1,
                "depthField": "depth",
                "restrictSearchWithMatch": {
                    "orgId": org_id,
                    "edgeClass": "operational",
                },
            }
        },
    ]

    result = list(db["findings"].aggregate(pipeline))
    traversed_edges = result[0]["traversedEdges"] if result else []

    adjacency = {}
    for edge in traversed_edges:
        source_key = get_node_key(edge["from"]["entityType"], edge["from"]["entityId"])
        adjacency.setdefault(source_key, []).append(edge)

    start_key = get_node_key("finding", finding_id)
    frontier = [(start_key, [])]
    visited_paths = {}

    while frontier:
        current_key, current_path = frontier.pop(0)
        current_hops = len(current_path)

        if current_hops == 2:
            continue

        for edge in adjacency.get(current_key, []):
            next_key = get_node_key(edge["to"]["entityType"], edge["to"]["entityId"])
            next_path = current_path + [edge["type"]]

            if next_key not in visited_paths:
                visited_paths[next_key] = []

            if next_path not in visited_paths[next_key]:
                visited_paths[next_key].append(next_path)

            frontier.append((next_key, next_path))

    reachable_entities = []
    for node_key, paths in visited_paths.items():
        entity_type, entity_id = node_key.split("|", 1)

        if entity_type == "finding" and entity_id == finding_id:
            continue

        summary = fetch_entity_summary(db, entity_type, entity_id)
        reachable_entities.append(
            {
                "entity": summary,
                "hopCount": min(len(path) for path in paths),
                "paths": sorted(paths, key=lambda path: (len(path), path)),
            }
        )

    reachable_entities.sort(
        key=lambda item: (
            item["hopCount"],
            item["entity"]["entityType"],
            item["entity"]["entityId"],
        )
    )

    return {
        "startEntity": fetch_entity_summary(db, "finding", finding_id),
        "orgId": org_id,
        "reachableEntityCount": len(reachable_entities),
        "entities": reachable_entities,
    }


def query_fan_out_by_edge_class(db):
    pipeline = [
        {
            "$project": {
                "edgeClass": 1,
                "endpoints": [
                    {
                        "entityType": "$from.entityType",
                        "entityId": "$from.entityId",
                    },
                    {
                        "entityType": "$to.entityType",
                        "entityId": "$to.entityId",
                    },
                ],
            }
        },
        {"$unwind": "$endpoints"},
        {
            "$group": {
                "_id": {
                    "entityType": "$endpoints.entityType",
                    "entityId": "$endpoints.entityId",
                    "edgeClass": "$edgeClass",
                },
                "edgeCount": {"$sum": 1},
            }
        },
        {
            "$group": {
                "_id": {
                    "entityType": "$_id.entityType",
                    "entityId": "$_id.entityId",
                },
                "countsByEdgeClass": {
                    "$push": {
                        "edgeClass": "$_id.edgeClass",
                        "count": "$edgeCount",
                    }
                },
                "totalEdgeCount": {"$sum": "$edgeCount"},
            }
        },
        {"$sort": {"totalEdgeCount": -1, "_id.entityId": 1}},
        {"$limit": 5},
    ]

    results = list(db["graph_edges"].aggregate(pipeline))

    formatted_results = []
    for result in results:
        entity_type = result["_id"]["entityType"]
        entity_id = result["_id"]["entityId"]
        summary = fetch_entity_summary(db, entity_type, entity_id)

        counts = {item["edgeClass"]: item["count"] for item in result["countsByEdgeClass"]}
        formatted_results.append(
            {
                "entity": summary,
                "countsByEdgeClass": counts,
                "totalEdgeCount": result["totalEdgeCount"],
            }
        )

    return formatted_results


def write_output(filename, data):
    ensure_output_directory()
    output_path = OUTPUT_DIR / filename

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)

    print(f"Wrote output to {output_path}")


def main():
    db = get_database()
    print(f"Connected to database: {db.name}")

    multi_hop_results = query_multi_hop_neighbor_discovery(db, "FND-002")
    print("\nQuery 1: Multi-Hop Neighbor Discovery")
    print(json.dumps(multi_hop_results, indent=2))

    write_output("query1_multi_hop_fnd_002.json", multi_hop_results)

    standard_impact_results = query_standard_impact_analysis(db, "STD-002")
    print("\nQuery 2: Standard Impact Analysis")
    print(json.dumps(standard_impact_results, indent=2))

    write_output("query2_standard_impact_std_002.json", standard_impact_results)

    org_subgraph_results = query_org_scoped_subgraph(db, "ORG-MCLEOD-DILLON")
    print("\nQuery 3: Org-Scoped Subgraph Extraction")
    print(json.dumps(org_subgraph_results, indent=2))

    write_output("query3_org_scoped_subgraph_dillon.json", org_subgraph_results)

    fan_out_results = query_fan_out_by_edge_class(db)
    print("\nQuery 4: Fan-Out by Edge Class")
    print(json.dumps(fan_out_results, indent=2))

    write_output("query4_fan_out_by_edge_class.json", fan_out_results)


if __name__ == "__main__":
    main()
