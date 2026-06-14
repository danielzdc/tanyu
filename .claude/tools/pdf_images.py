#!/usr/bin/env python3
"""
PDF Image Extractor + Visual Analyzer
用法: python pdf_images.py <input.pdf> [--no-ocr]
输出: <input>_images/ 目录，包含提取的图片和文字描述
"""
import base64
import json
import os
import sys
import urllib.request
from pathlib import Path

import fitz  # PyMuPDF

# 硅基流动 API 配置（与 VLM Bridge 共享）
API_BASE = "https://api.siliconflow.cn/v1"
API_KEY = "sk-ytajnbzhednhbfymtxwxhviptexejvjickdwydzfbzuyshaj"
MODEL = "Qwen/Qwen3-VL-30B-A3B-Instruct"

VISION_PROMPT = """Analyze this image extracted from a PDF document.
If it contains a chart, graph, or diagram: describe the data, trends, labels, axes, and key findings.
If it contains a table: extract all rows and columns as structured text.
If it contains text/screenshot/formula: transcribe ALL text completely, including Chinese characters.
If it's a photo or illustration: describe what's shown and any relevant details.
Reply in Chinese if the image content is in Chinese, otherwise use English."""


def extract_images(pdf_path: str, output_dir: Path) -> list[dict]:
    """从 PDF 中提取所有嵌入图片"""
    doc = fitz.open(pdf_path)
    images = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        # 方法1：获取页面上的图片
        image_list = page.get_images(full=True)

        for img_idx, img_info in enumerate(image_list):
            xref = img_info[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
            ext = base_image["ext"]

            # 跳过太小（可能是图标/decorative）
            if len(image_bytes) < 1024:
                continue

            filename = f"page{page_num + 1}_img{img_idx + 1}.{ext}"
            filepath = output_dir / filename
            with open(filepath, "wb") as f:
                f.write(image_bytes)

            images.append({
                "page": page_num + 1,
                "index": img_idx + 1,
                "filename": filename,
                "path": str(filepath),
                "size_kb": round(len(image_bytes) / 1024, 1),
                "ext": ext,
            })

    doc.close()
    return images


def call_vision(image_path: str) -> str | None:
    """调用视觉模型分析单张图片"""
    # 读取并编码
    with open(image_path, "rb") as f:
        data = f.read()

    if len(data) > 10 * 1024 * 1024:
        return f"[SKIP: 图片过大 {len(data) / 1024 / 1024:.1f} MB]"

    ext = Path(image_path).suffix.lower().lstrip(".")
    mime_map = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "gif": "gif", "webp": "webp", "bmp": "bmp"}
    mime = mime_map.get(ext, "png")
    img_b64 = base64.b64encode(data).decode()

    payload = {
        "model": MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/{mime};base64,{img_b64}"}},
                {"type": "text", "text": VISION_PROMPT},
            ],
        }],
        "max_tokens": 2000,
        "temperature": 0.1,
    }

    req = urllib.request.Request(
        f"{API_BASE}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"]
    except Exception as e:
        return f"[ERROR: {e}]"


def main():
    if len(sys.argv) < 2:
        print("用法: python pdf_images.py <input.pdf> [--no-ocr]")
        print("      提取 PDF 中所有嵌入图片，并用视觉模型分析")
        return 1

    pdf_path = sys.argv[1]
    no_ocr = "--no-ocr" in sys.argv

    if not os.path.isfile(pdf_path):
        print(f"文件不存在: {pdf_path}")
        return 1

    # 创建输出目录
    pdf_name = Path(pdf_path).stem
    output_dir = Path(pdf_path).parent / f"{pdf_name}_images"
    output_dir.mkdir(exist_ok=True)

    # 提取图片
    print(f"📄 打开 PDF: {pdf_path}")
    images = extract_images(pdf_path, output_dir)

    if not images:
        print("  未找到嵌入图片（可能是纯文字 PDF）")
        # 也检查整个页面是否为扫描件
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        doc.close()
        print(f"  提示: PDF 共 {total_pages} 页，如需 OCR 扫描页，请使用 pymupdf 转图片功能")
        return 0

    print(f"🖼️ 提取到 {len(images)} 张图片 → {output_dir}/")
    for img in images:
        print(f"  p{img['page']}_img{img['index']}: {img['size_kb']} KB ({img['ext']})")

    if no_ocr:
        print("\n--no-ocr 模式，跳过视觉分析")
        return 0

    # 逐个分析
    print(f"\n🔍 开始视觉分析 ({MODEL})...")
    report_lines = [f"# PDF 图片分析报告", f"", f"来源: {pdf_path}", f"图片数: {len(images)}", f""]

    for i, img in enumerate(images):
        print(f"  [{i + 1}/{len(images)}] p{img['page']}_img{img['index']} ({img['size_kb']} KB)...", end=" ")
        desc = call_vision(img["path"])
        print(f"{len(desc)} chars" if desc else "FAIL")

        report_lines.append(f"## 第 {img['page']} 页 · 图片 {img['index']} ({img['filename']})")
        report_lines.append(f"")
        report_lines.append(desc or "[分析失败]")
        report_lines.append(f"")

    # 保存报告
    report_path = output_dir / "README.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    print(f"\n✅ 报告已保存: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
