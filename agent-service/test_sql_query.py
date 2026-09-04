from app.tools.sql_query import sql_query


results = sql_query(
    "Get all incidents from Unit 3"
)

print("SQL RESULTS")
print("=" * 40)

for incident in results:
    print(incident)

