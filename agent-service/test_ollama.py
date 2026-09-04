import asyncio

from app.ollama_client import OllamaClient


async def main():
    client = OllamaClient()

    response = await client.generate(
        "Explain what an SOP is in one sentence."
    )

    print("QWEN RESPONSE:")
    print(response)


if __name__ == "__main__":
    asyncio.run(main())
