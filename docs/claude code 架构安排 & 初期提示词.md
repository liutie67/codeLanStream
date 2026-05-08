# claude code 架构安排 & 初期提示词

> 我打算在pycharm里用claude code开启这个项目，帮我列一个模块计划清单，并写一个开启项目初级阶段的提示词
> 

使用 PyCharm 结合 Claude Code 启动这个项目是一个极其高效的选择。Claude Code 作为命令行/IDE内置的智能体，非常擅长处理这种从零开始的脚手架搭建和样板代码编写。

为了让 Claude 能够准确理解并按部就班地工作，我们需要将这个宏大的系统拆解为清晰的模块，并为它提供一个“约束明确、目标清晰”的初始提示词。

### 一、 项目模块计划清单 (Roadmap)

建议采用**前后端分离**的架构，并在初期聚焦于“跑通主链路”，再逐步添加高级媒体处理和 AI 功能。

### 阶段 1：后端基建与 MVP (最小可行性产品) —— **当前阶段**

- **[模块] 项目脚手架:** 使用 `uv` 初始化 Python 环境和 FastAPI 项目结构。
- **[模块] 数据库核心 (`database`):** 定义 SQLite (前期用于快速开发) 模型，包含 `Media` 表 (ID, 路径, 类型, 宽高, 时长, 创建时间)。
- **[模块] 本地扫描器 (`scanner`):** 编写脚本遍历指定本地测试目录，识别 `.mp4`, `.jpg`, `.webp` 等文件，提取基础元数据并入库。
- **[模块] 核心 API (`routers`):**
    - `GET /api/feed`: 支持分页 (`page`, `size`) 获取媒体列表。
    - `GET /api/media/{id}`: 基于 HTTP `206 Partial Content` (Range Requests) 的媒体流传输接口 (这是不卡顿的核心)。

### 阶段 2：前端基建与基础信息流

- **[模块] 前端脚手架:** 使用 Vite + Vue 3 + TailwindCSS 初始化项目。
- **[模块] API 封装:** 使用 Axios 或 Fetch 配置与 FastAPI 后端的交互。
- **[模块] 瀑布流/滑动组件:** 引入 `vue-masonry` 或实现基础的上下滑动列表。
- **[模块] 基础播放器:** 引入 `ArtPlayer.js`，实现基础的视频加载和播放逻辑。

### 阶段 3：媒体深加工 (破局点)

- **[模块] 封面生成器 (`media_processor`):** 监听新入库视频，调用 FFmpeg 异步截取首帧/关键帧生成 `.webp` 封面并更新数据库。
- **[模块] 预览雪碧图 (`sprite_generator`):** 针对长视频，异步生成雪碧图及 `.vtt` 文件，打通前端 ArtPlayer 的进度条预览功能。
- **[模块] 缓存策略:** 完善静态资源 (封面、雪碧图) 的高速路由。

### 阶段 4：进阶与 AI 赋能

- **[模块] 目录监听 (`watchdog`):** 实现文件系统的热更新，NAS/本地文件夹有新文件立刻自动入库。
- **[模块] 标签与分类:** 增加目录树解析，支持按文件夹、类型过滤。
- **[模块] AI 联动:** 接入你的大模型脚本，实现自动打标签或摘要生成。

---

### 二、 Claude Code 启动提示词 (Prompt)

不要试图一次性让大模型写出所有代码，这会导致上下文混乱。我们第一步的提示词只聚焦于“阶段 1”的后端搭建。

请在 PyCharm 中唤出 Claude Code，并直接发送以下这段精心设计的 Prompt：

---

```
你现在是一位资深的 Python 全栈架构师。我们需要从零开始开发一个名为 "LanStream" 的局域网高性能媒体信息流系统（类似支持本地 NAS 的私有化 TikTok/小红书）。

当前任务：完成后端 MVP（最小可行性产品）的脚手架搭建。

【技术栈限制】
- 包管理与环境：必须使用 `uv`。
- Web 框架：FastAPI + Uvicorn。
- 数据库：SQLAlchemy 2.0 + SQLite（前期快速验证使用）。
- 异步编程：全程使用 async/await 模式。

【执行步骤】
请你一步步执行以下操作，并在每完成一步后向我确认，不要一次性全部生成：

1. 项目初始化：
   - 请使用 `uv init` 或标准 python 结构创建一个规范的 FastAPI 项目目录结构。推荐结构：包含 `main.py`, `core/`, `models/`, `api/`, `services/`。
   - 生成对应的 `pyproject.toml`，包含 fastapi, uvicorn, sqlalchemy, aiosqlite 等核心依赖。

2. 数据库设计 (models & db)：
   - 编写数据库连接器 (异步 SQLite)。
   - 设计一个 `Media` 表模型，字段至少包含：id (uuid), file_path (绝对路径, str), media_type (枚举: video/image), size_bytes (int), duration (float, 可为空), created_at (datetime)。

3. 核心 API 开发 (api & services)：
   - 编写 `GET /api/media/feed` 接口：支持按时间倒序返回数据库中的媒体列表，需支持 cursor 或 page 分页。
   - 编写 `GET /api/media/stream/{media_id}` 接口：**极其重要**，由于是为了前端视频流播放，此接口必须实现对 HTTP Range Requests (206 Partial Content) 的完美支持，以确保视频可以分段加载和拖拽，不能直接将整个视频文件读入内存。

4. 简易测试脚本：
   - 编写一个独立的 `scripts/scan_mock.py` 脚本：能够扫描本地的一个指定测试文件夹（如 `./test_media`），将其中的 `.mp4` 和 `.jpg` 文件路径写入 SQLite 数据库，用于后续 API 测试。

请先阅读并理解整个任务，然后从第 1 步开始执行。在此过程中遇到任何路径或配置不确定的地方，请随时询问我。
```

---

### 💡 执行建议

1. **循序渐进:** Claude Code 会根据这个提示词开始创建文件和写入代码。当它完成一步时，花几秒钟检查一下它的目录结构是否符合你的习惯。
2. **Range Requests 重点关注:** 提示词中特别强调了 `206 Partial Content`。这是流媒体服务器的灵魂。检查它生成的代码中是否包含了对 `request.headers.get("range")` 的处理，如果没有，要求它重写该接口。
3. **运行跑通:** 当它完成这 4 步后，你自己创建一个 `test_media` 文件夹扔几个短视频进去，运行它的脚本和 FastAPI 服务，用浏览器或者 Postman 测试一下 `http://127.0.0.1:8000/api/media/feed` 是否能正确返回 JSON 数据，流接口能否正确起播视频。

跑通这套后端闭环后，我们再开始用下一个 Prompt 让它去构建 Vue 3 的前端瀑布流界面。