#!/bin/sh
# Applies deploy/db-init/init-roles.sql. Connection settings (PGHOST, PGUSER,
# PGDATABASE, PGPASSWORD, PGSSLMODE) and the four role passwords arrive as
# environment variables from Secret Manager; nothing is printed.
# Idempotent: the SQL is safe to run on every deploy.
set -eu

: "${PGHOST:?}" "${PGPASSWORD:?}" "${BACKEND_OWNER_PASSWORD:?}" "${BACKEND_APP_PASSWORD:?}" \
  "${AI_OWNER_PASSWORD:?}" "${AI_APP_PASSWORD:?}"

# Passwords are passed to psql as variables (read by the SQL as :'name'), so they
# are never interpolated into a shell command line that could be logged.
exec psql --set=ON_ERROR_STOP=1 \
  -v db="${PGDATABASE:-build}" \
  -v backend_owner_password="${BACKEND_OWNER_PASSWORD}" \
  -v backend_app_password="${BACKEND_APP_PASSWORD}" \
  -v ai_owner_password="${AI_OWNER_PASSWORD}" \
  -v ai_app_password="${AI_APP_PASSWORD}" \
  -f /db-init/init-roles.sql
