# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

LanStream 是一个局域网媒体信息流系统（私有化 TikTok/小红书，支持本地/NAS 媒体）。阶段1-2已完成，包含完整的前后端功能，可发布使用。

## 常用命令

```bash
# 后端
uv run python main.py                      # 启动开发服务器 (0.0.0.0:8000, 热重载)
PYTHONPATH=. uv run python scripts/scan_mock.py [目录1] [目录2] ...  # 扫描媒体目录并导入 SQLite
uv run python scripts/generate_test_media.py  # 生成测试媒体文件到 test_media/
uv sync                                     # 安装/更新依赖
uv add <包名>                               # 添加新依赖

# 前端
cd frontend && npm run dev                  # 启动前端开发服务器 (localhost:5173, 代理 /api → 后端)
cd frontend && npm run build                # 构建前端生产版本
```

尚未配置测试框架。

## 架构

前后端分离架构。后端 FastAPI + 前端 Vue 3。

### 后端

FastAPI 异步后端，使用 SQLAlchemy 2.0 + SQLite (aiosqlite)，全部采用 async/await 模式。

**分层结构：**
- `main.py` → 入口，启动 uvicorn 加载 `app.main:app`
- `app/main.py` → FastAPI 应用，lifespan 中自动建表 + 数据库迁移，CORS 中间件
- `app/core/config.py` → `pydantic-settings` 配置，所有配置通过 `LANSTREAM_` 环境变量前缀覆盖
- `app/core/database.py` → 异步引擎 + 会话工厂 + `get_db` 依赖注入 + 自动迁移
- `app/models/media.py` → SQLAlchemy `Media` 模型 + `Base` 声明基类
- `app/schemas/media.py` → Pydantic 响应模型（`MediaOut`、`FeedResponse`、`RandomResponse`）
- `app/services/media.py` → 业务逻辑：目录扫描、Feed 查询、随机加载、文件夹浏览、收藏/删除、批量操作、导出
- `app/services/thumbnail.py` → 视频封面生成（Pillow）
- `app/api/media.py` → FastAPI 路由，包含以下端点：
  - `GET /api/media/feed` — 分页媒体列表，支持按类型/文件夹筛选
  - `GET /api/media/random` — 随机获取 N 个媒体，支持排除已加载和类型筛选
  - `GET /api/media/browse` — 文件夹层级浏览，支持按类型筛选
  - `GET /api/media/stream/{id}` — HTTP 206 Partial Content 流传输（视频播放核心）
  - `GET /api/media/thumbnail/{id}` — 视频封面图
  - `POST /api/media/{id}/favorite` — 切换收藏状态
  - `POST /api/media/{id}/delete` — 切换删除标记
  - `POST /api/media/manage/purge` — 物理删除所有标记删除的文件
  - `POST /api/media/manage/export-favorites` — 导出收藏到指定目录
  - `POST /api/media/manage/batch` — 批量收藏/取消/删除/恢复

### 前端

Vue 3 + TypeScript + TailwindCSS v4，Vite 开发服务器代理 API 请求到后端。

**结构：**
- `frontend/src/api/` — API 类型定义和 fetch 封装
- `frontend/src/composables/useFeed.ts` — 随机 Feed 状态管理（50个一批，排除已加载）
- `frontend/src/composables/useSwipe.ts` — 原生手势处理（轴向锁定、速度检测、wheel 事件）
- `frontend/src/composables/useTheme.ts` — 黑白主题切换（localStorage 持久化）
- `frontend/src/components/MediaCard.vue` — 媒体卡片（按钮在图片下方）
- `frontend/src/components/VideoPlayer.vue` — 视频播放模态框
- `frontend/src/components/TypeFilter.vue` — 全部/视频/图片筛选
- `frontend/src/components/FolderBrowser.vue` — 文件夹层级浏览器（面包屑导航）
- `frontend/src/components/RoamingView.vue` — TikTok 式全屏漫游（三卡片堆叠、跟手拖拽、弹性回弹）
- `frontend/src/views/FeedView.vue` — 瀑布流主页
- `frontend/src/views/ManageView.vue` — 桌面端管理页面（批量操作、导出、清理）
- `frontend/vite.config.ts` — Vite 配置（host: true 局域网访问，代理 /api）

**关键设计决策：**
- `Base` 定义在 `app/models/media.py` 中（非独立文件），新增模型时从该处导入
- 数据库自动迁移：`create_tables` 中通过 ALTER TABLE 添加新列，无需手动迁移
- 扫描时记录 `root_dir`（扫描主目录），支持文件夹层级浏览
- 扫描时跳过隐藏文件（`.` 开头）和系统文件（Thumbs.db 等）
- Feed 使用随机排序 + `exclude_ids` 避免重复，每次加载 50 个
- Range 请求解析支持所有标准格式（`bytes=0-`、`bytes=-500`、`bytes=0-499`）
- SQLite 数据库位于 `./data/lanstream.db`，启动时自动创建
- 瀑布流使用 CSS `column-count` + `break-inside: avoid`，桌面端 4 列、移动端 2 列
- 漫游模式使用三卡片堆叠 + CSS transform 实现跟手拖拽和弹性回弹
- 文件夹浏览使用 `os.sep` 替代硬编码 `/`，兼容 Windows 路径
- TailwindCSS v4 使用 `@tailwindcss/vite` 插件，CSS-first 配置，无需 `tailwind.config.js`

## 配置

配置项使用 `LANSTREAM_` 环境变量前缀（如 `LANSTREAM_DEBUG=false`）。关键默认值：
- `database_url`: `sqlite+aiosqlite:///./data/lanstream.db`
- `media_scan_dirs`: `["./test_media"]`
- `feed_page_size`: 20
- `supported_video_exts`: `{".mp4", ".webm", ".mkv", ".avi", ".mov", ".flv", ".m4v"}`
- `supported_image_exts`: `{".jpg", ".jpeg", ".png", ".webp", ".gif"}`

## 路线图

阶段1（已完成）：后端 MVP — 扫描、API、流传输、封面生成
阶段2（已完成）：Vue 3 前端 — 瀑布流浏览、漫游模式、文件夹浏览、收藏/删除、管理页面、黑白主题、局域网访问
阶段3：FFmpeg 封面生成、雪碧图预览（ArtPlayer 集成）
阶段4：watchdog 目录监控、标签系统、AI 联动
