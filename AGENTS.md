# 仓库指南

## 项目结构与模块组织

LanStream 采用前后端分离架构：后端是 FastAPI，前端是 Vue 3 + Vite。后端代码位于 `app/`：`app/main.py` 创建 FastAPI 应用，`app/api/` 定义接口路由，`app/services/` 放媒体扫描和业务逻辑，`app/models/` 放 SQLAlchemy 模型，`app/schemas/` 放 Pydantic 响应模型。根目录 `main.py` 是后端启动入口。前端代码位于 `frontend/src/`，其中 `api/` 封装请求，`composables/` 存放复用状态逻辑，`components/` 存放组件，`views/` 存放页面。`scripts/` 是工具脚本，`data/` 是运行时 SQLite 数据库目录，`test_media/` 是本地测试媒体目录。

## 构建、测试与开发命令

- `uv sync`：安装或更新 Python 依赖。
- `uv run python main.py`：启动后端服务，默认监听 `0.0.0.0:8000`。
- `PYTHONPATH=. uv run python scripts/scan_mock.py /path/to/media`：扫描媒体文件并写入 SQLite。
- `uv run python scripts/generate_test_media.py`：生成测试媒体到 `test_media/`。
- `cd frontend && npm install`：安装前端依赖。
- `cd frontend && npm run dev`：启动 Vite 开发服务器，默认端口 `5173`。
- `cd frontend && npm run build`：执行 `vue-tsc` 类型检查并构建生产资源。

## 编码风格与命名约定

后端使用 Python 3.12；涉及 FastAPI、异步 SQLAlchemy 会话或 I/O 的代码应保持 `async/await` 风格。Python 代码使用 4 空格缩进、类型标注和清晰的服务层划分；模块、函数和数据库字段使用 `snake_case`。前端使用 Vue 单文件组件，统一采用 `<script setup lang="ts">`；TypeScript 标识符使用 `camelCase`，组件文件使用 `PascalCase`。样式以 TailwindCSS 工具类为主，优先遵循现有组件写法。

## 测试指南

当前尚未配置自动化测试框架。提交前至少运行 `cd frontend && npm run build`，并用 `uv run python main.py` 手动验证受影响的后端接口或前端流程。新增测试时，请同步记录运行命令，保持 fixture 体积小，并避免依赖个人本地媒体路径。

## 提交与 Pull Request 规范

近期提交使用 Conventional Commit 前缀，例如 `feat:`、`fix:`，后接简洁中文说明。除非项目另行调整，继续沿用该格式。Pull Request 应说明用户可见变更、列出验证步骤、标明数据库或配置影响；涉及 UI 的改动应附截图或录屏。