#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
  cat >&2 <<'USAGE'
Usage:
  process-dashboard-screenshots.sh AUTH0_RAW_IMAGE CLOUDFLARE_RAW_IMAGE [OUTPUT_DIR]

Captures must be viewport screenshots of the Auth0 APIs list and Cloudflare
Zero Trust > Networks > Tunnels list. Originals stay outside the repository.
The script scales to 1600px width, highlights the target row, and blurs the
Cloudflare account identity before writing the processed JPEGs.
USAGE
  exit 2
fi

AUTH0_RAW="$1"
CLOUDFLARE_RAW="$2"
OUTPUT_DIR="${3:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)}"

command -v ffmpeg >/dev/null 2>&1 || {
  printf '%s\n' 'ffmpeg is required.' >&2
  exit 1
}
[[ -s "$AUTH0_RAW" ]] || { printf 'Missing Auth0 image: %s\n' "$AUTH0_RAW" >&2; exit 1; }
[[ -s "$CLOUDFLARE_RAW" ]] || { printf 'Missing Cloudflare image: %s\n' "$CLOUDFLARE_RAW" >&2; exit 1; }
mkdir -p -- "$OUTPUT_DIR"

# Auth0 API-list screenshot: outline the COS Multi-Account MCP custom API row.
ffmpeg -hide_banner -loglevel error -y -i "$AUTH0_RAW" \
  -vf "scale=1600:-2,drawbox=x=410:y=540:w=870:h=62:color=0xe76f35@1.0:t=5" \
  -frames:v 1 -q:v 2 "$OUTPUT_DIR/auth0-apis-ui.jpg"

# Cloudflare Tunnels screenshot: blur the account label and outline cos-mcp.
ffmpeg -hide_banner -loglevel error -y -i "$CLOUDFLARE_RAW" \
  -filter_complex "[0:v]scale=1600:-2,split[base][roi];[roi]crop=224:53:44:0,boxblur=12:3[blur];[base][blur]overlay=44:0,drawbox=x=328:y=246:w=660:h=46:color=0xe76f35@1.0:t=5[v]" \
  -map '[v]' -frames:v 1 -q:v 2 "$OUTPUT_DIR/cloudflare-tunnels-ui.jpg"

printf '%s\n' 'Processed dashboard screenshots:'
file "$OUTPUT_DIR/auth0-apis-ui.jpg" "$OUTPUT_DIR/cloudflare-tunnels-ui.jpg"
printf '%s\n' 'Original input images were not modified.'
