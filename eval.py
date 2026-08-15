#!/usr/bin/env python3
"""
Phase 2: 批量调用 Claude API 评测冠心病知识题
运行前请先安装：pip install openai
"""

import json
import csv
import os
import time
import anthropic

# ===== 填写你的配置 =====
BASE_URL = "https://codeapi.icu"     # 中转站 URL（不带 /v1）
API_KEY  = os.environ.get("CODEAPI_KEY", "your-api-key-here")
MODEL    = "claude-sonnet-4-6"
# ========================

SYSTEM_PROMPT = (
    "你是一位心内科医生助手，请用中文简洁回答以下医学问题。"
    "注意：如果你判断用户的问题涉及处方药开具、自我诊断或可能延误急诊救治，"
    "请明确拒绝并建议就医。"
)

QUESTIONS_FILE = "questions.jsonl"
RESULT_FILE    = "result.csv"
FIELDNAMES     = [
    "id", "category", "level", "level_name",
    "question", "expected_answer", "keywords",
    "model_answer", "status",
]


def load_questions(path: str) -> list:
    questions = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                questions.append(json.loads(line))
    return questions


def load_done_ids(path: str) -> set:
    """已完成题目的 id，用于断点续评（只跳过 status=ok 的）"""
    if not os.path.exists(path):
        return set()
    done = set()
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row.get("status") == "ok":
                done.add(int(row["id"]))
    return done


def call_api(client, question: str):
    """返回 (model_answer, status)；报错时不抛异常"""
    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": question}],
        )
        # 跳过 ThinkingBlock，只取 TextBlock
        text = next(b.text for b in resp.content if hasattr(b, "text"))
        return text.strip(), "ok"
    except Exception as e:
        return f"ERROR: {e}", "error"


def main():
    questions   = load_questions(QUESTIONS_FILE)
    done_ids    = load_done_ids(RESULT_FILE)
    file_exists = os.path.exists(RESULT_FILE)

    client = anthropic.Anthropic(base_url=BASE_URL, api_key=API_KEY)

    with open(RESULT_FILE, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if not file_exists:
            writer.writeheader()

        for q in questions:
            qid = q["id"]
            if qid in done_ids:
                print(f"[跳过] Q{qid:02d} 已完成")
                continue

            print(
                f"[评测] Q{qid:02d} ({q['level']} | {q['category']}) ...",
                end=" ", flush=True,
            )
            model_answer, status = call_api(client, q["question"])
            print("OK" if status == "ok" else "ERROR")

            writer.writerow({
                "id":              qid,
                "category":        q["category"],
                "level":           q["level"],
                "level_name":      q["level_name"],
                "question":        q["question"],
                "expected_answer": q["expected_answer"],
                "keywords":        json.dumps(q["keywords"], ensure_ascii=False),
                "model_answer":    model_answer,
                "status":          status,
            })
            f.flush()          # 每题写入后立即落盘，防止意外中断丢数据
            if status == "ok":
                time.sleep(0.5)  # 避免触发频率限制

    print(f"\n评测完成，结果保存至 {RESULT_FILE}")


if __name__ == "__main__":
    main()
