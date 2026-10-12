FROM node:24-bookworm-slim AS photon
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

FROM python:3.12-slim-bookworm
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libstdc++6 && rm -rf /var/lib/apt/lists/*
COPY --from=photon /usr/local/bin/node /usr/local/bin/node
COPY --from=photon /build/node_modules /app/node_modules
COPY requirements.lock.txt .
RUN pip install --no-cache-dir -r requirements.lock.txt
COPY app app
COPY web web
COPY integrations/photon integrations/photon
COPY run.py .
COPY deploy/container_start.py deploy/container_start.py
COPY scripts/provision.py scripts/provision.py
ENV TGTOP_HOST=0.0.0.0 TGTOP_PORT=8765 TGTOP_DATA=/data
RUN useradd --create-home tgtop && mkdir /data && chown tgtop:tgtop /data
USER tgtop
VOLUME /data
EXPOSE 8765
ENTRYPOINT ["python", "/app/deploy/container_start.py"]
CMD ["python", "run.py"]
