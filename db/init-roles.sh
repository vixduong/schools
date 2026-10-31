#!/bin/sh
# Runs once on a fresh volume. The owner runs migrations; the app role serves requests and
# cannot bypass row-level security. Neither is a superuser (superusers ignore RLS).
set -eu
psql -v ON_ERROR_STOP=1 -U postgres -d postgres \
  -v owner="$DB_OWNER_USER" -v owner_pw="$DB_OWNER_PASSWORD" \
  -v app="$DB_APP_USER" -v app_pw="$DB_APP_PASSWORD" -v db="$DB_NAME" <<'SQL'
CREATE ROLE :"owner" LOGIN PASSWORD :'owner_pw' CREATEDB NOSUPERUSER NOBYPASSRLS;
CREATE ROLE :"app" LOGIN PASSWORD :'app_pw' NOSUPERUSER NOCREATEDB NOBYPASSRLS;
CREATE DATABASE :"db" OWNER :"owner";
SQL
