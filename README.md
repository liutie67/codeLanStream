# LanStream

局域网媒体信息流系统 — 私有化 TikTok / 小红书，支持本地和 NAS 媒体浏览。

## 功能

- **瀑布流浏览** — 随机展示媒体，桌面端 4 列、移动端 2 列自适应布局
- **漫游模式** — TikTok 式全屏滑动浏览，视频自动播放，左滑删除右滑收藏
- **文件夹浏览** — 按目录层级浏览媒体库，支持面包屑导航和类型筛选
- **视频流传输** — HTTP 206 Range 请求，支持拖动进度条和断点续传
- **收藏与软删除** — 标记收藏/删除后媒体仍可浏览，桌面端管理页面支持批量操作
- **导出收藏** — 一键复制所有收藏媒体到指定目录
- **深色/浅色主题** — 一键切换，状态持久化
- **局域网访问** — 手机、平板等设备可直接访问电脑上的媒体库
- **跨平台** — 支持 macOS、Windows、Linux，路径分隔符自动适配

## 支持的媒体格式

**视频：** mp4, webm, mkv, avi, mov, flv, m4v（大小写不敏感）

**图片：** jpg, jpeg, png, webp, gif

## 快速开始

### 前置要求

- Python >= 3.12
- Node.js >= 18
- [uv](https://docs.astral.sh/uv/)（Python 包管理器）

### 安装

```bash
# 克隆仓库
git clone https://github.com/your-username/codeLanStream.git
cd codeLanStream

# 安装后端依赖
uv sync

# 安装前端依赖
cd frontend && npm install && cd ..
```

### 扫描媒体

```bash
# macOS / Linux
PYTHONPATH=. uv run python scripts/scan_mock.py /path/to/your/media

# Windows PowerShell
$env:PYTHONPATH="."; uv run python scripts/scan_mock.py C:\Pictures

# 多个目录
PYTHONPATH=. uv run python scripts/scan_mock.py /photos /videos /screenshots
```

扫描是增量操作：重复扫描同一目录只会导入新增文件，不会重复入库。

### 启动服务

```bash
# 终端 1：启动后端（端口 8000）
uv run python main.py

# 终端 2：启动前端开发服务器（端口 5173）
cd frontend && npm run dev
```

浏览器访问 `http://localhost:5173`。

局域网设备访问 `http://<电脑IP>:5173`（前端会自动监听所有网络接口）。

### 生产部署

```bash
# 构建前端
cd frontend && npm run build && cd ..

# 后端直接服务前端静态文件（需配置反向代理或使用 main.py 中的静态文件挂载）
uv run python main.py
```

## 配置

所有配置项通过 `LANSTREAM_` 环境变量前缀覆盖：

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `LANSTREAM_DATABASE_URL` | `sqlite+aiosqlite:///./data/lanstream.db` | 数据库连接 |
| `LANSTREAM_MEDIA_SCAN_DIRS` | `["./test_media"]` | 默认扫描目录（JSON 数组） |
| `LANSTREAM_FEED_PAGE_SIZE` | `20` | 每页媒体数量 |
| `LANSTREAM_DEBUG` | `true` | 调试模式（输出 SQL 日志） |

示例：
```bash
LANSTREAM_DEBUG=false LANSTREAM_MEDIA_SCAN_DIRS='["/photos","/videos"]' uv run python main.py
```

## 项目结构

```
codeLanStream/
├── app/                          # 后端
│   ├── main.py                   # FastAPI 应用入口
│   ├── core/
│   │   ├── config.py             # 配置管理
│   │   └── database.py           # 数据库引擎 + 会话
│   ├── models/
│   │   └── media.py              # Media 模型
│   ├── schemas/
│   │   └── media.py              # Pydantic 响应模型
│   ├── services/
│   │   ├── media.py              # 业务逻辑
│   │   └── thumbnail.py          # 视频封面生成
│   └── api/
│       └── media.py              # API 路由
├── frontend/                     # 前端
│   ├── src/
│   │   ├── api/                  # API 类型 + fetch 封装
│   │   ├── composables/          # Vue composables
│   │   ├── components/           # UI 组件
│   │   └── views/                # 页面视图
│   └── vite.config.ts            # Vite 配置（代理 + 局域网）
├── scripts/                      # 工具脚本
│   ├── scan_mock.py              # 媒体扫描入库
│   └── generate_test_media.py    # 生成测试媒体
├── data/                         # SQLite 数据库（运行时生成）
└── test_media/                   # 测试媒体文件
```

## 技术栈

**后端：** Python 3.12 · FastAPI · SQLAlchemy 2.0 · SQLite (aiosqlite) · Pillow

**前端：** Vue 3 · TypeScript · TailwindCSS v4 · Vite · Vue Router

## License

MIT
