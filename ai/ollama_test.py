print("SCRIPT STARTED")

import json
import urllib.request

print("IMPORTS WORKED")

url = "http://localhost:11434/api/chat"

data = {
    "model": "qwen3:8b",
    "messages": [
        {
            "role": "user",
            "content": "Say hello in one sentence."
        }
    ],
    "stream": False
}

print("ABOUT TO CALL OLLAMA")

request = urllib.request.Request(
    url,
    data=json.dumps(data).encode("utf-8"),
    headers={"Content-Type": "application/json"}
)

with urllib.request.urlopen(request, timeout=120) as response:
    print("OLLAMA RESPONDED")
    result = json.loads(response.read().decode("utf-8"))

print(result["message"]["content"])