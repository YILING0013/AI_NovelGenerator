"""让并发归档命令在整个异步连接周期内拒绝驱动警告。"""

from contextlib import contextmanager
import sys
from threading import RLock
import warnings


_lock = RLock()
_active = 0
_scope = None


@contextmanager
def driver_warning_guard():
    """将驱动警告转为异常，最后一个并发操作退出后恢复原策略。

    Args:
        无。
    Yields:
        无；调用者负责将异常转换为不含 URI 或 DNS 选项的固定说明。
    """
    global _active, _scope
    if getattr(sys.flags, "context_aware_warnings", False):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            yield
        return
    # Python 默认策略是进程全局；异步任务交错退出不能提前恢复另一任务的过滤器。
    with _lock:
        if _active == 0:
            _scope = warnings.catch_warnings()
            _scope.__enter__()
            warnings.simplefilter("error")
        _active += 1
    try:
        yield
    finally:
        with _lock:
            _active -= 1
            if _active == 0:
                _scope.__exit__(None, None, None)
                _scope = None
