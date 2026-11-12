# Nguồn ảnh chụp dashboard

> Ngôn ngữ: [English](SCREENSHOT-SOURCES.md) | Tiếng Việt

## Ảnh đã render hiện tại

Các file `.jpg` được tham chiếu bởi [`../dashboard-walkthrough.vi.md`](../dashboard-walkthrough.vi.md) là crop sạch từ ảnh chụp dashboard thật, có title strip tiếng Việt. Tutorial tiếng Anh dùng ảnh tương ứng trong [`en/`](en/) với title strip tiếng Anh. Phiên bản hiện tại không chứa khung annotation màu đỏ; nội dung văn bản bên cạnh giải thích control và giá trị cần đối chiếu.

## Kho ảnh nguồn local

Raw capture được giữ ngoài repository vì chúng có thông tin UI của account/tenant:

```text
/home/long/.cache/cos-mcp-doc-shots/
```

Các phiên bản cũ có annotation sai đã được giữ riêng trước khi thay overlay:

```text
/home/long/.cache/cos-mcp-doc-shots/old-docs-assets-annotated/
```

Không xóa hai thư mục này cho tới khi ảnh render được review và source capture đã được archive ở nơi lưu trữ bền vững.

## Mapping ảnh

| Ảnh đã render | Capture gốc | Xử lý |
| --- | --- | --- |
| `auth0-apis-ui.jpg` | `auth0-apis-list-target-row.jpg` | Crop header tenant phía trên |
| `auth0-api-create-form.jpg` | `auth0-api-create-form.jpg` | Crop header tenant phía trên |
| `auth0-api-settings.jpg` | `auth0-api-settings.jpg` | Crop header tenant phía trên |
| `auth0-api-token-profile.jpg` | `auth0-api-settings-jwt.jpg` | Crop header tenant phía trên |
| `auth0-api-permissions.jpg` | `auth0-api-permissions.jpg` | Crop header tenant phía trên |
| `auth0-google-connection.jpg` | `auth0-google-settings.jpg` | Crop header tenant phía trên |
| `auth0-google-credentials.jpg` | `auth0-google-credentials-lower.jpg` | Giữ lower-page crop |
| `auth0-post-login.jpg` | `auth0-post-login.jpg` | Crop header tenant phía trên |
| `auth0-action-secrets-panel.jpg` | `auth0-action-secrets-full.jpg` | Crop Secrets panel; loại vùng code editor |
| `cloudflare-tunnels-ui.jpg` | `cloudflare-tunnels-list-refresh.jpg` | Crop header account phía trên |
| `cloudflare-route-detail.jpg` | `cloudflare-routes-raw.jpg` | Crop header account phía trên |
| `cloudflare-add-route-form.jpg` | `cloudflare-add-route-form.jpg` | Crop header account phía trên |
| `cloudflare-add-route-filled-example.jpg` | `cloudflare-add-route-filled.jpg` | Crop header account phía trên |

## Render lại

Dùng FFmpeg với tọa độ tính trên ảnh nguồn trước khi áp dụng scale filter. Ví dụ:

```bash
ffmpeg -i source.jpg -vf 'crop=iw:ih-56:0:56' -frames:v 1 -q:v 2 output.jpg
```

Không dùng lại tọa độ từ preview 1600 pixel trên ảnh nguồn 2000 pixel. Nếu cần highlight control, hãy tính rectangle theo kích thước frame nguồn và kiểm tra trực quan ảnh kết quả trước khi cập nhật Markdown.

## Ảnh tutorial có đánh số

13 ảnh tutorial sử dụng một title strip cao 88px riêng, nằm phía trên screenshot. Badge màu cam cho biết thứ tự đọc. FFmpeg thêm strip bằng `pad` và `drawtext`; nó không dịch chuyển, scale, crop hoặc che bất kỳ control dashboard nào. Dashboard không bị vẽ khung hoặc mũi tên theo tọa độ phỏng đoán. Ảnh nguồn sạch được version-control tại [`source/`](source/):

```text
docs/assets/source/
```

Tạo lại cả 13 ảnh theo đúng thứ tự tài liệu bằng một trong hai lệnh:

```bash
# Tiếng Việt (ghi vào docs/assets/)
bash docs/assets/number-tutorial-images.sh vi

# Tiếng Anh (ghi vào docs/assets/en/)
bash docs/assets/number-tutorial-images.sh en
```

Thứ tự: `01` danh sách Tunnel, `02` route hiện tại, `03` route form trống, `04` ví dụ form đã điền, `05` Auth0 API list, `06` form Create API, `07` API settings, `08` JWT profile/signing, `09` permission, `10` Google connection, `11` Google credentials, `12` Post Login flow, `13` Action Secrets panel.
