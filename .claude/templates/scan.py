#!/usr/bin/env python3
"""
模板库管理器 - 扫描原始模板，提取格式，建立索引。
用法: python scan.py
"""
import json
import subprocess
import sys
import io
from pathlib import Path
from datetime import datetime

# Fix Windows GBK encoding issue
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

TEMPLATE_DIR = Path(__file__).parent
ORIGINALS = TEMPLATE_DIR / "originals"
FORMATS = TEMPLATE_DIR / "formats"
INDEX = TEMPLATE_DIR / "index.json"
EXTRACTOR = Path("d:/项目/.claude/skills/docx-format-replicator/scripts/extract_format.py").resolve()

def scan():
    if not ORIGINALS.exists():
        print("❌ originals/ 目录不存在")
        return

    docx_files = list(ORIGINALS.glob("*.docx"))
    if not docx_files:
        print("📭 originals/ 中没有 .docx 模板文件")
        print(f"   请把模板文件放入: {ORIGINALS}")
        return

    # Load existing index
    index = {}
    if INDEX.exists():
        with open(INDEX, 'r', encoding='utf-8') as f:
            index = json.load(f)

    new_count = 0
    update_count = 0

    for docx_path in docx_files:
        name = docx_path.stem  # filename without extension
        json_path = FORMATS / f"{name}.json"
        mtime = docx_path.stat().st_mtime

        # Check if needs update
        if name in index and index[name].get('mtime') == mtime:
            continue

        # Extract format
        print(f"📄 提取格式: {docx_path.name}")
        result = subprocess.run(
            [sys.executable, str(EXTRACTOR), str(docx_path), str(json_path)],
            capture_output=True, text=True
        )

        if result.returncode != 0:
            print(f"   ⚠️ 失败: {result.stderr}")
            continue

        # Update index
        if name in index:
            update_count += 1
        else:
            new_count += 1

        index[name] = {
            "name": name,
            "original": str(docx_path.name),
            "format_json": str(json_path.name),
            "mtime": mtime,
            "extracted_at": datetime.now().isoformat(),
            "size_kb": round(docx_path.stat().st_size / 1024, 1)
        }

    # Save index
    with open(INDEX, 'w', encoding='utf-8') as f:
        json.dump(index, f, indent=2, ensure_ascii=False)

    # Summary
    print(f"\n✅ 完成: {new_count} 个新增, {update_count} 个更新")
    print(f"   模板库共有 {len(index)} 个模板:")
    for name, info in index.items():
        print(f"   • {name} ({info['size_kb']} KB)")

def list_templates():
    """列出所有可用模板"""
    if not INDEX.exists():
        print("[EMPTY] 模板库为空，还没有提取过模板")
        return []

    with open(INDEX, 'r', encoding='utf-8') as f:
        index = json.load(f)

    print(f"📚 模板库 ({len(index)} 个模板):")
    for name, info in index.items():
        print(f"   • {name} — {info['size_kb']} KB — 提取于 {info.get('extracted_at', '?')[:10]}")
    return list(index.keys())

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "list":
        list_templates()
    else:
        scan()
