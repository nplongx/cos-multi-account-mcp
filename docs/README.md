# Documentation index

> Language: English | [Tiếng Việt](README.vi.md)

This directory maintains parallel English and Vietnamese versions. Existing unsuffixed Markdown files are English; matching `.vi.md` files are Vietnamese. Legal texts (`LICENSE`, `NOTICE`) retain their original wording.

## Start here

| Topic | English | Tiếng Việt |
| --- | --- | --- |
| End-to-end setup | [getting-started.md](getting-started.md) | [getting-started.vi.md](getting-started.vi.md) |
| Beginner dashboard walkthrough | [dashboard-walkthrough.md](dashboard-walkthrough.md) | [dashboard-walkthrough.vi.md](dashboard-walkthrough.vi.md) |
| Operator deployment runbook | [deployment-guide.md](deployment-guide.md) | [deployment-guide.vi.md](deployment-guide.vi.md) |
| OAuth: Auth0, Google, ChatGPT | [oauth-setup.md](oauth-setup.md) | [oauth-setup.vi.md](oauth-setup.vi.md) |

## Technical reference

| Topic | English | Tiếng Việt |
| --- | --- | --- |
| Architecture and trust boundaries | [architecture.md](architecture.md) | [architecture.vi.md](architecture.vi.md) |
| Deployment | [deployment.md](deployment.md) | [deployment.vi.md](deployment.vi.md) |
| Operations | [operations.md](operations.md) | [operations.vi.md](operations.vi.md) |
| Verification and acceptance | [verification.md](verification.md) | [verification.vi.md](verification.vi.md) |
| Gmail user provisioning | [sso-user-provisioning.md](sso-user-provisioning.md) | [sso-user-provisioning.vi.md](sso-user-provisioning.vi.md) |
| A2A autostart (Linux/systemd) | [a2a-autostart.md](a2a-autostart.md) | [a2a-autostart.vi.md](a2a-autostart.vi.md) |

## A2A implementation records

| Topic | English | Tiếng Việt |
| --- | --- | --- |
| Eight-Workstream bootstrap (2026-11-03) | [a2a-workstream-bootstrap-2026-11-03.md](a2a-workstream-bootstrap-2026-11-03.md) | [a2a-workstream-bootstrap-2026-11-03.vi.md](a2a-workstream-bootstrap-2026-11-03.vi.md) |
| Live WS1/WS3 pilot (2026-11-03) | [a2a-pilot-2026-11-03.md](a2a-pilot-2026-11-03.md) | [a2a-pilot-2026-11-03.vi.md](a2a-pilot-2026-11-03.vi.md) |

## Image assets and source notes

| Topic | English | Tiếng Việt |
| --- | --- | --- |
| Dashboard screenshot sources and FFmpeg rendering | [SCREENSHOT-SOURCES.md](assets/SCREENSHOT-SOURCES.md) | [SCREENSHOT-SOURCES.vi.md](assets/SCREENSHOT-SOURCES.vi.md) |

The numbered screenshots are localized: English images live in `assets/en/`; Vietnamese images live directly in `assets/`. Clean source captures live in `assets/source/`. Rebuild both language sets with:

```bash
bash docs/assets/number-tutorial-images.sh en
bash docs/assets/number-tutorial-images.sh vi
```

## Repository-level documents

- [English README](../README.md) / [Tiếng Việt README](../README.vi.md)
- [English security policy](../SECURITY.md) / [Chính sách bảo mật tiếng Việt](../SECURITY.vi.md)
