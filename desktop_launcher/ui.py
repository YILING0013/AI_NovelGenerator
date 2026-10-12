"""启动器共用的雾蓝 / 墨夜配色与线性图标按钮。"""

from functools import lru_cache

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QToolButton

# 与 frontend/src/lib/themes.ts 的 Mist 基准一致，控件只使用颜色的用途名称。
THEMES = {
    "light": {
        "background": "#f1f3f5", "surface": "#fafaf9", "secondary": "#e9edf1",
        "raised": "#fdfdfc", "selected": "#e2eaf2", "text": "#303844",
        "muted": "#5b6877", "accent": "#456783", "on_accent": "#f8fafc",
        "accent_hover": "#3a5973", "border": "#d6dce3", "disabled": "#929ba6",
        "error": "#ad3546", "warning": "#8a601d", "success": "#267052",
    },
    "dark": {
        "background": "#171b22", "surface": "#20252e", "secondary": "#272e38",
        "raised": "#2a303b", "selected": "#2c3b4d", "text": "#d9dfe7",
        "muted": "#a4b0bf", "accent": "#aac3df", "on_accent": "#1c2a39",
        "accent_hover": "#bed1e8", "border": "#3b4655", "disabled": "#707e90",
        "error": "#ee929d", "warning": "#d8b879", "success": "#83c6a6",
    },
}

# 沿用网页端 24px 画布、圆端点线条；太阳、月亮与 Navbar 使用相同路径。
_ICONS = {
    "system": '<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8m-4-4v4"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M4.93 4.93l1.41 1.41m11.32 11.32 1.41 1.41M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>',
    "moon": '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
    "play": '<path d="m8 5 11 7-11 7Z"/>',
    "stop": '<rect x="4" y="4" width="16" height="16" rx="1"/>',
    "pause": '<path d="M8 5v14M16 5v14"/>',
    "follow": '<path d="M12 3v12m-5-5 5 5 5-5M5 20h14"/>',
    "next": '<path d="M12 4v16m-6-6 6 6 6-6"/>',
    "clear": '<path d="m15 3 6 6-11 11H6l-4-4L15 3ZM8 9l7 7M10 20h11"/>',
    "file": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Zm0 0v6h6M8 12h8m-8 4h8"/>',
    "folder": '<path d="M3 7V5a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v1M3 7h5l2 3h11l-3 10H3Z"/>',
    "external": '<path d="M14 3h7v7m0-7L10 14M10 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-5"/>',
    "save": '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h12l4 4v12a2 2 0 0 1-2 2ZM7 3v6h9V3M7 21v-8h10v8"/>',
    "bug": '<rect x="7" y="7" width="10" height="14" rx="5"/><path d="M9 7V5a3 3 0 0 1 6 0v2M12 12v9M3 9l4 2M3 15h4m-4 6 4-3M21 9l-4 2m4 4h-4m4 6-4-3"/>',
}


@lru_cache(maxsize=128)
def line_icon(name: str, normal: str, selected: str, disabled: str) -> QIcon:
    """生成明暗主题下都清楚的图标，并缓存相同图标。

    Args:
        name: 图标名称。
        normal: 普通状态的线条颜色。
        selected: 选中状态的线条颜色。
        disabled: 禁用状态的线条颜色。

    Returns:
        带普通、选中和禁用状态的 Qt 图标。
    """
    icon = QIcon()
    for color, mode, state in (
        (normal, QIcon.Mode.Normal, QIcon.State.Off),
        (selected, QIcon.Mode.Normal, QIcon.State.On),
        (disabled, QIcon.Mode.Disabled, QIcon.State.Off),
        (disabled, QIcon.Mode.Disabled, QIcon.State.On),
    ):
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{_ICONS[name]}</svg>'
        pixmap = QPixmap(48, 48)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        QSvgRenderer(svg.encode()).render(painter)
        painter.end()
        pixmap.setDevicePixelRatio(2)
        icon.addPixmap(pixmap, mode, state)
    return icon


class IconButton(QToolButton):
    """复用于服务、日志和主题工具栏的图标按钮。"""

    def __init__(self, symbol: str, label: str, *, show_text: bool = False, primary: bool = False):
        super().__init__()
        self.symbol = symbol
        self.colors = THEMES["light"]
        self.primary = primary
        self.setProperty("iconOnly", not show_text)
        self.setAutoRaise(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setIconSize(QSize(18, 18))
        self.setFixedHeight(36)
        if show_text:
            self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        else:
            self.setFixedWidth(36)
        if primary:
            self.setObjectName("primary")
        self.set_action(symbol, label)

    def set_action(self, symbol: str, label: str) -> None:
        """同步按钮图标、提示与可访问名称。

        Args:
            symbol: 操作图标。
            label: 操作名称。

        Returns:
            无。
        """
        self.symbol = symbol
        self.setText(label)
        self.setToolTip(label)
        self.setAccessibleName(label)
        self.set_theme(self.colors)

    def set_theme(self, colors: dict[str, str]) -> None:
        """更新图标各状态的颜色。

        Args:
            colors: 当前主题的语义颜色。

        Returns:
            无。
        """
        self.colors = colors
        normal = colors["on_accent"] if self.primary else colors["muted"]
        self.setIcon(line_icon(self.symbol, normal, colors["accent"], colors["disabled"]))
