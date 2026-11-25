#!/usr/bin/env bash
# Time connect, TLS and first byte to one or more HTTPS URLs (step 2 of the
# latency method in docs/gcp-staging-verification.md). Read-only: it only
# makes GET requests to the URLs you pass.
#
#   deploy/gcp/benchmark/measure.sh 20 https://a.example/ https://b.example/
#
# Run it from each network students use (MTN, Airtel, Glo, campus Wi-Fi), at
# three times of day. Report the median and the 95th percentile.
set -euo pipefail

if [ "$#" -lt 2 ]; then
  echo "usage: $0 <samples> <url> [<url> ...]" >&2
  exit 2
fi
samples="$1"
shift

for url in "$@"; do
  echo "== ${url}"
  : > /tmp/measure.$$
  for _ in $(seq 1 "${samples}"); do
    curl -s -o /dev/null --max-time 15 \
      -w '%{time_connect} %{time_appconnect} %{time_starttransfer}\n' "${url}" >> /tmp/measure.$$ || echo "0 0 0" >> /tmp/measure.$$
    sleep 1
  done
  for col in 1 2 3; do
    label=$(echo "connect tls first_byte" | cut -d' ' -f"${col}")
    sort -g -k"${col}" /tmp/measure.$$ | awk -v c="${col}" -v l="${label}" '
      { v[NR] = $c }
      END {
        p95 = int(NR * 0.95); if (p95 < 1) p95 = 1
        printf "%-10s median=%.3fs p95=%.3fs (n=%d)\n", l, v[int((NR + 1) / 2)], v[p95], NR
      }'
  done
  rm -f /tmp/measure.$$
done
