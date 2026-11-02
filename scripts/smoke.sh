#!/bin/sh
# The app as a person meets it (docs/slices/slice-9.md, done-when): a fresh database, one
# create_school, then the SPA's proxy on <school>.localhost serving the page, the School's name,
# activation, `me` and sign-out. Catches what stubbed tests cannot (the proxy's Host header, a
# broken route tree). Throwaway compose project and ports; run from the repo root with .env
# exported (make smoke does both).
set -eu
DB=5434 API=8010 WEB=5180 SUB=smoke
work=$(mktemp -d)
export DB_PORT=$DB DJANGO_DEBUG=1 SECURE_COOKIES=false
cleanup() {
  [ -f "$work/pids" ] && kill $(cat "$work/pids") 2>/dev/null || true
  docker compose -p schools-smoke down -v >/dev/null 2>&1 || true
  rm -rf "$work"
}
trap cleanup EXIT
fail() { echo "smoke FAILED: $1" >&2; for f in "$work"/*.log; do echo "--- $f" >&2; tail -20 "$f" >&2; done; exit 1; }

docker compose -p schools-smoke up -d --wait db >/dev/null 2>&1 || fail "database did not start"
(cd backend && DB_ROLE=owner uv run python manage.py migrate -v0) || fail "migrate"
code=$(cd backend && DB_ROLE=owner uv run python manage.py create_school $SUB --name "Smoke" \
  --admin smoke@example.com --admin-name "Smoke Admin" --operator smoke | sed -n 's/^Code.*: //p')
[ -n "$code" ] || fail "create_school printed no code"

(cd backend && exec uv run python manage.py runserver $API --noreload >"$work/django.log" 2>&1) &
echo $! >"$work/pids"
(cd frontend && API_PORT=$API exec pnpm exec vite --port $WEB --strictPort >"$work/vite.log" 2>&1) &
echo $! >>"$work/pids"

base="http://$SUB.localhost:$WEB"
jar="$work/jar"
for _ in $(seq 1 60); do curl -sf -o /dev/null "$base/api/auth/school/" && break; sleep 1; done
curl -sf "$base/login" | grep -q 'id="root"' || fail "the SPA page"
curl -sf "$base/api/auth/school/" | grep -q '"name":"Smoke"' || fail "school through the proxy (Host header?)"
curl -sf -c "$jar" -b "$jar" -o /dev/null "$base/api/auth/csrf/" || fail "csrf"
token=$(awk '/csrftoken/ {print $7}' "$jar")
post() { curl -s -o "$work/body" -w '%{http_code}' -c "$jar" -b "$jar" -H "X-CSRFToken: $token" \
  -H 'Content-Type: application/json' -d "$2" "$base/api/auth/$1/"; }
body=$(printf '{"code":"%s","identifier":"smoke@example.com","password":"smoke password 1"}' "$code")
[ "$(post activate "$body")" = 200 ] || fail "activate: $(cat "$work/body")"
grep -q '"role":"school_admin"' "$work/body" || fail "activated without the school_admin role"
token=$(awk '/csrftoken/ {print $7}' "$jar")  # rotated at sign-in
[ "$(curl -s -o /dev/null -w '%{http_code}' -b "$jar" "$base/api/auth/me/")" = 200 ] || fail "me"
[ "$(post logout '{}')" = 204 ] || fail "logout"
[ "$(curl -s -o /dev/null -w '%{http_code}' -b "$jar" "$base/api/auth/me/")" = 403 ] || fail "me after logout"
echo "smoke OK: fresh database, create_school, activation, me and sign-out through the SPA proxy"
