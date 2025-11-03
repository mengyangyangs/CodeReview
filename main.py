import os
import asyncio
import subprocess
import tempfile
import zipfile # ⭐️ 新增：导入 zipfile
import shutil # ⭐️ 新增：用于删除整个临时目录
from fastapi import FastAPI, File, UploadFile, HTTPException, status
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.concurrency import run_in_threadpool
from google import genai
import markdown2
from starlette.responses import FileResponse

# --- [初始化代码，保持不变] ---
os.environ["OBJC_DISABLE_INITIALIZE_FORK_SAFETY"] = "YES"
app = FastAPI(title="Code Review Agent", description="基于 Gemini 模型的智能代码审查系统", version="1.0")

GEMINI_API_KEY = os.getenv("GENAI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("请先在系统环境中设置 GENAI_API_KEY")
try:
    client = genai.Client(api_key=GEMINI_API_KEY)
    MODEL_NAME = "gemini-2.5-pro"
except Exception as e:
    print(f"初始化 Gemini 客户端失败: {e}")
    raise

# ------------------------------------
# ⭐️ 修改：get_review_data 核心逻辑
# ------------------------------------
async def get_review_data(filename: str, content: bytes) -> dict:
    """
    执行审查的核心逻辑，不再依赖 UploadFile，而是接收文件名和字节内容。
    """
    ext = os.path.splitext(filename)[1].lower()
    language_map = {".py": "Python", ".swift": "Swift", ".c": "C", ".cpp": "C++", ".js": "JavaScript", ".java": "Java"}
    language = language_map.get(ext, "Unknown")
    
    tmp_path = ""
    try:
        # 将字节内容写入临时文件，供静态分析工具使用
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            # 严格检查 UTF-8 编码
            code_text = content.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            # 对于压缩包内的文件，我们不抛出 HTTPException，而是返回错误信息
            return {
                "filename": filename,
                "language": language,
                "static_check": "N/A",
                "gemini_review_markdown": "⚠️ 编码错误：文件编码不是有效的 UTF-8，无法审查。",
            }

        # 2️⃣ Gemini 模型审查
        prompt = f"""
你是一位资深软件工程师，请对以下 {language} 代码进行专业 code review：
- 找出潜在 bug、安全问题和性能问题；
- 给出修改建议；
- 尝试直接提供修改后的代码（只输出修改后的完整代码）；
--------------------
{code_text}
"""
        suggestion_md = ""
        try:
            response = await run_in_threadpool(
                client.models.generate_content,
                model=MODEL_NAME,
                contents=prompt
            )
            suggestion_md = response.text
        except Exception as e:
            suggestion_md = f"⚠️ 调用 Gemini 模型时出错: {str(e)}"


        # 3️⃣ 异步静态分析
        static_check = await run_static_analysis(tmp_path, ext)

        # 4️⃣ 返回结构化数据
        return {
            "filename": filename,
            "language": language,
            "static_check": static_check,
            "gemini_review_markdown": suggestion_md,
        }

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

# --- [run_static_analysis 函数，保持不变] ---
# ... (原 run_static_analysis 函数代码) ...
async def run_static_analysis(tmp_path: str, ext: str) -> str:
    """
    异步运行静态分析工具。(代码与你提供的一致)
    """
    command = []
    if ext == ".py":
        command = ["pylint", tmp_path, "--score=n"]
    elif ext == ".swift":
        command = ["swiftlint", "lint", "--path", tmp_path]
    elif ext in [".c", ".cpp"]:
        command = ["clang", "-fsyntax-only", tmp_path]
    else:
        return "N/A (静态检查未对此语言配置)"
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(process.communicate(), timeout=20.0)
        stdout = stdout_bytes.decode("utf-8", errors="ignore")
        stderr = stderr_bytes.decode("utf-8", errors="ignore")
        if ext in [".c", ".cpp"]:
            return stderr if stderr else "[Clang] 未发现语法错误。"
        else:
            return stdout if stdout else "[Linter] 未发现问题。"
    except asyncio.TimeoutError:
        try:
            process.terminate()
            await process.wait()
        except ProcessLookupError:
            pass
        return f"静态检查超时 (超过 20 秒)。"
    except FileNotFoundError:
        return f"[错误] 静态检查工具 '{command[0]}' 未安装或不在系统 PATH 中。"
    except Exception as e:
        return f"静态检查时发生意外错误: {str(e)}"

# ------------------------------------
# ⭐️ 修改：支持单个文件的 /review (JSON) 接口
# ------------------------------------
@app.post("/review", summary="获取单个文件的 JSON 审查结果")
async def review_code_json(file: UploadFile = File(...)):
    """
    上传单个代码文件，返回 JSON 格式的审查报告。
    """
    content = await file.read()
    data = await get_review_data(file.filename, content)

    # 如果是单个文件，且发生编码错误或 Gemini 错误，直接返回 HTTP 错误
    if "⚠️" in data["gemini_review_markdown"]:
         raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=data["gemini_review_markdown"]
            )
    
    data["gemini_review"] = data.pop("gemini_review_markdown")
    return JSONResponse(data)


# ------------------------------------
# ⭐️ 新增：支持 ZIP 文件的 /review/zip 接口
# ------------------------------------
@app.post("/review/zip", summary="获取 ZIP 压缩包内所有文件的 JSON 审查结果")
async def review_zip(file: UploadFile = File(...)):
    """
    上传 ZIP 文件，返回包内所有代码文件的审查报告列表。
    """
    if not file.filename.lower().endswith('.zip'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请上传 .zip 格式的压缩文件。"
        )

    tmp_zip_path = ""
    tmp_extract_dir = ""
    results = []
    
    try:
        # 1. 保存上传的 ZIP 文件
        tmp_zip_path = os.path.join(tempfile.gettempdir(), file.filename)
        content = await file.read()
        with open(tmp_zip_path, "wb") as f:
            f.write(content)

        # 2. 解压 ZIP 文件
        tmp_extract_dir = tempfile.mkdtemp()
        with zipfile.ZipFile(tmp_zip_path, 'r') as zip_ref:
            zip_ref.extractall(tmp_extract_dir)

        # 3. 遍历解压后的文件并审查
        tasks = []
        for root, _, files in os.walk(tmp_extract_dir):
            for filename in files:
                full_path = os.path.join(root, filename)
                
                # 忽略隐藏文件或配置文件
                if filename.startswith('.') or filename.endswith(('.DS_Store', 'LICENSE', 'README.md')):
                    continue

                # 检查文件大小，避免 OOM
                if os.path.getsize(full_path) > 5 * 1024 * 1024: # 5MB
                    results.append({
                        "filename": filename,
                        "language": "N/A",
                        "static_check": "N/A",
                        "gemini_review_markdown": "⚠️ 文件过大（>5MB），已跳过审查。",
                    })
                    continue

                with open(full_path, "rb") as f:
                    file_content = f.read()
                
                # 使用相对路径作为文件名，保持清晰
                relative_filename = os.path.relpath(full_path, tmp_extract_dir)
                
                # 创建异步任务
                tasks.append(get_review_data(relative_filename, file_content))

        # 4. 并发执行所有审查任务
        results = await asyncio.gather(*tasks)

        # 5. 格式化结果并返回
        formatted_results = []
        for res in results:
            res["gemini_review"] = res.pop("gemini_review_markdown")
            formatted_results.append(res)
            
        return JSONResponse({"results": formatted_results})

    except zipfile.BadZipFile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ZIP 文件损坏或格式不正确。"
        )
    finally:
        # 6. 清理临时文件和目录
        if tmp_zip_path and os.path.exists(tmp_zip_path):
            os.unlink(tmp_zip_path)
        if tmp_extract_dir and os.path.isdir(tmp_extract_dir):
            shutil.rmtree(tmp_extract_dir)


# ------------------------------------
# ⭐️ ZIP 格式的 HTML 渲染接口 (新增)
# ------------------------------------
@app.post("/review/zip/pretty", response_class=HTMLResponse, summary="获取 ZIP 压缩包内所有文件的 HTML 审查报告")
async def review_zip_pretty_ui(file: UploadFile = File(...)):
    """
    上传 ZIP 文件，返回一个排版优美的 HTML 页面报告，包含所有文件的审查结果。
    """
    # 直接调用 review_zip 获取 JSON 数据
    response = await review_zip(file)
    data = response.body.decode('utf-8')
    data = JSONResponse.render(response).body.decode('utf-8')
    data_json = JSONResponse.content(response) # 无法直接获取 content，我们假设 response.body 是 JSON 字符串
    
    # 重新解析 JSON 数据
    import json
    try:
        data_json = json.loads(data)
    except Exception as e:
        # 如果解析失败，返回错误页面
        return HTMLResponse(f"<h1>Error</h1><p>Failed to parse review data: {e}</p>", status_code=500)

    all_reviews_html = ""
    
    # 遍历所有文件结果并渲染
    for result in data_json.get("results", []):
        filename = result.get('filename', 'N/A')
        language = result.get('language', 'N/A')
        gemini_md = result.get('gemini_review', '')
        static_check = result.get('static_check', '')
        
        gemini_html = markdown2.markdown(
            gemini_md,
            extras=["fenced-code-blocks", "tables", "cuddled-lists"]
        )
        static_check_html = f"<pre><code>{static_check}</code></pre>"
        
        all_reviews_html += f"""
        <div class="file-section">
            <h2 class="file-header">📁 文件: {filename} ({language})</h2>
            <div class="section">
                <h2>🤖 Gemini 智能审查</h2>
                <div class="gemini-review">
                    {gemini_html}
                </div>
            </div>
            <div class="section">
                <h2>🔬 静态分析 (Linter)</h2>
                {static_check_html}
            </div>
        </div>
        <hr style="border: 0; border-top: 1px dashed #ccc; margin: 30px 0;">
        """

    # 最终 HTML 模板
    html_content = f"""
    <html>
    <head>
        <title>ZIP Code Review 报告</title>
        <style>
            /* 复用大部分样式，新增 file-header 样式 */
            body {{ font-family: -apple-system, ... }}
            .container {{ max-width: 900px; ... }}
            .header {{ padding: 20px 30px; border-bottom: 2px solid #eee; }}
            .content {{ padding: 30px; }}
            .section h2 {{ font-size: 1.5em; color: #007aff; border-bottom: 2px solid #f0f0f0; padding-bottom: 5px; }}
            .file-header {{ font-size: 1.8em; color: #1a1a1a; margin-top: 40px; padding-bottom: 5px; border-bottom: 3px solid #007aff; }}
            pre {{ background-color: #282c34; ... }}
            .gemini-review h3 {{ color: #333; ... }}
            /* ... (省略其他样式以保持简洁) ... */
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>ZIP 压缩包 Code Review 报告</h1>
                <p>包含 {len(data_json.get("results", []))} 个文件的审查结果。</p>
            </div>
            <div class="content">
                {all_reviews_html}
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


# ------------------------------------
# 根路由保持不变
# ------------------------------------
@app.get("/", response_class=FileResponse, summary="提供前端 UI 界面")
async def get_frontend():
    """
    当用户访问根目录时，返回 index.html。
    """
    return FileResponse("index.html")
