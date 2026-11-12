# Dashboard screenshot sources

> Language: English | [Tiếng Việt](SCREENSHOT-SOURCES.vi.md)

## Current rendered images

The `.jpg` files referenced by [`../dashboard-walkthrough.vi.md`](../dashboard-walkthrough.vi.md) are clean crops from real dashboard screenshots with Vietnamese title strips. The English tutorial uses matching images under [`en/`](en/) with English title strips. No red annotation boxes are baked into the current versions; the adjacent text identifies the controls and values.

## Local source archive

Raw captures are intentionally kept outside this repository because they include account/tenant UI details:

```text
/home/long/.cache/cos-mcp-doc-shots/
```

The previously annotated versions were preserved separately before replacing the incorrect overlays:

```text
/home/long/.cache/cos-mcp-doc-shots/old-docs-assets-annotated/
```

Do not delete either directory until the rendered images have been reviewed and the source captures have been archived somewhere persistent.

## Image mapping

| Rendered image | Original capture | Processing |
| --- | --- | --- |
| `auth0-apis-ui.jpg` | `auth0-apis-list-target-row.jpg` | Crop top tenant header |
| `auth0-api-create-form.jpg` | `auth0-api-create-form.jpg` | Crop top tenant header |
| `auth0-api-settings.jpg` | `auth0-api-settings.jpg` | Crop top tenant header |
| `auth0-api-token-profile.jpg` | `auth0-api-settings-jwt.jpg` | Crop top tenant header |
| `auth0-api-permissions.jpg` | `auth0-api-permissions.jpg` | Crop top tenant header |
| `auth0-google-connection.jpg` | `auth0-google-settings.jpg` | Crop top tenant header |
| `auth0-google-credentials.jpg` | `auth0-google-credentials-lower.jpg` | Preserve lower-page crop |
| `auth0-post-login.jpg` | `auth0-post-login.jpg` | Crop top tenant header |
| `auth0-action-secrets-panel.jpg` | `auth0-action-secrets-full.jpg` | Crop Secrets panel; exclude code editor |
| `cloudflare-tunnels-ui.jpg` | `cloudflare-tunnels-list-refresh.jpg` | Crop top account header |
| `cloudflare-route-detail.jpg` | `cloudflare-routes-raw.jpg` | Crop top account header |
| `cloudflare-add-route-form.jpg` | `cloudflare-add-route-form.jpg` | Crop top account header |
| `cloudflare-add-route-filled-example.jpg` | `cloudflare-add-route-filled.jpg` | Crop top account header |

## Re-rendering

Use FFmpeg with source coordinates before applying any scale filter. For example:

```bash
ffmpeg -i source.jpg -vf 'crop=iw:ih-56:0:56' -frames:v 1 -q:v 2 output.jpg
```

Do not reuse coordinates from a 1600-pixel preview on a 2000-pixel source. If highlighting a control is necessary, calculate the rectangle against the source frame dimensions and verify the resulting image visually before updating the Markdown.

## Numbered tutorial images

The 13 tutorial images use a separate 88px title strip above the screenshot. The orange number badge identifies the reading order. FFmpeg adds this strip with `pad` and `drawtext`; it does not move, scale, crop, or cover any dashboard control. The dashboard itself is not annotated with guessed rectangles or arrows. Clean source screenshots are versioned in [`source/`](source/):

```text
docs/assets/source/
```

Rebuild all 13 in either language:

```bash
# Vietnamese (writes to docs/assets/)
bash docs/assets/number-tutorial-images.sh vi

# English (writes to docs/assets/en/)
bash docs/assets/number-tutorial-images.sh en
```

Sequence: `01` Tunnel list, `02` existing route, `03` blank route form, `04` filled route example, `05` Auth0 API list, `06` create API form, `07` API settings, `08` JWT profile/signing, `09` permission, `10` Google connection, `11` Google credentials, `12` Post Login flow, `13` Action Secrets panel.
