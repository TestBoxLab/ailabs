# Build context is the repository root. This image never imports or runs Studio.
FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends openssl ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY monarch-benchmark/workflowbench/wb_repair /app/wb_repair
ENV PYTHONUNBUFFERED=1 GENESIS_REPAIR_HOST=0.0.0.0 GENESIS_REPAIR_DATA=/data
EXPOSE 8780
CMD ["python", "-m", "wb_repair.server"]
