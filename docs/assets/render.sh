#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ASSET_DIR="$SCRIPT_DIR"

command -v ffmpeg >/dev/null 2>&1 || {
  printf '%s\n' 'ffmpeg is required to render setup documentation assets.' >&2
  exit 1
}

for name in architecture cloudflare-tunnel auth0-flow setup-sequence; do
  ffmpeg -hide_banner -loglevel error -y \
    -i "$ASSET_DIR/$name.svg" -frames:v 1 -update 1 \
    "$ASSET_DIR/$name.png"
done

ffmpeg -hide_banner -loglevel error -y \
  -loop 1 -framerate 30 -t 4 -i "$ASSET_DIR/architecture.png" \
  -loop 1 -framerate 30 -t 4 -i "$ASSET_DIR/cloudflare-tunnel.png" \
  -loop 1 -framerate 30 -t 4 -i "$ASSET_DIR/auth0-flow.png" \
  -loop 1 -framerate 30 -t 4 -i "$ASSET_DIR/setup-sequence.png" \
  -filter_complex "\
    [0:v]scale=1280:720,setsar=1,format=yuv420p,settb=AVTB,setpts=PTS-STARTPTS[v0];\
    [1:v]scale=1280:720,setsar=1,format=yuv420p,settb=AVTB,setpts=PTS-STARTPTS[v1];\
    [2:v]scale=1280:720,setsar=1,format=yuv420p,settb=AVTB,setpts=PTS-STARTPTS[v2];\
    [3:v]scale=1280:720,setsar=1,format=yuv420p,settb=AVTB,setpts=PTS-STARTPTS[v3];\
    [v0][v1]xfade=transition=fade:duration=0.5:offset=3.5[v01];\
    [v01][v2]xfade=transition=fade:duration=0.5:offset=7.0[v012];\
    [v012][v3]xfade=transition=fade:duration=0.5:offset=10.5[v]" \
  -map '[v]' -an -t 14.5 -r 30 -c:v libx264 -crf 21 -preset medium \
  -pix_fmt yuv420p -movflags +faststart \
  "$ASSET_DIR/setup-walkthrough.mp4"

ffmpeg -hide_banner -loglevel error -y \
  -i "$ASSET_DIR/setup-walkthrough.mp4" \
  -vf "fps=8,scale=800:-1:flags=lanczos,split[s0][s1];[s0]palettegen=stats_mode=diff[p];[s1][p]paletteuse=dither=sierra2_4a" \
  -loop 0 "$ASSET_DIR/setup-walkthrough.gif"

printf '%s\n' 'Rendered PNG diagrams, setup-walkthrough.mp4, and setup-walkthrough.gif.'
ffprobe -v error -show_entries format=duration,size -of default=noprint_wrappers=1 \
  "$ASSET_DIR/setup-walkthrough.mp4"
