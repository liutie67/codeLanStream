# 媒体来源失效处理：实现与验证

采用自动隐藏、保留记录方案。浏览时检查，管理页支持复查和后台全库检查；不做定期扫描或路径重绑定。

## 数据与接口

- `media.availability`：`available`、`missing`、`unavailable`；`availability_checked_at` 为最后一次检查时间。旧记录的时间为空，在返回浏览结果前检查。
- 收藏、删除和损坏分类独立保留。可读取根目录下的明确缺失记为 `missing`；根目录消失、权限错误或明确的 I/O 错误记为 `unavailable`。整批超时或探测进程异常不是对每个路径的确认：这类结果不写数据库，请求显示 503，全库任务报告失败且保留已经完成的结果。
- `/api/media/feed` 的查询参数和 `/api/media/random` 的请求体支持 `availability`，默认 `available`，也可选 `missing`、`unavailable`、`all`。管理页默认 `all`。
- `POST /api/media/manage/availability/probe`：`{"ids": [...]}`，返回复查后的媒体列表。
- `POST /api/media/manage/availability/remove-records`：同上，返回 `removed_count`。最多 200 个 ID；复查后若包含已恢复记录，返回 409，不删除该批索引。只改数据库，不删除源文件或调用物理清理接口。
- `POST /api/media/manage/availability/check` 创建或接回已有全库检查；同路径 `GET` 列出任务；`GET /{job_id}` 读取进度，`POST /{job_id}/cancel` 取消。任务存于独立的 `availability_check_jobs` 表。
- `/api/media/browse` 的根目录包含 `availability`；支持 `page`、`page_size`（默认 60，上限 200），返回 `total`、`has_next`；只验证当前页及判断下一页所需的记录。前端继续加载传递 `after_path` 文件路径游标，避免前一页的失效移除导致后续条目被跳过。选中目录缺失返回 404，权限错误返回 403，来源不可访问或超时返回 503。实际目录选择器也使用有超时的子进程枚举。

最多并发 2 个磁盘探测子进程，单次超时 3 秒，浏览总预算 8 秒，前端超时 10 秒。目录与原文件、缓存图片信息共用按路径的 5 秒 LRU 缓存，容量 4096；缓存命中不更新检查时间或写数据库。浏览后立即播放可复用文件大小，冷播放只需一次探测。手动复查和全库检查强制探测。探测不持有 SQLite 写事务；按原路径和检查时间条件更新，忽略过期结果。隐藏记录按最早检查时间分批复查，大量恢复可以主动全检。

`total` 统计尚未被确认失效的所有索引，包含迁移后检查时间为空的记录，避免首次打开把整个媒体库误报为一页的大小。返回的媒体仍需验证。缩略图/预览缺失单独返回缓存图片错误，不声称原文件缺失。漫游图片失败用响应式状态管理，单张重试更新 URL，保留位置、已加载条目和撤销历史。

启动时增量添加字段和索引，重复迁移安全；迁移错误会明确失败。全库任务关闭页面后继续运行，取消会终止当前探测；重启标记中断，已完成批次保留。

## 自动化验证

```bash
uv run python -m unittest discover -s tests
cd frontend
npm run test
npm run build
```

本次通过 49 项后端测试、26 项前端测试及生产构建。新增场景包括目录移走、单文件缺失、来源离线及恢复、分页与随机批次补齐、缓存失效、独立任务进度、取消正在执行的探测、重启中断、迟到结果、索引移除、重复迁移，以及前端超时和切换目录后的迟到响应。审查修复另覆盖整批超时不改状态、不允许移除未确认索引、健康来源继续浏览、冷播放一次探测/热播放零探测零写入、缓存容量与作用域复用、分页游标不漏项、首次加载计数及手动复查不复用旧探测。实际漫游组件验证单张重试、保留前后历史和撤销、忽略旧复查响应，以及先刷新文件信息再重新加载。切换目录会清除上一页的加载更多状态。任务完成状态在检查点落库后才对外发布。

## 页面验收

使用独立临时 SQLite 和生成的示例图片启动本机验证服务；未操作个人媒体目录。确认主页仅显示可用媒体，管理页保留失效记录的分类；选中目录不可访问时结束加载并能返回；将示例文件夹移回原路径并复查后，照片重新显示且收藏和删除分类保留。

- [灰色根目录入口](screenshots/availability-roots.jpg)
- [失效目录提示与返回入口](screenshots/availability-folder-error.jpg)
- [检查结果、失效记录与索引操作](screenshots/availability-manage.jpg)
- [恢复原路径后保留收藏与删除分类](screenshots/availability-restored.jpg)
- [文件夹首次仅加载 60/65 项](screenshots/availability-folder-page.jpg)
- [点击加载更多后完整显示 65/65 项](screenshots/availability-folder-page-complete.jpg)
- [第 2 张漫游图片失败提示](screenshots/availability-roaming-retry-before.jpg)
- [替换临时图片并重试后恢复，位置和文件名保持不变](screenshots/availability-roaming-retry-after.jpg)

没有接入真实 NAS 或拔插个人硬盘。慢盘、权限错误和进程终止由自动化测试模拟验证；页面使用移动临时目录复现失效与恢复。
