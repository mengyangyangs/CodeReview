# Code Review Agent - 智能代码审查系统

## 项目简介

Code Review Agent 是一个基于 FastAPI 框架和 Google Gemini 大语言模型构建的智能代码审查系统。它旨在帮助开发者快速、高效地发现代码中的潜在问题，如 Bug、安全漏洞、性能瓶颈以及提供优化建议。系统支持单个代码文件上传审查，更强大的是，它能够接收 .zip 压缩包，对其中的多个代码文件进行批量审查，并生成结构化的 JSON 报告或美观的 HTML 报告。前端界面简洁直观，用户体验友好。

## 主要特性

*   智能代码审查: 利用 Google Gemini 2.5 Pro 大语言模型，提供深入、专业的代码审查意见、修改建议，甚至尝试直接给出修改后的代码。
*   多语言支持: 通过文件扩展名自动识别 Python, Swift, C, C++, JavaScript, Java 等多种编程语言。
*   静态代码分析集成: 针对不同语言（如 Python 的 Pylint, Swift 的 SwiftLint, C/C++ 的 Clang），集成主流静态分析工具，提供额外的代码质量报告。
*   支持单文件审查: 用户可以直接上传单个代码文件获取即时审查结果。
*   支持 ZIP 压缩包批量审查: 革命性地支持上传 .zip 压缩包，系统会自动解压并审查包内的所有代码文件，尤其适用于项目级别的代码审查。
*   多种报告格式:
    *   JSON 报告: 提供机器可读的结构化审查数据，便于集成到 CI/CD 流程或其他自动化工具中。
    *   美观的 HTML 报告: 为批量审查结果生成一个排版优美、易于阅读的 HTML 页面，直观展示每个文件的审查详情。
*   友好的前端界面: 简洁的 Web UI，方便用户上传文件、查看审查进度和结果。
*   高效异步处理: 利用 FastAPI 的异步能力，确保在处理大文件或多个文件时系统的响应性和吞吐量。

## 快速开始

### 1. 克隆项目
git clone <项目仓库地址> # 替换为你的项目仓库地址
cd CodeReviewAgent

### 2. 设置 Gemini API Key
在运行之前，你需要一个 Google Gemini API Key。请访问 Google AI Studio (https://ai.google.dev/) 获取。

将你的 API Key 设置为系统环境变量：
export GENAI_API_KEY="YOUR_GEMINI_API_KEY"

### 3.创建虚拟环境并激活
建议使用Conda来构建环境
`conda create -n your_project_name python=3.10`，建议选择Python3.10版本
激活环境
`conda activate your_project_name`

### 4.安装各种依赖
pip install -r requestments.txt

### 5.在终端输入指令
uvicorn main:app --host 0.0.0.0 --port 8080，然后打开本地浏览器，`http://127.0.0.1:8000`

### 接口概览

*   `GET /`: 访问前端用户界面。
*   `POST /review`: 上传单个代码文件进行审查，返回 JSON 格式结果。
    *   `file`: (File) 要审查的代码文件。
*   `POST /review/zip`: 上传 .zip 压缩包进行批量审查，返回包含所有文件审查结果的 JSON 列表。
    *   `file`: (File) 要审查的 .zip 文件。
*   `POST /review/zip/pretty`: 上传 .zip 压缩包进行批量审查，返回美观的 HTML 报告页面。
    *   `file`: (File) 要审查的 .zip 文件。
 
### 前端界面

访问 `http://127.0.0.1:8000` 即可进入用户界面。

界面允许你：

1.  选择单个代码文件 (.py, .js, .swift, .c, .cpp, .java 等)。
2.  选择 .zip 压缩包。
3.  点击 "开始审查" 按钮。
4.  等待审查完成，结果将直接展示在页面上，对于 ZIP 文件会有详细的每个文件的报告。
PS:建议不要上传zip，因为会看到这个报错`调用 Gemini 模型时出错: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota... limit: 2... Please retry in 57.099437754s.'}`,说明你已达到当前配额限制（Quota Limit）。具体来说，你的免费配额（Free Tier）的限制是每分钟 2 个请求（limit: 2）。毕竟白嫖的，懂得都懂
