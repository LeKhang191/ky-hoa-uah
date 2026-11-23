# UAH - Ký họa thực chiến (bản dựng lại)

Flask + PostgreSQL + Cloudinary. Xây theo ERD và phân tích thiết kế của CLB, **Giai đoạn 1 (MVP)**.

## Chạy
```bash
pip install -r requirements.txt
cp .env.example .env            # điền 4 biến; thiếu biến nào app báo lỗi ngay khi khởi động
export $(grep -v '^#' .env | xargs)
flask --app app init-db         # áp schema.sql, chạy lại an toàn
flask --app app create-admin --email ban@clb.vn --name "Ban chủ nhiệm"   # in mã kích hoạt
flask --app app run             # vào /activate, nhập email + mã, tự đặt mật khẩu
```
Docker: `docker build -t ky-hoa . && docker run -p 8000:8000 --env-file .env ky-hoa`.

## Test (Postgres thật, tự khởi chạy; Cloudinary được thay bằng bản giả)
```bash
pip install -r requirements-dev.txt && pytest
```

## Đã có (Giai đoạn 1)
- **Đăng nhập bằng mã kích hoạt**: admin tạo tài khoản hoặc import CSV, mã 16 ký tự, chỉ lưu hash, hết hạn 72 giờ, dùng một lần. Thành viên vào `/activate` (email + mã) để tự đặt mật khẩu; "cấp lại mã" cũng chính là cách đặt lại mật khẩu. Không có đăng ký công khai.
- **Phân quyền**: khách / member (active đăng được; break, former chỉ xem) / admin; khóa tài khoản có hiệu lực ngay cả với phiên đang đăng nhập.
- **Tranh**: ảnh gốc lưu Cloudinary `private` (không bao giờ ra HTML); bản công khai nén 1600px, xoay đúng EXIF, watermark nhẹ; `public` / `internal` (nội bộ dùng URL có chữ ký); tag địa điểm/chất liệu/buổi thực chiến + lọc; xóa mềm; admin duyệt / từ chối kèm lý do.
- **Admin**: thành viên (trạng thái, quyền, khóa, cấp lại/thu hồi mã), import CSV (sai một dòng thì cả file bị từ chối), bảng tin, album ảnh sinh hoạt, nhật ký thao tác.
- Bảo mật: CSRF mọi form POST, cookie Secure + SameSite, mật khẩu băm scrypt (werkzeug).

## Chưa có (đúng như PDF)
- **Giai đoạn 2**: like, bình luận, link chia sẻ, màn khôi phục thùng rác, biểu đồ dashboard. Cột `deleted_at` đã sẵn.
- **Giai đoạn 3**: challenge, lịch sinh hoạt + điểm danh, FCM.

## Quyết định cần biết
- Thay đổi so với PDF: đăng nhập bằng **email** + mã (tên hiển thị không duy nhất nên không dùng làm định danh). Bỏ `join_applications`: đơn vẫn nằm ở Google Form, admin tạo tài khoản trực tiếp.
- Bỏ SQLite, chỉ còn một đường Postgres. Bỏ role `photographer`: admin quản lý album.
- Không dùng Go/Rust/Redis/Qdrant/MinIO/Prometheus: chưa có tính năng nào cần tới.

## Giới hạn đã biết
- Chưa kiểm chứng với Cloudinary thật: `storage.move` (đổi public ↔ internal bằng `rename` với `to_type`) và việc tải ảnh lên. Test thay Cloudinary bằng bản giả. Hãy thử một lần với tài khoản thật.
- Chưa giới hạn số lần đăng nhập sai: nên bật rate limiting / Bot Fight ở Cloudflare trước domain.
- Ảnh cũ trên site Flask cũ chỉ còn bản 1200px (ảnh gốc đã bị bỏ từ trước), và chưa có script chuyển dữ liệu cũ sang.
- Watermark một góc, dễ bị cắt: đủ để răn đe, không ngăn được người cố tình.
