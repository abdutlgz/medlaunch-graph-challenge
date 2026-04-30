import json
import os
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient


BASE_DIR = Path(__file__).resolve().parent.parent
# Seed files
SEED_DATA_DIR = BASE_DIR / "seed-data"

COLLECTION_FILES = {
    "standards": "standards.json",
    "findings": "findings.json",
    "action_items": "action_items.json",
    "policies": "policies.json",
    "quality_objectives": "quality_objectives.json",
    "events": "events.json",
}

ENTITY_TYPE_MAP = {
    "standards": "standard",
    "findings": "finding",
    "action_items": "action_item",
    "policies": "policy",
    "quality_objectives": "quality_objective",
    "events": "event",
}

REFERENCE_RULES = {
    "findings": {
        "standardRefs": ("standard", "CITES_STANDARD"),
        "actionItemRefs": ("action_item", "HAS_ACTION_ITEM"),
        "policyRefs": ("policy", "GOVERNED_BY_POLICY"),
    },
    "action_items": {
        "findingRefs": ("finding", "ADDRESSES_FINDING"),
        "policyRefs": ("policy", "IMPLEMENTS_POLICY"),
        "standardRefs": ("standard", "IMPLEMENTS_STANDARD"),
    },
    "policies": {
        "standardRefs": ("standard", "ALIGNS_WITH_STANDARD"),
    },
    "quality_objectives": {
        "findingRefs": ("finding", "TRACKS_FINDING"),
        "policyRefs": ("policy", "SUPPORTS_POLICY"),
        "standardRefs": ("standard", "TARGETS_STANDARD"),
    },
    "events": {
        "findingRefs": ("finding", "RELATES_TO_FINDING"),
        "actionItemRefs": ("action_item", "RELATES_TO_ACTION_ITEM"),
        "policyRefs": ("policy", "RELATES_TO_POLICY"),
        "standardRefs": ("standard", "RELATES_TO_STANDARD"),
    },
}


def get_database():
    load_dotenv()
    mongo_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017/medlaunch_challenge")
    client = MongoClient(mongo_uri)
    return client.get_default_database()


def load_json_file(filename):
    file_path = SEED_DATA_DIR / filename
    with open(file_path, "r", encoding="utf-8") as file:
        return json.load(file)


def load_all_seed_data():
    seed_data = {}

    for collection_name, filename in COLLECTION_FILES.items():
        seed_data[collection_name] = load_json_file(filename)

    return seed_data


def seed_entities(db, seed_data):
    total_inserted = 0

    for collection_name, documents in seed_data.items():
        collection = db[collection_name]
        collection.delete_many({})

        if documents:
            collection.insert_many(documents)

        print(f"Seeded {len(documents)} documents into {collection_name}")
        total_inserted += len(documents)

    return total_inserted


def verify_entity_counts(db):
    total_count = 0

    for collection_name in COLLECTION_FILES:
        count = db[collection_name].count_documents({})
        print(f"Verified {collection_name}: {count} documents in MongoDB")
        total_count += count

    print(f"Verified total entities in MongoDB: {total_count}")


def build_entity_id_lookup(seed_data):
    # Valid targets
    entity_lookup = {}

    for collection_name, documents in seed_data.items():
        entity_type = ENTITY_TYPE_MAP[collection_name]
        entity_lookup[entity_type] = {document["_id"] for document in documents}

    return entity_lookup


def build_operational_edges(seed_data, entity_lookup):
    # Edge builder
    edges = []
    skipped_references = []

    for collection_name, documents in seed_data.items():
        source_entity_type = ENTITY_TYPE_MAP[collection_name]
        reference_rules = REFERENCE_RULES.get(collection_name, {})

        for document in documents:
            source_id = document["_id"]
            org_id = document["orgId"]

            for ref_field, (target_entity_type, relationship_type) in reference_rules.items():
                target_ids = document.get(ref_field, [])

                for target_id in target_ids:
                    if target_id not in entity_lookup[target_entity_type]:
                        skipped_references.append(
                            {
                                "sourceCollection": collection_name,
                                "sourceEntityType": source_entity_type,
                                "sourceId": source_id,
                                "refField": ref_field,
                                "targetEntityType": target_entity_type,
                                "targetId": target_id,
                                "reason": "missing target document",
                            }
                        )
                        continue

                    edge = {
                        "_id": f"operational|{org_id}|{source_entity_type}|{source_id}|{relationship_type}|{target_entity_type}|{target_id}",
                        "orgId": org_id,
                        "edgeClass": "operational",
                        "origin": "ingestion",
                        "type": relationship_type,
                        "from": {
                            "entityType": source_entity_type,
                            "entityId": source_id,
                        },
                        "to": {
                            "entityType": target_entity_type,
                            "entityId": target_id,
                        },
                    }
                    edges.append(edge)

    return edges, skipped_references


def seed_graph_edges(db, edges):
    collection = db["graph_edges"]
    collection.delete_many({})

    if edges:
        collection.insert_many(edges)

    print(f"Seeded {len(edges)} documents into graph_edges")


def verify_graph_edge_count(db):
    count = db["graph_edges"].count_documents({})
    print(f"Verified graph_edges: {count} documents in MongoDB")


def print_seed_summary(total_entities_inserted, total_edges_created, skipped_references):
    print("\nSeed Summary")
    print(f"Total entities inserted: {total_entities_inserted}")
    print(f"Total edges created: {total_edges_created}")
    print(f"Skipped references: {len(skipped_references)}")

    if skipped_references:
        print("Sample skipped references:")
        for skipped_reference in skipped_references[:5]:
            print(skipped_reference)


def main():
    db = get_database()
    seed_data = load_all_seed_data()
    entity_lookup = build_entity_id_lookup(seed_data)

    print(f"Connected to database: {db.name}")

    total_inserted = seed_entities(db, seed_data)
    verify_entity_counts(db)

    operational_edges, skipped_references = build_operational_edges(seed_data, entity_lookup)
    print(f"Built {len(operational_edges)} operational edges")

    for edge in operational_edges[:5]:
        print(edge)

    seed_graph_edges(db, operational_edges)
    verify_graph_edge_count(db)
    print_seed_summary(total_inserted, len(operational_edges), skipped_references)


if __name__ == "__main__":
    main()
