import os
import asyncio
import subprocess
import tempfile
import zipfile
import shutil
from typing import List # ⭐️ 新增：导入 List
from fastapi import FastAPI, File, UploadFile, HTTPException, status
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.concurrency import run_in_threadpool
from google import genai
import markdown2
from starlette.responses import FileResponse

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

async def get_review_data(filename: str, content: bytes) -> dict:
    """
    执行审查的核心逻辑，接收文件名和字节内容。
    """
    ext = os.path.splitext(filename)[1].lower()
    language_map = {".py": "Python", ".swift": "Swift", ".c": "C", ".cpp": "C++", ".js": "JavaScript", ".java": "Java"}
    language = language_map.get(ext, "Unknown")
    
    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            code_text = content.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            return {
                "filename": filename,
                "language": language,
                "static_check": "N/A",
                "gemini_review_markdown": "⚠️ 编码错误：文件编码不是有效的 UTF-8，无法审查。",
            }

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

        static_check = await run_static_analysis(tmp_path, ext)

        return {
            "filename": filename,
            "language": language,
            "static_check": static_check,
            "gemini_review_markdown": suggestion_md,
        }

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

async def run_static_analysis(tmp_path: str, ext: str) -> str:
    """
    异步运行静态分析工具。
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

@app.post("/review", summary="获取单个文件的 JSON 审查结果")
async def review_code_json(file: UploadFile = File(...)):
    """
    上传单个代码文件，返回 JSON 格式的审查报告。
    """
    content = await file.read()
    data = await get_review_data(file.filename, content)

    if "⚠️" in data["gemini_review_markdown"]:
         raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=data["gemini_review_markdown"]
            )
    
    data["gemini_review"] = data.pop("gemini_review_markdown")
    return JSONResponse(data)


# ⭐️ 新增：支持多个文件的 /review/multiple 接口
@app.post("/review/multiple", summary="获取多个文件的 JSON 审查结果")
async def review_multiple_files(files: List[UploadFile] = File(...)): # 接收 List[UploadFile]
    """
    上传多个代码文件，返回所有文件审查报告的列表。
    """
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请至少上传一个文件。"
        )

    tasks = []
    for file in files:
        content = await file.read()
        tasks.append(get_review_data(file.filename, content))
    
    results = await asyncio.gather(*tasks)

    formatted_results = []
    for res in results:
        res["gemini_review"] = res.pop("gemini_review_markdown")
        formatted_results.append(res)
            
    return JSONResponse({"results": formatted_results})


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
        tmp_zip_path = os.path.join(tempfile.gettempdir(), file.filename)
        content = await file.read()
        with open(tmp_zip_path, "wb") as f:
            f.write(content)

        tmp_extract_dir = tempfile.mkdtemp()
        with zipfile.ZipFile(tmp_zip_path, 'r') as zip_ref:
            zip_ref.extractall(tmp_extract_dir)

        tasks = []
        for root, _, files_in_dir in os.walk(tmp_extract_dir): # 更名为 files_in_dir 避免与函数参数 files 冲突
            for filename in files_in_dir:
                full_path = os.path.join(root, filename)
                
                if filename.startswith('.') or filename.endswith(('.DS_Store', 'LICENSE', 'README.md')):
                    continue

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
                
                relative_filename = os.path.relpath(full_path, tmp_extract_dir)
                
                tasks.append(get_review_data(relative_filename, file_content))

        results_from_zip = await asyncio.gather(*tasks) # 避免与外部 results 列表混淆

        formatted_results = []
        for res in results_from_zip: # 处理 zip 文件内的审查结果
            res["gemini_review"] = res.pop("gemini_review_markdown")
            formatted_results.append(res)
            
        results.extend(formatted_results) # 将 zip 文件内的结果合并到最终 results 列表中
            
        return JSONResponse({"results": results})

    except zipfile.BadZipFile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ZIP 文件损坏或格式不正确。"
        )
    finally:
        if tmp_zip_path and os.path.exists(tmp_zip_path):
            os.unlink(tmp_zip_path)
        if tmp_extract_dir and os.path.isdir(tmp_extract_dir):
            shutil.rmtree(tmp_extract_dir)


@app.post("/review/zip/pretty", response_class=HTMLResponse, summary="获取 ZIP 压缩包内所有文件的 HTML 审查报告")
async def review_zip_pretty_ui(file: UploadFile = File(...)):
    """
    上传 ZIP 文件，返回一个排版优美的 HTML 页面报告，包含所有文件的审查结果。
    """
    # 直接调用 review_zip 获取 JSON 数据
    response = await review_zip(file)
    data_json = json.loads(response.body.decode('utf-8')) # 直接从 response.body 解码

    all_reviews_html = ""
    
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

    html_content = f"""
    <html>
    <head>
        <title>ZIP Code Review 报告</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; line-height: 1.6; background-color: #f7f7f7; color: #333; margin: 0; padding: 20px; }}
            .container {{ max-width: 900px; margin: 20px auto; background-color: #ffffff; border: 1px solid #e0e0e0; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); overflow: hidden; }}
            .header {{ padding: 20px 30px; border-bottom: 2px solid #eee; }}
            .content {{ padding: 30px; }}
            .section h2 {{ font-size: 1.5em; color: #007aff; border-bottom: 2px solid #f0f0f0; padding-bottom: 5px; }}
            .file-header {{ font-size: 1.8em; color: #1a1a1a; margin-top: 40px; padding-bottom: 5px; border-bottom: 3px solid #007aff; }}
            pre {{ background-color: #282c34; color: #abb2bf; padding: 15px; border-radius: 6px; overflow-x: auto; white-space: pre-wrap; word-wrap: break-word; }}
            .gemini-review h3 {{ color: #333; }}
            .gemini-review code:not(pre > code) {{ background-color: #f0f0f0; color: #c7254e; padding: 2px 4px; border-radius: 4px; font-family: monospace; }}
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


@app.get("/", response_class=FileResponse, summary="提供前端 UI 界面")
async def get_frontend():
    """
    当用户访问根目录时，返回 index.html。
    """
    return FileResponse("index.html")
