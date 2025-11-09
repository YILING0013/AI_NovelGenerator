# -*- coding: utf-8 -*-
"""
实时性能监控系统
"""
import time
import psutil
import threading
from collections import deque
from typing import Dict, List, Any
from dataclasses import dataclass
import json

@dataclass
class PerformanceMetric:
    """性能指标数据类"""
    timestamp: float
    cpu_percent: float
    memory_percent: float
    memory_mb: float
    api_calls_count: int
    avg_response_time: float
    user_actions_count: int

class PerformanceMonitor:
    """性能监控器"""

    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self.metrics = deque(maxlen=max_history)
        self.api_calls = 0
        self.user_actions = 0
        self.response_times = deque(maxlen=100)
        self.monitoring = False
        self.monitor_thread = None

    def start_monitoring(self):
        """开始监控"""
        if self.monitoring:
            return

        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()

    def stop_monitoring(self):
        """停止监控"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join()

    def _monitor_loop(self):
        """监控循环"""
        while self.monitoring:
            try:
                # 收集系统指标
                cpu_percent = psutil.cpu_percent()
                memory_info = psutil.virtual_memory()
                process = psutil.Process()
                process_memory = process.memory_info()

                # 计算平均响应时间
                avg_response_time = sum(self.response_times) / len(self.response_times) if self.response_times else 0

                metric = PerformanceMetric(
                    timestamp=time.time(),
                    cpu_percent=cpu_percent,
                    memory_percent=memory_info.percent,
                    memory_mb=process_memory.rss / 1024 / 1024,
                    api_calls_count=self.api_calls,
                    avg_response_time=avg_response_time,
                    user_actions_count=self.user_actions
                )

                self.metrics.append(metric)
                time.sleep(1)  # 每秒收集一次

            except Exception as e:
                print(f"监控错误：{e}")
                time.sleep(5)

    def record_api_call(self, response_time: float):
        """记录API调用"""
        self.api_calls += 1
        self.response_times.append(response_time)

    def record_user_action(self):
        """记录用户操作"""
        self.user_actions += 1

    def get_current_metrics(self) -> Dict[str, Any]:
        """获取当前指标"""
        if not self.metrics:
            return {}

        latest = self.metrics[-1]
        return {
            "cpu_percent": latest.cpu_percent,
            "memory_percent": latest.memory_percent,
            "memory_mb": latest.memory_mb,
            "api_calls": latest.api_calls_count,
            "avg_response_time": latest.avg_response_time,
            "user_actions": latest.user_actions_count,
            "timestamp": latest.timestamp
        }

    def get_metrics_summary(self, minutes: int = 5) -> Dict[str, Any]:
        """获取指标摘要"""
        cutoff_time = time.time() - minutes * 60
        recent_metrics = [m for m in self.metrics if m.timestamp >= cutoff_time]

        if not recent_metrics:
            return {}

        cpu_values = [m.cpu_percent for m in recent_metrics]
        memory_values = [m.memory_percent for m in recent_metrics]

        return {
            "time_range_minutes": minutes,
            "avg_cpu_percent": sum(cpu_values) / len(cpu_values),
            "max_cpu_percent": max(cpu_values),
            "avg_memory_percent": sum(memory_values) / len(memory_values),
            "max_memory_percent": max(memory_values),
            "api_calls_total": recent_metrics[-1].api_calls_count - recent_metrics[0].api_calls_count,
            "user_actions_total": recent_metrics[-1].user_actions_count - recent_metrics[0].user_actions_count,
            "data_points": len(recent_metrics)
        }

    def export_metrics(self, filename: str):
        """导出指标数据"""
        data = [m.__dict__ for m in self.metrics]
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

# 全局性能监控实例
performance_monitor = PerformanceMonitor()
