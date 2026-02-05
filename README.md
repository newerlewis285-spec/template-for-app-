# Smart Video Template (OpusClip-like workflow)

Template này giúp bạn **cố định format video + style chữ + hiệu ứng**, để mỗi lần edit chỉ cần đổi:

- Video đầu vào
- Nội dung caption

Mọi thứ còn lại (font, màu, outline, animation chữ, khung dọc 9:16, blur nền, zoom nhẹ, color look) sẽ tự động áp dụng theo template JSON.

## 1) Yêu cầu

- Python 3.10+
- FFmpeg + FFprobe cài sẵn trong PATH

## 2) Cấu trúc file

- `video_template.py`: engine render template
- `template.opus-like.json`: preset template mặc định kiểu "viral short"
- `captions.sample.txt`: ví dụ caption dạng text thường (auto chia thời lượng)
- `captions.sample.json`: ví dụ caption có timing chính xác

## 3) Chạy nhanh

```bash
python3 video_template.py \
  --input input.mp4 \
  --output output_template.mp4 \
  --template template.opus-like.json \
  --captions captions.sample.txt
```

### Dùng caption timing chính xác (.json)

```bash
python3 video_template.py \
  --input input.mp4 \
  --output output_template.mp4 \
  --template template.opus-like.json \
  --captions captions.sample.json
```

## 4) Tùy biến giống OpusClip

Bạn chỉ cần sửa file `template.opus-like.json`:

### Text style

- `font_family`: font chữ
- `font_size`: kích thước
- `primary_color`: màu chữ chính
- `outline_color`, `outline`, `shadow`: độ nổi chữ
- `position`, `margin_v`: vị trí caption

### Text effects

- `fade_in_ms`, `fade_out_ms`: mờ vào / mờ ra
- `pop_in`: hiệu ứng pop-in chữ

### Video effects

- `background_blur`: blur nền
- `foreground_zoom_strength`: zoom nhịp nhẹ
- `saturation`, `contrast`, `brightness`: look màu

## 5) Ý tưởng workflow siêu nhanh

1. Chuẩn bị nhiều template JSON (Business, Podcast, Motivational, Vlog...).
2. Mỗi project chỉ đổi `--template` + file captions.
3. Có thể nối thêm pipeline STT để tự tạo captions JSON rồi feed vào script.

=> Bạn sẽ không cần chỉnh tay font/effect/màu mỗi lần edit nữa.
