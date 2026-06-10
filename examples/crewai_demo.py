from __future__ import annotations

from memory_gateway.adapters.crewai import MemorySearchTool
from memory_gateway.client import MemoryGatewayClient


def main() -> None:
    tool = MemorySearchTool(client=MemoryGatewayClient(api_key="backend-demo-key"))
    print(tool._run("What database should we use for long-term agent memory?"))


if __name__ == "__main__":
    main()

