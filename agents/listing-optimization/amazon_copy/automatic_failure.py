"""Seller-safe messages for automatic optimization failures."""


def optimization_failure_message(error: BaseException) -> str:
    """Map expected provider failures to seller-safe Chinese guidance."""
    return {
        TimeoutError: "模型服务在60秒内未完成响应, 请重试。",
    }.get(type(error), "模型返回格式无效或服务调用失败, 请重试; 若重复出现请检查模型服务。")


__all__ = ["optimization_failure_message"]
