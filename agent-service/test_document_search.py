from app.tools.document_search import document_search


results = document_search("Unit 3 safety incident")

print("SEARCH RESULTS")
print("=" * 40)

for document in results:
    print(f"ID: {document['id']}")
    print(f"Title: {document['title']}")
    print(f"Type: {document['type']}")
    print(f"Content: {document['content']}")
    print()

