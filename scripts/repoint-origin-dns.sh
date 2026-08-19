#!/usr/bin/env bash
# Point Cloudflare A records at a new origin IP.
#
# Requires CLOUDFLARE_API_TOKEN with Zone.DNS:Edit on the domain.
# Grey-cloud first so Let's Encrypt HTTP-01/TLS-ALPN can reach the origin;
# orange-cloud only after Caddy has a certificate.
#
#   CLOUDFLARE_API_TOKEN=... ./scripts/repoint-origin-dns.sh --ip 5.75.158.200 --grey
#   CLOUDFLARE_API_TOKEN=... ./scripts/repoint-origin-dns.sh --ip 5.75.158.200 --orange
set -euo pipefail

DOMAIN="${DOMAIN:-collectivewill.org}"
IP=""
PROXIED=""

usage() {
  echo "Usage: $0 --ip <origin-ipv4> --grey|--orange [--domain ${DOMAIN}]" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ip) IP="${2:-}"; shift 2 ;;
    --domain) DOMAIN="${2:-}"; shift 2 ;;
    --grey) PROXIED="false"; shift ;;
    --orange) PROXIED="true"; shift ;;
    -h|--help) usage ;;
    *) echo "Unknown argument: $1" >&2; usage ;;
  esac
done

[[ -n "$IP" && -n "$PROXIED" ]] || usage
[[ "$IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || {
  echo "Error: --ip must be an IPv4 address" >&2
  exit 1
}

if [[ -z "${CLOUDFLARE_API_TOKEN:-}" ]]; then
  echo "CLOUDFLARE_API_TOKEN is not set." >&2
  echo "Create a token (Zone.DNS Edit) at https://dash.cloudflare.com/profile/api-tokens" >&2
  echo "Until then, do this in the dashboard:" >&2
  echo "  1. SSL/TLS = Full (not Full strict)" >&2
  echo "  2. Grey-cloud @ and staging; A records -> ${IP}" >&2
  echo "  3. Wait until: dig +short staging.${DOMAIN}   # only ${IP}" >&2
  echo "  4. After Caddy has certs: orange-cloud + Full (strict)" >&2
  exit 2
fi

export CF_TOKEN="$CLOUDFLARE_API_TOKEN"
export CF_DOMAIN="$DOMAIN"
export CF_IP="$IP"
export CF_PROXIED="$PROXIED"

python3 - <<'PY'
import json, os, sys, urllib.error, urllib.parse, urllib.request

token = os.environ["CF_TOKEN"]
domain = os.environ["CF_DOMAIN"]
ip = os.environ["CF_IP"]
proxied = os.environ["CF_PROXIED"] == "true"
headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
}

def cf(method, path, body=None):
    req = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4{path}",
        data=None if body is None else json.dumps(body).encode(),
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        print(f"Cloudflare API {exc.code}: {detail}", file=sys.stderr)
        sys.exit(1)
    if not payload.get("success"):
        print(json.dumps(payload.get("errors", payload), indent=2), file=sys.stderr)
        sys.exit(1)
    return payload

zones = cf("GET", "/zones?" + urllib.parse.urlencode({"name": domain}))["result"]
if not zones:
    print(f"No Cloudflare zone named {domain}", file=sys.stderr)
    sys.exit(1)
zone_id = zones[0]["id"]

wanted = {domain: ip, f"staging.{domain}": ip}
records = cf(
    "GET",
    f"/zones/{zone_id}/dns_records?" + urllib.parse.urlencode({"type": "A", "per_page": 100}),
)["result"]

by_name = {}
for rec in records:
    by_name.setdefault(rec["name"], []).append(rec)

for name, content in wanted.items():
    existing = by_name.get(name, [])
    extras = existing[1:]
    if existing:
        rec = existing[0]
        cf(
            "PATCH",
            f"/zones/{zone_id}/dns_records/{rec['id']}",
            {"type": "A", "name": name, "content": content, "proxied": proxied, "ttl": 1},
        )
        print(f"updated A {name} -> {content} proxied={proxied}")
        for extra in extras:
            cf("DELETE", f"/zones/{zone_id}/dns_records/{extra['id']}")
            print(f"deleted extra A {name} ({extra['content']})")
    else:
        cf(
            "POST",
            f"/zones/{zone_id}/dns_records",
            {"type": "A", "name": name, "content": content, "proxied": proxied, "ttl": 1},
        )
        print(f"created A {name} -> {content} proxied={proxied}")

mode = "orange-cloud" if proxied else "grey-cloud (DNS only)"
print(f"done: {mode}")
if not proxied:
    print(f"verify: dig +short staging.{domain}   # expect {ip} only")
PY
