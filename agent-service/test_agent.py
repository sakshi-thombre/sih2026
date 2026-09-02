import asyncio

from app.agent import Agent


async def main():

    agent = Agent()

    task = (
        "Summarize all safety incidents in Unit 3 "
        "during the last 6 months."
    )

    print("\nCREATING PLAN")
    print("=" * 40)

    plan = await agent.create_plan(task)

    for step in plan.steps:
        print(f"\nStep {step.step}")
        print(f"Tool: {step.tool}")
        print(f"Action: {step.description}")

    print("\n\nEXECUTING PLAN")
    print("=" * 40)

    results = await agent.execute_plan(plan)

    for result in results:
        print(f"\nStep: {result['step']}")
        print(f"Tool: {result['tool']}")
        print(f"Description: {result['description']}")
        print(f"Result: {result['result']}")

    print("\n\nGENERATING FINAL ANSWER")
    print("=" * 40)

    final_answer = await agent.generate_final_answer(
        task,
        results
    )

    print("\nFINAL ANSWER")
    print("=" * 40)
    print(final_answer)


if __name__ == "__main__":
    asyncio.run(main())
