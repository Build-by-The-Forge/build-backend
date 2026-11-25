# The db-init Cloud Run job: runs deploy/db-init/init-roles.sql against Cloud SQL
# as the postgres user, with the four role passwords from Secret Manager.
# Build from the repository root:
#   docker build -f deploy/gcp/db-init/Dockerfile -t db-init .
# Same client major as the server (PostgreSQL 17), as in deploy/compose.m3.yml.
FROM postgres:17

COPY deploy/db-init/init-roles.sql /db-init/init-roles.sql
COPY deploy/gcp/db-init/run.sh /db-init/run.sh

# Nothing here runs a server; psql only. An unprivileged user, no shell login.
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin dbinit
USER 10001:10001

ENTRYPOINT ["/bin/sh", "/db-init/run.sh"]
