FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Python 3, pip and the uWSGI Python 3 plugin, as documented in the README
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        uwsgi \
        uwsgi-plugin-python3 \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install pinned dependencies first so this layer is cached between code changes
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Build from the local source instead of cloning a remote repository
COPY main.py search_index.py LICENSE ./
COPY templates ./templates
COPY static ./static

# Run as an unprivileged user that owns the data directory (search index)
RUN useradd --system --no-create-home --shell /usr/sbin/nologin suds \
    && mkdir /data && chown suds:suds /data
ENV SUDS_DATA_DIR=/data
USER suds

EXPOSE 8001

# uWSGI treats SIGTERM as a reload; SIGINT makes it shut down
STOPSIGNAL SIGINT

# Build or refresh the search index before serving (a failure only logs, the
# app retries in the background), then hand PID 1 over to uWSGI
CMD ["sh", "-c", "python3 search_index.py; exec uwsgi --plugin python3 --http-socket 0.0.0.0:8001 --wsgi-file main.py --callable app --processes 4 --threads 2"]
