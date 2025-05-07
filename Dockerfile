FROM python:3.12.3-slim-bookworm

RUN set -eux; \
    apt-get update; \
    apt install python3-dev build-essential libvips-dev -y; \
    rm -rf /var/lib/apt/lists/*

WORKDIR /slender

COPY . ./

RUN set -eux; \
    pip install uv; \
    uv sync --frozen --all-extras

CMD ["make", "test"]
