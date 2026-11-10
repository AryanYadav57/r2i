# R2I API (FastAPI + routing engine + fleet planner)
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install ".[api]"

COPY api ./api
COPY scripts ./scripts
COPY data/raw ./data/raw
COPY web/public/scenarios ./web/public/scenarios

# Fail the build early if the road graph is missing or broken (it is loaded at startup).
RUN python -c "from r2i.routing.router import load_routing_graph; G = load_routing_graph(); print(G.number_of_nodes(), 'nodes')"

ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT}"]
