# 🤖 Code Review Agent

**Code Review Agent** 是一个基于 **Gemini 2.5 Pro** 模型的智能代码审查系统。它结合了先进的 AI 大模型分析与传统的静态代码检查工具，为开发者提供全面、深入的代码质量反馈。

通过简洁的 Web 界面，您可以轻松上传单个代码文件、批量文件或整个 ZIP 项目包，系统将自动进行审查并生成详细的修复建议和优化报告。

---

## ✨ 核心功能

- **🤖 AI 智能审查**：利用 Google Gemini 2.5 Pro 模型，深入分析代码逻辑，发现潜在 Bug、安全漏洞及性能瓶颈，并提供重构后的代码示例。
- **🔬 静态代码分析**：集成多种静态分析工具，提供语法和规范性检查：
    - 🐍 **Python**: 使用 `pylint`
    - 🍎 **Swift**: 使用 `swiftlint`
    - 🇨 **C/C++**: 使用 `clang`
- **📂 多格式支持**：
    - 单个文件上传
    - 批量多文件上传
    - ZIP 压缩包上传（自动解压并递归审查）
- **📊 可视化报告**：提供直观的 HTML 报告，支持 Markdown 渲染，代码高亮显示。
- **🔌 RESTful API**：提供标准的 API 接口，方便集成到 CI/CD 流程或其他工具中。

---

## 🛠️ 环境要求

在运行本项目之前，请确保您的环境满足以下要求：

- **Python 3.10+**
- **Google GenAI API Key**：需要申请 Gemini API Key。

### 可选依赖（用于静态分析）
为了获得完整的静态检查功能，建议安装以下系统工具：
- **Pylint**: `pip install pylint` (通常包含在 requirements.txt 中)
- **SwiftLint**: (macOS) `brew install swiftlint`
- **Clang**: (macOS/Linux) 通常系统自带或通过 `xcode-select --install` / `apt install clang` 安装

---

## 🚀 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/mengyangyangs/CodeReview.git
cd CodeReview
```

### 2. 安装依赖

建议创建虚拟环境后安装依赖：

```bash
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

pip install -r requirements.txt
```

### 3. 配置 API Key

您需要将 Gemini API Key 设置为环境变量 `GENAI_API_KEY`。

**macOS/Linux:**
```bash
export GENAI_API_KEY="your_actual_api_key_here"
```

**Windows (PowerShell):**
```powershell
$env:GENAI_API_KEY="your_actual_api_key_here"
```

### 4. 启动服务

使用 `uvicorn` 启动 FastAPI 服务：

```bash
uvicorn main:app --reload
```

服务启动后，终端将显示访问地址，通常为：`http://127.0.0.1:8000`

---

## 📖 使用指南

### Web 界面

1. 打开浏览器访问 `http://127.0.0.1:8000`。
2. 点击 **"选择文件"** 按钮。
    - 您可以选择一个或多个代码文件（`.py`, `.js`, `.java`, `.cpp` 等）。
    - 也可以选择一个 `.zip` 压缩包（适合审查整个项目）。
3. 点击 **"开始审查"**。
4. 等待分析完成后，页面下方将展示每个文件的 AI 审查意见和静态检查结果。

### API 接口

您也可以通过 API 直接调用服务：

- **POST `/review`**: 上传单个文件进行审查。
- **POST `/review/multiple`**: 上传多个文件进行批量审查。
- **POST `/review/zip`**: 上传 ZIP 包，返回 JSON 格式的批量报告。
- **POST `/review/zip/pretty`**: 上传 ZIP 包，直接返回渲染好的 HTML 报告页面。

---

## 📂 项目结构

```text
CodeReviewAgent/
├── main.py              # FastAPI 后端核心逻辑
├── index.html           # 前端 UI 界面
├── requirements.txt     # Python 依赖列表
├── readme.md            # 项目说明文档
└── ...
```

## ⚠️ 注意事项

- 请确保您的 API Key 有足够的配额。
- 上传 ZIP 文件时，系统会自动过滤 `.DS_Store`、`__pycache__` 等无关文件，并跳过超过 5MB 的大文件。
- 静态分析依赖于宿主机的环境，如果未安装对应的 Linter 工具（如 swiftlint），静态检查部分将显示 "N/A"。

---

**Happy Coding! 🚀**