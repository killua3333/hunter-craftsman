"""同机 Agent A 调用示例：分析 → 实现 → 轮询反馈。"""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8791"
REQ_PATH = Path(__file__).parent / "requirement.sample.json"


def main() -> None:
    req = json.loads(REQ_PATH.read_text(encoding="utf-8"))
    oid = req["opportunity_id"]

    with httpx.Client(base_url=BASE, timeout=120.0) as client:
        fb = client.post(f"/v1/opportunities/{oid}/analyze", json=req).json()
        print("analyze:", json.dumps(fb, ensure_ascii=False, indent=2))
        if not fb["blueprint"]["accepted"]:
            return

        run = client.post(
            f"/v1/opportunities/{oid}/implement",
            json={"opportunity_id": oid, "requirement": req},
        ).json()
        run_id = run["run_id"]
        print("run_id:", run_id)

        while True:
            row = client.get(f"/v1/runs/{run_id}").json()
            status = row["status"]
            print("status:", status)
            if status in ("failed", "submitted", "ready_for_release", "platform_unavailable", "cancelled"):
                if row.get("feedback"):
                    print("feedback:", json.dumps(row["feedback"], ensure_ascii=False, indent=2))
                break
            time.sleep(3)


if __name__ == "__main__":
    main()
