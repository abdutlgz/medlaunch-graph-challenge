import os
import json
from collections import Counter, defaultdict, deque
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient


BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"

ENTITY_COLLECTION_MAP = {
    "finding": "findings",
    "action_item": "action_items",
    "quality_objective": "quality_objectives",
    "event": "events",
}


def get_database():
    load_dotenv()
    mongo_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017/medlaunch_challenge")
    client = MongoClient(mongo_uri)
    return client.get_default_database()


def get_node_key(entity_type, entity_id):
    return f"{entity_type}|{entity_id}"


def parse_node_key(node_key):
    return node_key.split("|", 1)


def fetch_entity_document(db, entity_type, entity_id):
    collection_name = ENTITY_COLLECTION_MAP[entity_type]
    return db[collection_name].find_one({"_id": entity_id})


def load_similarity_graph(db):
    # Similarity layer
    edges = list(
        db["graph_edges"].find(
            {
                "edgeClass": "analytical",
                "origin": "system-batch",
                "type": "SIMILAR_TO",
            }
        )
    )

    adjacency = defaultdict(set)
    edge_pairs = set()

    for edge in edges:
        source_key = get_node_key(edge["from"]["entityType"], edge["from"]["entityId"])
        target_key = get_node_key(edge["to"]["entityType"], edge["to"]["entityId"])

        adjacency[source_key].add(target_key)
        adjacency[target_key].add(source_key)
        edge_pairs.add(tuple(sorted((source_key, target_key))))

    return adjacency, edge_pairs


def compute_connected_components(adjacency):
    # BFS clusters
    visited = set()
    components = []

    for start_node in sorted(adjacency):
        if start_node in visited:
            continue

        queue = deque([start_node])
        component_nodes = []
        visited.add(start_node)

        while queue:
            node = queue.popleft()
            component_nodes.append(node)

            for neighbor in sorted(adjacency[node]):
                if neighbor in visited:
                    continue

                visited.add(neighbor)
                queue.append(neighbor)

        components.append(sorted(component_nodes))

    return components


def build_cluster_document(db, cluster_number, component_nodes, edge_pairs):
    members = []
    tag_counter = Counter()

    for node_key in component_nodes:
        entity_type, entity_id = parse_node_key(node_key)
        document = fetch_entity_document(db, entity_type, entity_id)
        tags = document.get("tags", []) if document else []
        tag_counter.update(tags)
        members.append(
            {
                "entityType": entity_type,
                "entityId": entity_id,
            }
        )

    component_node_set = set(component_nodes)
    internal_edge_count = sum(
        1 for edge_pair in edge_pairs if edge_pair[0] in component_node_set and edge_pair[1] in component_node_set
    )

    representative_label = None
    if tag_counter:
        representative_label = sorted(tag_counter.items(), key=lambda item: (-item[1], item[0]))[0][0]

    return {
        "_id": f"cluster-{cluster_number:03d}",
        "memberCount": len(members),
        "members": members,
        "internalEdgeCount": internal_edge_count,
        "representativeLabel": representative_label,
    }


def rebuild_clusters(db):
    adjacency, edge_pairs = load_similarity_graph(db)
    components = compute_connected_components(adjacency)
    cluster_documents = []

    for index, component_nodes in enumerate(components, start=1):
        cluster_documents.append(build_cluster_document(db, index, component_nodes, edge_pairs))

    clusters_collection = db["clusters"]
    clusters_collection.delete_many({})

    if cluster_documents:
        clusters_collection.insert_many(cluster_documents)

    return cluster_documents


def print_cluster_summary(cluster_documents):
    size_distribution = Counter(cluster["memberCount"] for cluster in cluster_documents)

    print("\nCluster Summary")
    print(f"Number of clusters: {len(cluster_documents)}")
    print(f"Size distribution: {dict(sorted(size_distribution.items()))}")

    for cluster in cluster_documents:
        print(
            f"{cluster['_id']}: size={cluster['memberCount']}, "
            f"internalEdgeCount={cluster['internalEdgeCount']}, "
            f"representativeLabel={cluster['representativeLabel']}"
        )


def write_cluster_output(cluster_documents):
    OUTPUT_DIR.mkdir(exist_ok=True)
    output_path = OUTPUT_DIR / "clusters.json"

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(cluster_documents, file, indent=2)

    print(f"Wrote output to {output_path}")


def main():
    db = get_database()
    print(f"Connected to database: {db.name}")

    cluster_documents = rebuild_clusters(db)
    print_cluster_summary(cluster_documents)
    write_cluster_output(cluster_documents)


if __name__ == "__main__":
    main()
