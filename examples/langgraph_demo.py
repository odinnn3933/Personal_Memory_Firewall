from __future__ import annotations

from memory_gateway.adapters.langgraph import memory_context_node
from memory_gateway.client import MemoryGatewayClient


def main() -> None:
    client = MemoryGatewayClient(api_key="backend-demo-key")
    node = memory_context_node(client)
    state = {"input": "What database should we use for long-term agent memory?"}
    print(node(state)["memory_context"])


if __name__ == "__main__":
    main()

