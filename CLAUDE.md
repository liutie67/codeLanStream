# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

LanStream 是一个局域网媒体信息流系统（支持本地/NAS的私有化 TikTok/小红书）。当前处于阶段1-2：后端 MVP + 前端基础信息流。完整的4阶段路线图记录在 `docs/` 中。

## 常用命令

```bash
# 后端
uv run python main.py                      # 启动开发服务器 (0.0.0.0:8000, 热重载)
uv run python scripts/scan_mock.py [目录]  # 扫描目录并将媒体导入 SQLite
uv run python scripts/generate_test_media.py  # 生成测试媒体文件到 test_media/
PYTHONPATH=. uv run python scripts/scan_mock.py  # 扫描脚本需要设置 PYTHONPATH
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
- `app/main.py` → FastAPI 应用，lifespan 中自动建表，CORS 中间件
- `app/core/config.py` → `pydantic-settings` 配置，所有配置通过 `LANSTREAM_` 环境变量前缀覆盖
- `app/core/database.py` → 异步引擎 + 会话工厂 + `get_db` 依赖注入
- `app/models/media.py` → SQLAlchemy `Media` 模型 + `Base` 声明基类
- `app/schemas/media.py` → Pydantic 响应模型（`MediaOut`、`FeedResponse`）
- `app/services/media.py` → 业务逻辑：目录扫描、Feed 查询、Range 请求解析
- `app/api/media.py` → FastAPI 路由，包含3个端点：
  - `GET /api/media/feed` — 分页媒体列表，支持按类型/文件夹筛选
  - `GET /api/media/random` — 随机获取 N 个媒体
  - `GET /api/media/stream/{id}` — HTTP 206 Partial Content 流传输（视频播放的核心）

### 前端

Vue 3 + TypeScript + TailwindCSS v4，Vite 开发服务器代理 API 请求到后端。

**结构：**
- `frontend/src/api/` — API 类型定义和 fetch 封装
- `frontend/src/composables/useFeed.ts` — Feed 分页状态管理
- `frontend/src/components/` — UI 组件（MediaCard、VideoPlayer、TypeFilter、LoadMore）
- `frontend/src/views/FeedView.vue` — 瀑布流主页（CSS columns 实现）
- `frontend/vite.config.ts` — Vite 代理配置（`/api` → `http://127.0.0.1:8000`）

**关键设计决策：**
- `Base` 定义在 `app/models/media.py` 中（非独立文件），新增模型时从该处导入
- Feed 分页使用 `LIMIT + 1` 技巧判断 `has_next`，无需额外计数查询
- Range 请求解析支持所有标准格式（`bytes=0-`、`bytes=-500`、`bytes=0-499`）
- SQLite 数据库位于 `./data/lanstream.db`，启动时自动创建
- 瀑布流使用 CSS `column-count` + `break-inside: avoid`，零依赖
- TailwindCSS v4 使用 `@tailwindcss/vite` 插件，CSS-first 配置，无需 `tailwind.config.js`
- 前端通过 Vite 代理访问后端 API，开发时无 CORS 问题

## 配置

配置项使用 `LANSTREAM_` 环境变量前缀（如 `LANSTREAM_DEBUG=false`）。关键默认值：
- `database_url`: `sqlite+aiosqlite:///./data/lanstream.db`
- `media_scan_dirs`: `["./test_media"]`
- `feed_page_size`: 20

## 路线图

阶段1（已完成）：后端 MVP — 扫描、API、流传输
阶段2（进行中）：Vue 3 + TailwindCSS 前端，瀑布流/滑动信息流
阶段3：FFmpeg 封面生成、雪碧图预览（ArtPlayer 集成）
阶段4：watchdog 目录监控、标签系统、AI 联动
