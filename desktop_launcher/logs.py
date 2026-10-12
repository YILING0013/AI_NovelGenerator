"""启动器的日志预览过滤；原始输出仍由启动器单独写入文件。"""

import re

MAX_LINE_CHARS = 2048
_DATA_URI = re.compile(r"data:[^\s<>\"']{0,160}?;base64,[A-Za-z0-9+/=_-]*", re.IGNORECASE)
_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07]*(?:\x07|\x1b\\)")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


class LogPreviewFilter:
    """按流保留短行，遇到超长行立即截断，不等待整行进入内存。"""

    def __init__(self) -> None:
        self._line = ""
        self._discarding = False

    def feed(self, text: str, *, final: bool = False) -> str:
        """过滤连续的输出块，兼容跨块的 Base64 地址和超长行。

        Args:
            text: 当前流新收到的文本。
            final: 流结束时输出尚未换行的短行。

        Returns:
            可以显示的纯文本；Base64 和超长内容以中文提示代替。
        """
        output: list[str] = []
        # 每次只扫描小块，超长且没有换行的响应也不会积存在 _line 中。
        for offset in range(0, len(text), 4096):
            parts = text[offset:offset + 4096].split("\n")
            for index, part in enumerate(parts):
                ended = index < len(parts) - 1
                if not self._discarding:
                    remaining = MAX_LINE_CHARS - len(self._line)
                    self._line += part[:remaining + 1]
                    truncated = len(self._line) > MAX_LINE_CHARS
                    if ended or truncated:
                        preview = _ANSI.sub("", self._line[:MAX_LINE_CHARS])
                        preview = _CONTROL.sub("", preview)
                        preview = _DATA_URI.sub("[Base64 已省略]", preview)
                        output.append(preview)
                        if truncated:
                            output.append(" … [超长行已截断，原文见日志文件]")
                        output.append("\n")
                        self._line = ""
                        self._discarding = truncated
                if ended:
                    self._discarding = False
        if final:
            if self._line:
                preview = _CONTROL.sub("", _ANSI.sub("", self._line))
                output.append(_DATA_URI.sub("[Base64 已省略]", preview))
            self._line = ""
            self._discarding = False
        return "".join(output)
