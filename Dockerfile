# This file is for the docker-compose so that it takes care of the Python build as well

# nzdpu-wis
# The builder stage is necessary to keep the actual container image small
FROM python:3.11-slim-bullseye as base
# Upgrade package indexes and then packages
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked apt update && apt upgrade -y
# Need libmagic for python-magic https://pypi.org/project/python-magic/
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked apt install libmagic1 -y
RUN --mount=type=cache,target=/root/.cache/pip python3 -m pip install -U pip
WORKDIR /src

# Wheel builder is for the local docker compose development
FROM base as whl-builder
RUN --mount=type=cache,target=/root/.cache/pip python3 -m pip install build
RUN rm -rf dist
COPY . .
RUN --mount=type=cache,target=/root/.cache/pip python3 -m build

FROM base
# `curl` requirement for healthchecking
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked apt update && apt install curl -y
# Bring in the wheel of our app
COPY --from=whl-builder /src/dist/ /tmp/packages/
# Install nzdpu-wis and look for packages in /tmp/packages (should only be nzdpu-wis)
RUN --mount=type=cache,target=/root/.cache/pip pip install --find-links /tmp/packages nzdpu-wis
COPY app/ .
ENV LEADER_DB_HOST=localhost
ENV LEADER_DB_PORT=5432
ENV POSTGRES_DB=nzdpu_wis
ENV POSTGRES_USER=postgres
ENV POSTGRES_PASSWORD=postgres
EXPOSE 80
RUN apt-get update && apt-get install -y \
  curl
ENTRYPOINT ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80"]
