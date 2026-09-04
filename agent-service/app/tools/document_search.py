DOCUMENTS = [
    {
        "id": "INC-001",
        "title": "Unit 3 Safety Incident Report",
        "content": (
            "A pressure leak was detected in Unit 3 during routine inspection. "
            "The affected valve was isolated and maintenance was notified."
        ),
        "unit": "Unit 3",
        "type": "incident",
    },
    {
        "id": "INC-002",
        "title": "Unit 3 Equipment Incident",
        "content": (
            "An abnormal vibration was detected in a pump in Unit 3. "
            "The pump was shut down for inspection."
        ),
        "unit": "Unit 3",
        "type": "incident",
    },
    {
        "id": "SOP-001",
        "title": "Unit 3 Startup Safety SOP",
        "content": (
            "Before startup, operators must verify equipment status, "
            "safety interlocks, emergency systems, and operating parameters."
        ),
        "unit": "Unit 3",
        "type": "sop",
    },
]


def document_search(query: str) -> list:
    query_words = query.lower().split()

    results = []

    for document in DOCUMENTS:
        searchable_text = (
            document["title"] + " " + document["content"]
        ).lower()

        if any(word in searchable_text for word in query_words):
            results.append(document)

    return results

