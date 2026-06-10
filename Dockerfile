FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY memory_gateway ./memory_gateway
COPY examples ./examples
RUN python -m pip install --no-cache-dir -e ".[postgres,mcp]"

EXPOSE 8000
CMD ["python", "-m", "memory_gateway.api.main"]

