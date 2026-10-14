FROM node:24-bookworm-slim AS photon
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

FROM debian:bookworm-slim AS codex
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL https://github.com/openai/codex/releases/download/rust-v0.162.1/codex-x86_64-unknown-linux-musl.tar.gz -o /tmp/codex.tar.gz \
 && echo '86f268d81b898f3e144c5ecff2ad2fda2c5802e042d6195b72538fe0fa125057  /tmp/codex.tar.gz' | sha256sum -c - \
 && tar -xzf /tmp/codex.tar.gz -C /usr/local/bin codex-x86_64-unknown-linux-musl \
 && mv /usr/local/bin/codex-x86_64-unknown-linux-musl /usr/local/bin/tgtop-codex

FROM python:3.12-slim-bookworm
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libstdc++6 && rm -rf /var/lib/apt/lists/*
COPY --from=photon /usr/local/bin/node /usr/local/bin/node
COPY --from=photon /build/node_modules /app/node_modules
COPY --from=codex /usr/local/bin/tgtop-codex /usr/local/bin/tgtop-codex
COPY requirements.lock.txt .
RUN pip install --no-cache-dir -r requirements.lock.txt
COPY app app
COPY web web
COPY integrations/photon integrations/photon
COPY run.py .
COPY deploy/container_start.py deploy/container_start.py
COPY scripts/provision.py scripts/provision.py
ENV TGTOP_HOST=0.0.0.0 TGTOP_PORT=8765 TGTOP_DATA=/data
ENV TGTOP_CODEX_BIN=/usr/local/bin/tgtop-codex
RUN useradd --create-home tgtop && mkdir /data && chown tgtop:tgtop /data
USER tgtop
VOLUME /data
EXPOSE 8765
ENTRYPOINT ["python", "/app/deploy/container_start.py"]
CMD ["python", "run.py"]
