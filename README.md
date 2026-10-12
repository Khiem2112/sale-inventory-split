# Sale Inventory Split

## Mục đích và điểm tích hợp

`sale_inventory_split` mở rộng module `sale_stock`, cho phép người dùng xác nhận
một Đơn bán hàng thành nhiều nhóm giao hàng. Số lượng của một dòng đơn hàng có
thể được phân bổ vào nhiều nhóm, và mỗi nhóm có thể sử dụng một địa chỉ giao
hàng khác nhau.

Module thêm nút **Confirm with Split** bên cạnh nút **Confirm** chuẩn trên form
Đơn bán hàng. Nút này xuất hiện trong cùng các trạng thái nháp và đã gửi báo
giá. Luồng xác nhận chuẩn không thay đổi khi không có kế hoạch chia hàng.

Module tái sử dụng các luồng procurement, stock rule, xác nhận stock move, gán
picking, giữ hàng và tạo move line chuẩn. Phần tùy chỉnh chỉ thay đổi cách chia
số lượng procurement và cách gom các move vào picking.

## Các model và field chính

### Các model tạm dùng để lập kế hoạch

- `sale.inventory.split.wizard` quản lý kế hoạch chia hàng của một Đơn bán hàng.
- `sale.inventory.split.picking` đại diện cho một phiếu giao hàng dự kiến. Các
  field quan trọng gồm `name`, `sequence`, `delivery_partner_id`,
  `split_group_key` và `allocation_ids`.
- `sale.inventory.split.move` phân bổ một `quantity` dương từ một
  `sale.order.line` vào một phiếu giao hàng dự kiến.

`delivery_partner_id` mặc định lấy từ `sale.order.partner_shipping_id` và người
dùng có thể thay đổi. Đây chỉ là field dùng khi lập kế hoạch; các bản ghi kho
được tạo ra vẫn sử dụng các field chuẩn `stock.move.partner_id` và
`stock.picking.partner_id`.

`split_group_key` là khóa kỹ thuật duy nhất dùng để phân nhóm. Nó không phải ID
của picking xem trước vì trước khi xác nhận chưa có picking thật trong cơ sở dữ
liệu.

### Các field được lưu trên model kho

- `stock.move.sale_split_group_key` ngăn các move thuộc những nhóm giao hàng dự
  kiến khác nhau bị gom chung.
- `stock.picking.sale_split_group_key` xác định nhóm giao hàng dự kiến đã tạo ra
  picking và hỗ trợ tìm picking khi gán move.

Module không thêm source location hoặc destination location riêng.
`location_id` và `location_dest_id` tiếp tục được xác định bởi warehouse route
và stock rule chuẩn.

## Các method kế thừa quan trọng

### `sale.order`

- `action_open_inventory_split_wizard()` kiểm tra đơn hàng có thể được xác nhận
  hay không, tạo kế hoạch tạm và mở modal.

### `sale.order.line`

- `_create_procurements()` gọi `super()` đối với luồng xác nhận thông thường.
  Với luồng split, method tạo một procurement chuẩn cho mỗi allocation sau khi
  quy đổi số lượng giữa đơn vị tính bán hàng và đơn vị tính procurement. Mỗi
  procurement nhận `sale_split_group_key` và `partner_id` đã được chọn.

Đây là điểm mở rộng chuẩn sớm nhất để biến một dòng Đơn bán hàng thành nhiều số
lượng procurement mà không cần thay thế `_action_launch_stock_rule()`.

### `stock.rule`

- `_get_custom_move_fields()` truyền `sale_split_group_key` từ procurement
  values sang stock move mới.
- `_get_stock_move_values()` tái sử dụng toàn bộ values do `super()` chuẩn bị và
  chỉ thay `stock.move.partner_id` đối với procurement thuộc luồng split. Việc
  này cần thiết vì logic chuẩn thường lấy partner của move từ procurement group
  dùng chung hoặc địa chỉ cấu hình trên rule, trong khi mỗi allocation cần một
  partner riêng.

### `stock.move`

- `_key_assign_picking()` thêm `sale_split_group_key` vào khóa gán picking trong
  bộ nhớ.
- `_search_picking_for_assignation_domain()` giới hạn việc tìm picking trong cơ
  sở dữ liệu theo cùng split group.
- `_get_new_picking_values()` sao chép split key sang picking mới. Logic chuẩn
  vẫn lấy `stock.picking.partner_id` từ các move đã được gom nhóm.
- `_prepare_merge_moves_distinct_fields()` ngăn move thuộc các split group khác
  nhau bị merge.
- `_prepare_procurement_values()` truyền split key và partner hiện tại của move
  qua các bước tiếp theo trong route nhiều bước.

### `stock.picking`

Model chỉ được thêm `sale_split_group_key`. Module không thêm field địa chỉ giao
hàng mới; `partner_id` chuẩn vẫn là địa chỉ giao hàng.

## Luồng xác nhận

1. Người dùng nhấn **Confirm with Split**.
2. Wizard tạo một phiếu giao hàng dự kiến và phân bổ toàn bộ số lượng còn lại
   hợp lệ vào phiếu đó.
3. Người dùng thêm các phiếu giao hàng, chuyển allocation giữa các phiếu, thay
   đổi số lượng và chọn địa chỉ giao hàng cho từng phiếu.
4. Backend kiểm tra mỗi phiếu có allocation, số lượng phân bổ là số dương, split
   key không trùng và tổng số lượng của từng dòng đơn hàng được phân bổ chính
   xác.
5. Wizard gọi `sale.order.action_confirm()` chuẩn và truyền kế hoạch split qua
   context.
6. Mỗi dòng đơn hàng tạo một procurement cho từng allocation. Stock rule tạo
   các move chuẩn mang theo split key và partner đã chọn.
7. Logic gán picking chuẩn chỉ gom các move có cùng split key. Sau đó values tạo
   picking chuẩn lấy partner chung của các move để gán vào
   `stock.picking.partner_id`.
8. Route nhiều bước tiếp tục truyền cùng split key và partner xuống các move
   tiếp theo. Các luồng gán picking, giữ hàng, tạo stock move line và xác nhận
   vẫn chạy theo logic chuẩn, không bị thay thế.
