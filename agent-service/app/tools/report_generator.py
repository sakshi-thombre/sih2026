def report_generator(title: str, data: list) -> dict:
    """
    Creates a structured report from tool results.
    """

    report = {
        "title": title,
        "total_records": len(data),
        "records": data
    }

    return report
