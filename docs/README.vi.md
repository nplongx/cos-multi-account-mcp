# Mục lục tài liệu

> Ngôn ngữ: [English](README.md) | Tiếng Việt

Thư mục này duy trì hai bộ tài liệu song song bằng tiếng Anh và tiếng Việt. File Markdown không có hậu tố là tiếng Anh; file tương ứng có hậu tố `.vi.md` là tiếng Việt. Văn bản pháp lý (`LICENSE`, `NOTICE`) giữ nguyên nội dung gốc.

## Bắt đầu tại đây

| Chủ đề | English | Tiếng Việt |
| --- | --- | --- |
| Setup end-to-end | [getting-started.md](getting-started.md) | [getting-started.vi.md](getting-started.vi.md) |
| Hướng dẫn dashboard cho người mới | [dashboard-walkthrough.md](dashboard-walkthrough.md) | [dashboard-walkthrough.vi.md](dashboard-walkthrough.vi.md) |
| Operator deployment runbook | [deployment-guide.md](deployment-guide.md) | [deployment-guide.vi.md](deployment-guide.vi.md) |
| OAuth: Auth0, Google, ChatGPT | [oauth-setup.md](oauth-setup.md) | [oauth-setup.vi.md](oauth-setup.vi.md) |

## Tham chiếu kỹ thuật

| Chủ đề | English | Tiếng Việt |
| --- | --- | --- |
| Kiến trúc và ranh giới tin cậy | [architecture.md](architecture.md) | [architecture.vi.md](architecture.vi.md) |
| Deployment | [deployment.md](deployment.md) | [deployment.vi.md](deployment.vi.md) |
| Vận hành | [operations.md](operations.md) | [operations.vi.md](operations.vi.md) |
| Kiểm chứng và nghiệm thu | [verification.md](verification.md) | [verification.vi.md](verification.vi.md) |
| Provision Gmail user | [sso-user-provisioning.md](sso-user-provisioning.md) | [sso-user-provisioning.vi.md](sso-user-provisioning.vi.md) |
| A2A autostart (Linux/systemd) | [a2a-autostart.md](a2a-autostart.md) | [a2a-autostart.vi.md](a2a-autostart.vi.md) |

## Hồ sơ triển khai A2A

| Chủ đề | English | Tiếng Việt |
| --- | --- | --- |
| Bootstrap tám Workstream (2026-11-03) | [a2a-workstream-bootstrap-2026-11-03.md](a2a-workstream-bootstrap-2026-11-03.md) | [a2a-workstream-bootstrap-2026-11-03.vi.md](a2a-workstream-bootstrap-2026-11-03.vi.md) |
| Live pilot WS1/WS3 (2026-11-03) | [a2a-pilot-2026-11-03.md](a2a-pilot-2026-11-03.md) | [a2a-pilot-2026-11-03.vi.md](a2a-pilot-2026-11-03.vi.md) |

## Hình ảnh và ghi chú source

| Chủ đề | English | Tiếng Việt |
| --- | --- | --- |
| Nguồn screenshot dashboard và FFmpeg rendering | [SCREENSHOT-SOURCES.md](assets/SCREENSHOT-SOURCES.md) | [SCREENSHOT-SOURCES.vi.md](assets/SCREENSHOT-SOURCES.vi.md) |

Screenshot được đánh số theo từng ngôn ngữ: ảnh tiếng Anh ở `assets/en/`; ảnh tiếng Việt nằm trực tiếp trong `assets/`. Ảnh nguồn sạch nằm tại `assets/source/`. Render lại cả hai bộ bằng:

```bash
bash docs/assets/number-tutorial-images.sh en
bash docs/assets/number-tutorial-images.sh vi
```

## Tài liệu cấp repository

- [README tiếng Anh](../README.md) / [README tiếng Việt](../README.vi.md)
- [Security policy tiếng Anh](../SECURITY.md) / [Chính sách bảo mật tiếng Việt](../SECURITY.vi.md)
