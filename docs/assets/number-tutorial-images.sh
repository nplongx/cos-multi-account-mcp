#!/usr/bin/env bash
set -euo pipefail

# Add a numbered title strip ABOVE each screenshot. The screenshot pixels are
# not scaled, cropped, translated, or covered by annotations.
#
# Usage:
#   number-tutorial-images.sh [vi|en] [OUTPUT_DIR] [CLEAN_SOURCE_DIR]
#
# The clean source directory must contain the 13 source screenshots. These
# source images are versioned in docs/assets/source so the build is portable.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
LANGUAGE="${1:-vi}"
case "$LANGUAGE" in
  vi) DEFAULT_OUTPUT_DIR="$SCRIPT_DIR" ;;
  en) DEFAULT_OUTPUT_DIR="$SCRIPT_DIR/en" ;;
  *) printf 'Unsupported language: %s (use vi or en)\n' "$LANGUAGE" >&2; exit 2 ;;
esac
OUTPUT_DIR="${2:-$DEFAULT_OUTPUT_DIR}"
SOURCE_DIR="${3:-$SCRIPT_DIR/source}"
FONT="${FONT:-/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf}"

command -v ffmpeg >/dev/null 2>&1 || { echo 'ffmpeg is required' >&2; exit 1; }
[[ -s "$FONT" ]] || { printf 'Font not found: %s\n' "$FONT" >&2; exit 1; }
[[ -d "$SOURCE_DIR" ]] || { printf 'Source directory not found: %s\n' "$SOURCE_DIR" >&2; exit 1; }
mkdir -p -- "$OUTPUT_DIR"

render() {
  local number="$1" title="$2" file="$3"
  local input="$SOURCE_DIR/$file" output="$OUTPUT_DIR/$file"
  [[ -s "$input" ]] || { printf 'Missing source image: %s\n' "$input" >&2; exit 1; }

  # Draw the number/title in a new 88px top strip. This avoids coordinate
  # guesses against browser viewport scaling and preserves every source pixel.
  ffmpeg -hide_banner -loglevel error -y -i "$input" \
    -vf "pad=iw:ih+88:0:88:color=0x142438,drawbox=x=24:y=17:w=82:h=54:color=0xe76f35:t=fill,drawtext=fontfile='$FONT':text='$number':fontcolor=white:fontsize=27:x=45:y=28,drawtext=fontfile='$FONT':text='$title':fontcolor=white:fontsize=25:x=132:y=30" \
    -frames:v 1 -q:v 2 "$output"
}

if [[ "$LANGUAGE" == "vi" ]]; then
  render 01 'Cloudflare - Mở danh sách Tunnels' cloudflare-tunnels-ui.jpg
  render 02 'Cloudflare - Kiểm tra Routes hiện có' cloudflare-route-detail.jpg
  render 03 'Cloudflare - Mở form Published application' cloudflare-add-route-form.jpg
  render 04 'Cloudflare - Điền hostname và Service URL' cloudflare-add-route-filled-example.jpg
  render 05 'Auth0 - Mở Applications và APIs' auth0-apis-ui.jpg
  render 06 'Auth0 - Tạo Custom API nếu chưa có' auth0-api-create-form.jpg
  render 07 'Auth0 - Kiểm tra Settings và Identifier' auth0-api-settings.jpg
  render 08 'Auth0 - Kiểm tra RFC 9068 và RS256' auth0-api-token-profile.jpg
  render 09 'Auth0 - Kiểm tra quyền MCP connect' auth0-api-permissions.jpg
  render 10 'Auth0 - Mở Google Social Connection' auth0-google-connection.jpg
  render 11 'Auth0 - Nhập Client ID và Client Secret' auth0-google-credentials.jpg
  render 12 'Auth0 - Kiểm tra Post Login Action' auth0-post-login.jpg
  render 13 'Auth0 - Kiểm tra Action Secrets' auth0-action-secrets-panel.jpg
else
  render 01 'Cloudflare - Open Tunnels list' cloudflare-tunnels-ui.jpg
  render 02 'Cloudflare - Inspect existing Routes' cloudflare-route-detail.jpg
  render 03 'Cloudflare - Open Published application form' cloudflare-add-route-form.jpg
  render 04 'Cloudflare - Fill hostname and Service URL' cloudflare-add-route-filled-example.jpg
  render 05 'Auth0 - Open Applications and APIs' auth0-apis-ui.jpg
  render 06 'Auth0 - Create Custom API if missing' auth0-api-create-form.jpg
  render 07 'Auth0 - Inspect API Settings and Identifier' auth0-api-settings.jpg
  render 08 'Auth0 - Verify RFC 9068 and RS256' auth0-api-token-profile.jpg
  render 09 'Auth0 - Verify MCP connect permission' auth0-api-permissions.jpg
  render 10 'Auth0 - Open Google Social Connection' auth0-google-connection.jpg
  render 11 'Auth0 - Enter Google OAuth Client credentials' auth0-google-credentials.jpg
  render 12 'Auth0 - Verify Post Login Action' auth0-post-login.jpg
  render 13 'Auth0 - Inspect Action Secrets panel' auth0-action-secrets-panel.jpg
fi

printf 'Rendered 13 numbered screenshots into %s\n' "$OUTPUT_DIR"
