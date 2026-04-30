import os
from collections import defaultdict
from datetime import datetime, timezone

from dotenv import load_dotenv
from pymongo import MongoClient


ENTITY_COLLECTION_MAP = {
    "finding": "findings",
    "action_item": "action_items",
    "quality_objective": "quality_objectives",
    "event": "events",
}

SIMILARITY_EDGE_TYPE = "SIMILAR_TO"
SIMILARITY_SCORE_FORMULA = "(shared_tag_count + shared_standard_count) / (unique_tag_count + unique_standard_count)"


def get_database():
    load_dotenv()
    mongo_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017/medlaunch_challenge")
    client = MongoClient(mongo_uri)
    return client.get_default_database()


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_similarity_candidates(db):
    # Batch inputs
    candidates_by_type_and_org = defaultdict(list)

    for entity_type, collection_name in ENTITY_COLLECTION_MAP.items():
        documents = list(db[collection_name].find({}))

        for document in documents:
            candidate = {
                "entityType": entity_type,
                "entityId": document["_id"],
                "title": document.get("title"),
                "orgId": document["orgId"],
                "tags": set(document.get("tags", [])),
                "standardRefs": set(document.get("standardRefs", [])),
            }

            candidates_by_type_and_org[(entity_type, document["orgId"])].append(candidate)

    return candidates_by_type_and_org


def calculate_similarity(candidate_a, candidate_b):
    shared_tags = sorted(candidate_a["tags"] & candidate_b["tags"])
    shared_standards = sorted(candidate_a["standardRefs"] & candidate_b["standardRefs"])

    if len(shared_tags) < 2:
        return None

    if len(shared_standards) < 1:
        return None

    unique_tags = candidate_a["tags"] | candidate_b["tags"]
    unique_standards = candidate_a["standardRefs"] | candidate_b["standardRefs"]
    denominator = len(unique_tags) + len(unique_standards)

    score = 0.0
    if denominator > 0:
        score = round((len(shared_tags) + len(shared_standards)) / denominator, 4)

    return {
        "sharedTags": shared_tags,
        "sharedStandards": shared_standards,
        "sharedTagCount": len(shared_tags),
        "sharedStandardCount": len(shared_standards),
        "similarityScore": score,
        "scoreFormula": SIMILARITY_SCORE_FORMULA,
    }


def build_similarity_edge(source, target, similarity, timestamp):
    return {
        "_id": f"analytical|{source['orgId']}|{source['entityType']}|{source['entityId']}|{SIMILARITY_EDGE_TYPE}|{target['entityType']}|{target['entityId']}",
        "orgId": source["orgId"],
        "edgeClass": "analytical",
        "origin": "system-batch",
        "type": SIMILARITY_EDGE_TYPE,
        "from": {
            "entityType": source["entityType"],
            "entityId": source["entityId"],
        },
        "to": {
            "entityType": target["entityType"],
            "entityId": target["entityId"],
        },
        "similarityScore": similarity["similarityScore"],
        "sharedTagCount": similarity["sharedTagCount"],
        "sharedStandardCount": similarity["sharedStandardCount"],
        "sharedTags": similarity["sharedTags"],
        "sharedStandardRefs": similarity["sharedStandards"],
        "scoreFormula": similarity["scoreFormula"],
        "updatedAt": timestamp,
    }


def build_desired_similarity_edges(candidates_by_type_and_org):
    # Same-type pairs
    desired_edges = {}
    pairs_evaluated = 0
    timestamp = utc_now()

    for (_, _), candidates in candidates_by_type_and_org.items():
        sorted_candidates = sorted(candidates, key=lambda item: item["entityId"])

        for index, candidate_a in enumerate(sorted_candidates):
            for candidate_b in sorted_candidates[index + 1 :]:
                pairs_evaluated += 1
                similarity = calculate_similarity(candidate_a, candidate_b)

                if not similarity:
                    continue

                edge_ab = build_similarity_edge(candidate_a, candidate_b, similarity, timestamp)
                edge_ba = build_similarity_edge(candidate_b, candidate_a, similarity, timestamp)
                desired_edges[edge_ab["_id"]] = edge_ab
                desired_edges[edge_ba["_id"]] = edge_ba

    return desired_edges, pairs_evaluated


def normalize_edge_for_comparison(edge):
    comparable = dict(edge)
    comparable.pop("updatedAt", None)
    return comparable


def sync_similarity_edges(db, desired_edges):
    graph_edges = db["graph_edges"]
    existing_edges = list(
        graph_edges.find(
            {
                "edgeClass": "analytical",
                "origin": "system-batch",
                "type": SIMILARITY_EDGE_TYPE,
            }
        )
    )

    existing_by_id = {edge["_id"]: edge for edge in existing_edges}
    desired_ids = set(desired_edges)
    existing_ids = set(existing_by_id)

    created_count = 0
    updated_count = 0

    for edge_id, desired_edge in desired_edges.items():
        existing_edge = existing_by_id.get(edge_id)

        if existing_edge is None:
            graph_edges.insert_one(desired_edge)
            created_count += 1
            continue

        if normalize_edge_for_comparison(existing_edge) != normalize_edge_for_comparison(desired_edge):
            graph_edges.replace_one({"_id": edge_id}, desired_edge)
            updated_count += 1

    stale_ids = sorted(existing_ids - desired_ids)
    removed_count = 0
    if stale_ids:
        result = graph_edges.delete_many({"_id": {"$in": stale_ids}})
        removed_count = result.deleted_count

    return created_count, updated_count, removed_count


def main():
    db = get_database()
    print(f"Connected to database: {db.name}")

    candidates_by_type_and_org = load_similarity_candidates(db)
    desired_edges, pairs_evaluated = build_desired_similarity_edges(candidates_by_type_and_org)
    created_count, updated_count, removed_count = sync_similarity_edges(db, desired_edges)

    print("\nAnalytical Edge Batch Summary")
    print(f"Entity pairs evaluated: {pairs_evaluated}")
    print(f"SIMILAR_TO edges created: {created_count}")
    print(f"SIMILAR_TO edges updated: {updated_count}")
    print(f"Stale SIMILAR_TO edges removed: {removed_count}")
    print(f"Current analytical SIMILAR_TO edges: {len(desired_edges)}")


if __name__ == "__main__":
    main()
