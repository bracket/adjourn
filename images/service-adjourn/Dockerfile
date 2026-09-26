FROM ghcr.io/bracket/base-service-python-swipl:1.0.0

ENV PIP_INDEX_URL=http://host.docker.internal:7974/bracket/packages/+simple/
ENV PIP_TRUSTED_HOST=host.docker.internal

ENV ADJOURN_VERSION=0.1.7

ENV CACHE_BUST=DogDfATpUuPzJAuIaV9Rn5v1JT+Sw/O9

RUN ${VIRTUAL_ENV}/bin/pip \
    install "adjourn[mcp]==${ADJOURN_VERSION}" \
    --no-cache-dir

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["/bin/sh"]
