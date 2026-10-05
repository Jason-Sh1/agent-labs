# A minimal agent environment: the repo, Python, git, a non-root user, nothing else.
# Build from the agent-labs folder:
#   docker build -f lab5-sandbox/Dockerfile -t agent-lab .
# Run the harness with no network at all (mock model):
#   docker run --rm --network none agent-lab python3 lab1-harness/harness.py --repo sample-project --task "Fix all the failing tests" --mock --mode auto
# Run it with the real model (needs network to reach the API, and only that):
#   docker run --rm -e ANTHROPIC_API_KEY agent-lab python3 lab1-harness/harness.py --repo sample-project --task "Fix all the failing tests" --mode auto
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir anthropic \
    && useradd -m agent
WORKDIR /home/agent/labs
COPY --chown=agent:agent . .
USER agent
