from __future__ import annotations

from typing import Any


def classify_build_failure(errors: list[str], log: str = "") -> dict[str, Any]:
    corpus = " ".join([*errors, log]).lower()
    category = "unknown_build_failure"
    suggested_rules = ["检查 build.log 与 build_errors.json 后重试"]
    retryable = False

    if "use of unresolved identifier" in corpus or "cannot find" in corpus:
        category = "missing_symbol"
        suggested_rules = [
            "补齐缺失符号定义，检查拼写与可见性",
            "确认 Sources 文件已加入 target",
        ]
    elif "expected" in corpus and ("swift" in corpus or "error:" in corpus):
        category = "swift_syntax"
        suggested_rules = [
            "优先修复语法错误（括号、泛型、闭包签名）",
            "按编译器第一条错误逐个修复，避免连锁误报",
        ]
    elif "code signing" in corpus or "provisioning profile" in corpus:
        category = "signing_config"
        suggested_rules = [
            "校验签名证书与 provisioning profile",
            "本地 Demo 模式可先跳过签名验证",
        ]
    elif "simulator" in corpus and ("not found" in corpus or "unable to boot" in corpus):
        category = "simulator_unavailable"
        suggested_rules = [
            "确认模拟器名称与版本可用",
            "执行 xcrun simctl list 检查目标设备",
        ]
        retryable = True
    elif "timed out" in corpus or "timeout" in corpus:
        category = "build_timeout"
        suggested_rules = [
            "提高构建超时并检查机器负载",
            "分批构建以降低单次编译压力",
        ]
        retryable = True

    return {
        "category": category,
        "retryable": retryable,
        "suggested_rules": suggested_rules,
    }


def classify_runtime_exception(exc: Exception) -> dict[str, Any]:
    message = str(exc).lower()
    category = "runtime_exception"
    retryable = False

    if any(token in message for token in ("timeout", "tempor", "connection reset", "database is locked")):
        category = "transient_infra"
        retryable = True
    elif "not found" in message:
        category = "resource_missing"

    return {"category": category, "retryable": retryable}
