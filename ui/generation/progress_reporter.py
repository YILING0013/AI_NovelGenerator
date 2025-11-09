"""
Progress Reporter
进度报告器类

负责处理进度报告、状态管理和统计信息。
为用户提供清晰的进度反馈和详细的状态信息。

主要功能:
- 进度跟踪和更新
- 状态变化监控
- 统计信息收集
- 报告生成
- 历史记录管理
"""

import logging
import time
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class GenerationStatus(Enum):
    """生成状态"""
    IDLE = "idle"
    PREPARING = "preparing"
    GENERATING = "generating"
    OPTIMIZING = "optimizing"
    VALIDATING = "validating"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ProgressEvent:
    """进度事件"""
    timestamp: datetime
    chapter_id: int
    status: GenerationStatus
    progress_percentage: float
    message: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'timestamp': self.timestamp.isoformat(),
            'chapter_id': self.chapter_id,
            'status': self.status.value,
            'progress_percentage': self.progress_percentage,
            'message': self.message,
            'details': self.details
        }


@dataclass
class GenerationSession:
    """生成会话"""
    session_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    total_chapters: int = 0
    completed_chapters: int = 0
    failed_chapters: int = 0
    current_chapter: int = 0
    status: GenerationStatus = GenerationStatus.IDLE
    events: List[ProgressEvent] = field(default_factory=list)
    total_words_generated: int = 0
    average_generation_time: float = 0.0

    @property
    def duration(self) -> float:
        """会话持续时间（秒）"""
        end = self.end_time or datetime.now()
        return (end - self.start_time).total_seconds()

    @property
    def success_rate(self) -> float:
        """成功率"""
        total_attempted = self.completed_chapters + self.failed_chapters
        if total_attempted == 0:
            return 0.0
        return (self.completed_chapters / total_attempted) * 100

    @property
    def overall_progress(self) -> float:
        """总体进度百分比"""
        if self.total_chapters == 0:
            return 0.0
        return (self.completed_chapters / self.total_chapters) * 100


class ProgressReporter:
    """进度报告器类"""

    def __init__(self, max_history: int = 100):
        """
        初始化进度报告器

        Args:
            max_history: 最大历史记录数
        """
        self.max_history = max_history
        self.current_session: Optional[GenerationSession] = None
        self.session_history: List[GenerationSession] = []

        # 进度回调函数
        self.progress_callbacks: List[Callable[[ProgressEvent], None]] = []

        # 状态变化回调函数
        self.status_callbacks: List[Callable[[GenerationStatus], None]] = []

        # 全局统计
        self.global_stats = {
            'total_sessions': 0,
            'total_chapters_generated': 0,
            'total_words_generated': 0,
            'total_generation_time': 0.0,
            'average_session_duration': 0.0,
            'overall_success_rate': 0.0
        }

        logger.info("ProgressReporter 初始化完成")

    def start_new_session(
        self,
        total_chapters: int,
        session_id: Optional[str] = None
    ) -> str:
        """
        开始新的生成会话

        Args:
            total_chapters: 总章节数
            session_id: 会话ID（可选）

        Returns:
            str: 会话ID
        """
        if session_id is None:
            session_id = f"session_{int(time.time())}"

        # 结束当前会话
        if self.current_session and self.current_session.status not in [GenerationStatus.COMPLETED, GenerationStatus.FAILED, GenerationStatus.CANCELLED]:
            self.end_session(GenerationStatus.CANCELLED, "开始新会话")

        # 创建新会话
        self.current_session = GenerationSession(
            session_id=session_id,
            start_time=datetime.now(),
            total_chapters=total_chapters,
            status=GenerationStatus.PREPARING
        )

        # 添加会话开始事件
        self._add_event(
            chapter_id=0,
            status=GenerationStatus.PREPARING,
            progress_percentage=0.0,
            message=f"开始新的生成会话，目标{total_chapters}章"
        )

        logger.info(f"开始新会话: {session_id}, 目标{total_chapters}章")
        return session_id

    def update_progress(
        self,
        chapter_id: int,
        progress_percentage: float,
        message: str,
        status: Optional[GenerationStatus] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        更新进度

        Args:
            chapter_id: 章节ID
            progress_percentage: 进度百分比（0-100）
            message: 进度消息
            status: 当前状态（可选）
            details: 详细信息（可选）
        """
        if not self.current_session:
            logger.warning("没有活跃的会话，无法更新进度")
            return

        # 确保进度在合理范围内
        progress_percentage = max(0.0, min(100.0, progress_percentage))

        # 更新当前章节
        self.current_session.current_chapter = chapter_id

        # 更新状态
        if status and status != self.current_session.status:
            old_status = self.current_session.status
            self.current_session.status = status

            # 触发状态变化回调
            self._notify_status_change(status)

            logger.info(f"状态变化: {old_status.value} -> {status.value}")

        # 添加进度事件
        self._add_event(
            chapter_id=chapter_id,
            status=status or self.current_session.status,
            progress_percentage=progress_percentage,
            message=message,
            details=details or {}
        )

        # 触发进度回调
        if self.progress_callbacks:
            event = self.current_session.events[-1]
            for callback in self.progress_callbacks:
                try:
                    callback(event)
                except Exception as e:
                    logger.error(f"进度回调执行失败: {e}")

    def mark_chapter_completed(
        self,
        chapter_id: int,
        word_count: int,
        generation_time: float,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        标记章节完成

        Args:
            chapter_id: 章节ID
            word_count: 生成的字数
            generation_time: 生成时间
            details: 详细信息（可选）
        """
        if not self.current_session:
            logger.warning("没有活跃的会话，无法标记章节完成")
            return

        self.current_session.completed_chapters += 1
        self.current_session.total_words_generated += word_count

        # 更新平均生成时间
        if self.current_session.completed_chapters > 0:
            total_time = (self.current_session.average_generation_time * (self.current_session.completed_chapters - 1) + generation_time)
            self.current_session.average_generation_time = total_time / self.current_session.completed_chapters

        # 添加完成事件
        self._add_event(
            chapter_id=chapter_id,
            status=GenerationStatus.COMPLETED,
            progress_percentage=self.current_session.overall_progress,
            message=f"第{chapter_id}章完成，字数: {word_count}，耗时: {generation_time:.2f}秒",
            details={
                'word_count': word_count,
                'generation_time': generation_time,
                **(details or {})
            }
        )

        logger.info(f"第{chapter_id}章完成，字数: {word_count}")

    def mark_chapter_failed(
        self,
        chapter_id: int,
        error_message: str,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        标记章节失败

        Args:
            chapter_id: 章节ID
            error_message: 错误信息
            details: 详细信息（可选）
        """
        if not self.current_session:
            logger.warning("没有活跃的会话，无法标记章节失败")
            return

        self.current_session.failed_chapters += 1

        # 添加失败事件
        self._add_event(
            chapter_id=chapter_id,
            status=GenerationStatus.FAILED,
            progress_percentage=self.current_session.overall_progress,
            message=f"第{chapter_id}章失败: {error_message}",
            details={
                'error_message': error_message,
                **(details or {})
            }
        )

        logger.warning(f"第{chapter_id}章失败: {error_message}")

    def end_session(
        self,
        final_status: GenerationStatus,
        message: str = ""
    ) -> None:
        """
        结束当前会话

        Args:
            final_status: 最终状态
            message: 结束消息
        """
        if not self.current_session:
            logger.warning("没有活跃的会话可以结束")
            return

        # 更新会话状态
        self.current_session.status = final_status
        self.current_session.end_time = datetime.now()

        # 添加结束事件
        self._add_event(
            chapter_id=self.current_session.current_chapter,
            status=final_status,
            progress_percentage=100.0 if final_status == GenerationStatus.COMPLETED else self.current_session.overall_progress,
            message=f"会话结束: {message}"
        )

        # 更新全局统计
        self._update_global_stats()

        # 添加到历史记录
        self.session_history.append(self.current_session)

        # 限制历史记录数量
        if len(self.session_history) > self.max_history:
            self.session_history = self.session_history[-self.max_history:]

        logger.info(f"会话结束: {self.current_session.session_id}, 状态: {final_status.value}")

        # 清除当前会话
        self.current_session = None

    def get_current_session_info(self) -> Optional[Dict[str, Any]]:
        """获取当前会话信息"""
        if not self.current_session:
            return None

        return {
            'session_id': self.current_session.session_id,
            'start_time': self.current_session.start_time.isoformat(),
            'duration': self.current_session.duration,
            'total_chapters': self.current_session.total_chapters,
            'completed_chapters': self.current_session.completed_chapters,
            'failed_chapters': self.current_session.failed_chapters,
            'current_chapter': self.current_session.current_chapter,
            'status': self.current_session.status.value,
            'overall_progress': self.current_session.overall_progress,
            'success_rate': self.current_session.success_rate,
            'total_words_generated': self.current_session.total_words_generated,
            'average_generation_time': self.current_session.average_generation_time,
            'event_count': len(self.current_session.events)
        }

    def get_session_summary(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取指定会话的摘要"""
        # 在当前会话中查找
        if self.current_session and self.current_session.session_id == session_id:
            return self.get_current_session_info()

        # 在历史记录中查找
        for session in self.session_history:
            if session.session_id == session_id:
                return {
                    'session_id': session.session_id,
                    'start_time': session.start_time.isoformat(),
                    'end_time': session.end_time.isoformat() if session.end_time else None,
                    'duration': session.duration,
                    'total_chapters': session.total_chapters,
                    'completed_chapters': session.completed_chapters,
                    'failed_chapters': session.failed_chapters,
                    'status': session.status.value,
                    'overall_progress': session.overall_progress,
                    'success_rate': session.success_rate,
                    'total_words_generated': session.total_words_generated,
                    'average_generation_time': session.average_generation_time,
                    'event_count': len(session.events)
                }

        return None

    def get_session_events(self, session_id: str) -> List[Dict[str, Any]]:
        """获取指定会话的所有事件"""
        events = []

        # 在当前会话中查找
        if self.current_session and self.current_session.session_id == session_id:
            events.extend([event.to_dict() for event in self.current_session.events])

        # 在历史记录中查找
        for session in self.session_history:
            if session.session_id == session_id:
                events.extend([event.to_dict() for event in session.events])

        return events

    def get_recent_events(self, count: int = 50) -> List[Dict[str, Any]]:
        """获取最近的事件"""
        all_events = []

        # 添加当前会话的事件
        if self.current_session:
            all_events.extend([(self.current_session.start_time, event.to_dict()) for event in self.current_session.events])

        # 添加历史会话的事件
        for session in self.session_history[-10:]:  # 最近10个会话
            for event in session.events:
                all_events.append((event.timestamp, event.to_dict()))

        # 按时间排序
        all_events.sort(key=lambda x: x[0], reverse=True)

        # 返回指定数量的事件
        return [event for _, event in all_events[:count]]

    def get_global_stats(self) -> Dict[str, Any]:
        """获取全局统计信息"""
        self._update_global_stats()
        return self.global_stats.copy()

    def add_progress_callback(self, callback: Callable[[ProgressEvent], None]) -> None:
        """添加进度回调函数"""
        self.progress_callbacks.append(callback)
        logger.info("添加进度回调函数")

    def add_status_callback(self, callback: Callable[[GenerationStatus], None]) -> None:
        """添加状态变化回调函数"""
        self.status_callbacks.append(callback)
        logger.info("添加状态变化回调函数")

    def remove_progress_callback(self, callback: Callable[[ProgressEvent], None]) -> None:
        """移除进度回调函数"""
        if callback in self.progress_callbacks:
            self.progress_callbacks.remove(callback)
            logger.info("移除进度回调函数")

    def remove_status_callback(self, callback: Callable[[GenerationStatus], None]) -> None:
        """移除状态变化回调函数"""
        if callback in self.status_callbacks:
            self.status_callbacks.remove(callback)
            logger.info("移除状态变化回调函数")

    def clear_history(self) -> None:
        """清除历史记录"""
        self.session_history.clear()
        logger.info("历史记录已清除")

    def export_session_report(self, session_id: str, format: str = "json") -> Optional[str]:
        """
        导出会话报告

        Args:
            session_id: 会话ID
            format: 导出格式 ("json" 或 "text")

        Returns:
            Optional[str]: 报告内容
        """
        summary = self.get_session_summary(session_id)
        events = self.get_session_events(session_id)

        if not summary and not events:
            return None

        if format == "json":
            import json
            report = {
                'summary': summary,
                'events': events
            }
            return json.dumps(report, indent=2, ensure_ascii=False)

        elif format == "text":
            lines = []
            if summary:
                lines.append(f"会话报告: {session_id}")
                lines.append("=" * 50)
                lines.append(f"开始时间: {summary.get('start_time', 'N/A')}")
                lines.append(f"结束时间: {summary.get('end_time', 'N/A')}")
                lines.append(f"持续时间: {summary.get('duration', 0):.2f} 秒")
                lines.append(f"总章节数: {summary.get('total_chapters', 0)}")
                lines.append(f"完成章节: {summary.get('completed_chapters', 0)}")
                lines.append(f"失败章节: {summary.get('failed_chapters', 0)}")
                lines.append(f"成功率: {summary.get('success_rate', 0):.1f}%")
                lines.append(f"总字数: {summary.get('total_words_generated', 0)}")
                lines.append(f"平均生成时间: {summary.get('average_generation_time', 0):.2f} 秒")
                lines.append("")

            if events:
                lines.append("事件记录:")
                lines.append("-" * 50)
                for event in events:
                    lines.append(f"[{event['timestamp']}] 章节{event['chapter_id']} - {event['status']}: {event['message']}")

            return "\n".join(lines)

        else:
            raise ValueError(f"不支持的导出格式: {format}")

    def _add_event(
        self,
        chapter_id: int,
        status: GenerationStatus,
        progress_percentage: float,
        message: str,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """添加进度事件"""
        if not self.current_session:
            return

        event = ProgressEvent(
            timestamp=datetime.now(),
            chapter_id=chapter_id,
            status=status,
            progress_percentage=progress_percentage,
            message=message,
            details=details or {}
        )

        self.current_session.events.append(event)

    def _notify_status_change(self, new_status: GenerationStatus) -> None:
        """通知状态变化"""
        for callback in self.status_callbacks:
            try:
                callback(new_status)
            except Exception as e:
                logger.error(f"状态变化回调执行失败: {e}")

    def _update_global_stats(self) -> None:
        """更新全局统计"""
        all_sessions = list(self.session_history)
        if self.current_session:
            all_sessions.append(self.current_session)

        if not all_sessions:
            return

        # 基础统计
        self.global_stats['total_sessions'] = len(all_sessions)
        self.global_stats['total_chapters_generated'] = sum(s.completed_chapters for s in all_sessions)
        self.global_stats['total_words_generated'] = sum(s.total_words_generated for s in all_sessions)
        self.global_stats['total_generation_time'] = sum(s.duration for s in all_sessions if s.end_time)

        # 平均会话持续时间
        completed_sessions = [s for s in all_sessions if s.end_time]
        if completed_sessions:
            self.global_stats['average_session_duration'] = sum(s.duration for s in completed_sessions) / len(completed_sessions)

        # 总体成功率
        total_attempted = sum(s.completed_chapters + s.failed_chapters for s in all_sessions)
        if total_attempted > 0:
            self.global_stats['overall_success_rate'] = (self.global_stats['total_chapters_generated'] / total_attempted) * 100

    def reset_stats(self) -> None:
        """重置统计信息"""
        self.global_stats = {
            'total_sessions': 0,
            'total_chapters_generated': 0,
            'total_words_generated': 0,
            'total_generation_time': 0.0,
            'average_session_duration': 0.0,
            'overall_success_rate': 0.0
        }
        logger.info("全局统计已重置")