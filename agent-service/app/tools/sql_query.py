INCIDENTS = [
    {
        "id": 1,
        "unit": "Unit 3",
        "date": "2026-02-15",
        "type": "Pressure Leak",
        "severity": "High",
        "description": "Pressure leak detected in process line."
    },
    {
        "id": 2,
        "unit": "Unit 3",
        "date": "2026-04-10",
        "type": "Equipment Failure",
        "severity": "Medium",
        "description": "Pump vibration exceeded normal operating limits."
    },
    {
        "id": 3,
        "unit": "Unit 2",
        "date": "2026-05-20",
        "type": "Safety Violation",
        "severity": "Low",
        "description": "Required PPE was not used during maintenance."
    },
]


def sql_query(query: str) -> list:
    """
    Mock SQL query tool.

    Later this function will execute a real SQL query
    against the internal PostgreSQL database.
    """

    query_lower = query.lower()

    results = INCIDENTS

    if "unit 3" in query_lower:
        results = [
            incident
            for incident in results
            if incident["unit"].lower() == "unit 3"
        ]

    if "high" in query_lower:
        results = [
            incident
            for incident in results
            if incident["severity"].lower() == "high"
        ]

    return results

