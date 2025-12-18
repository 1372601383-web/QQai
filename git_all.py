# -*- coding: utf-8 -*-
import os
import sys
import shutil
import subprocess
import re
import openpyxl
from datetime import datetime
from urllib.parse import quote
from PyQt6 import QtCore, QtWidgets, QtGui


# ---------------- 环境与配置路径 ----------------
def get_resource_path():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


CONFIG_FILE = os.path.join(get_resource_path(), "config.txt")

# ---------------- 完整皮肤方案 ----------------
THEMES = {
    "经典深绿 (Classic Green)": {
        "main_bg": "#121212", "card_bg": "#1e1e1e", "text": "#ffffff", "sub_text": "#a0a0a0",
        "accent": "#2e8b57",
        "drag_gradient": "qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1, stop:0 #162b2b, stop:1 #1f2f2f)",
        "log_bg": "#0f1010", "btn_hover": "#3e9b67", "input_bg": "#252525"
    },
    "赛博朋克 (Cyber Pink)": {
        "main_bg": "#0d0221", "card_bg": "#0f082d", "text": "#00f5ff", "sub_text": "#ff007f",
        "accent": "#ff007f",
        "drag_gradient": "qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1, stop:0 #2d0b3a, stop:1 #0d0221)",
        "log_bg": "#050110", "btn_hover": "#ff4da6", "input_bg": "#1a0b35"
    },
    "极简浅色 (Light Mode)": {
        "main_bg": "#f5f5f5", "card_bg": "#ffffff", "text": "#333333", "sub_text": "#666666",
        "accent": "#0078d7",
        "drag_gradient": "qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1, stop:0 #e1e1e1, stop:1 #f5f5f5)",
        "log_bg": "#ffffff", "btn_hover": "#2b88d9", "input_bg": "#e8e8e8"
    },
    "深邃星空 (Space Blue)": {
        "main_bg": "#0b0e14", "card_bg": "#151921", "text": "#ffffff", "sub_text": "#7a869a",
        "accent": "#4a90e2",
        "drag_gradient": "qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1, stop:0 #1a2332, stop:1 #0b0e14)",
        "log_bg": "#080a0f", "btn_hover": "#64a4ed", "input_bg": "#1c222d"
    },
    "魅惑紫罗兰 (Violet)": {
        "main_bg": "#1a1625", "card_bg": "#241e30", "text": "#e0d7f2", "sub_text": "#8a2be2",
        "accent": "#8a2be2",
        "drag_gradient": "qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1, stop:0 #2e1a47, stop:1 #1a1625)",
        "log_bg": "#120f1a", "btn_hover": "#a052ee", "input_bg": "#282236"
    }
}


# ---------------- 上传逻辑 ----------------
class WorkerSignals(QtCore.QObject):
    log = QtCore.pyqtSignal(str)
    progress = QtCore.pyqtSignal(int, int)
    finished = QtCore.pyqtSignal(bool, str)


class UploadWorker(QtCore.QRunnable):
    def __init__(self, folder_list, repo_path, username, repo, branch):
        super().__init__()
        self.folder_list = folder_list
        self.repo_root = repo_path
        self.username = username
        self.repo = repo
        self.branch = branch
        self.signals = WorkerSignals()

    def run(self):
        try:
            for src_folder in self.folder_list:
                f_name = os.path.basename(src_folder.rstrip(os.sep))
                self.signals.log.emit(f"正在处理: {f_name}")
                dest = os.path.join(self.repo_root, f_name)
                os.makedirs(dest, exist_ok=True)
                for f in os.listdir(src_folder):
                    if os.path.splitext(f)[1].lower() in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".bmp"}:
                        shutil.copy2(os.path.join(src_folder, f), os.path.join(dest, f))

                subprocess.run(["git", "add", "."], cwd=self.repo_root)
                subprocess.run(["git", "commit", "-m", f"Upload {f_name}"], cwd=self.repo_root)
                subprocess.run(["git", "push", "origin", self.branch], cwd=self.repo_root)

                wb = openpyxl.Workbook()
                ws = wb.active
                ws.append(["文件名", "URL"])
                for f in os.listdir(dest):
                    url = f"https://cdn.jsdelivr.net/gh/{self.username}/{self.repo}/{f_name}/{quote(f)}"
                    ws.append([f, url])
                wb.save(os.path.join(self.repo_root, f"{f_name}_urls.xlsx"))
            self.signals.finished.emit(True, "任务全部执行完毕！")
        except Exception as e:
            self.signals.finished.emit(False, str(e))


# ---------------- 主界面 ----------------
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.repo_path = get_resource_path()
        self.queue = []
        self.pool = QtCore.QThreadPool.globalInstance()
        self._old_pos = None

        self.setWindowFlags(QtCore.Qt.WindowType.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)

        self.init_ui()
        self.load_skin_config()  # 加载历史皮肤

    def init_ui(self):
        self.resize(850, 750)
        self.bg_frame = QtWidgets.QFrame(self)
        self.bg_frame.setObjectName("MainFrame")
        self.setCentralWidget(self.bg_frame)

        # 紧凑型布局
        layout = QtWidgets.QVBoxLayout(self.bg_frame)
        layout.setContentsMargins(20, 10, 20, 20)
        layout.setSpacing(10)  # 减小组件间的间距

        # --- 标题栏 ---
        title_bar = QtWidgets.QHBoxLayout()
        self.title_label = QtWidgets.QLabel("🚀 GITHUB CDN MANAGER")
        self.title_label.setStyleSheet("font-weight: bold; font-family: 'Segoe UI';")
        self.min_btn = QtWidgets.QPushButton("–")
        self.close_btn = QtWidgets.QPushButton("✕")
        for btn in [self.min_btn, self.close_btn]:
            btn.setFixedSize(36, 30)
            btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.min_btn.clicked.connect(self.showMinimized)
        self.close_btn.clicked.connect(self.close)
        title_bar.addWidget(self.title_label)
        title_bar.addStretch()
        title_bar.addWidget(self.min_btn)
        title_bar.addWidget(self.close_btn)
        layout.addLayout(title_bar)

        # --- 配置栏 ---
        config_bar = QtWidgets.QHBoxLayout()
        self.theme_combo = QtWidgets.QComboBox()
        self.theme_combo.addItems(THEMES.keys())
        self.theme_combo.currentTextChanged.connect(self.on_theme_changed)
        self.deploy_btn = QtWidgets.QPushButton("⚡ 初始化仓库")
        self.deploy_btn.clicked.connect(self.run_deploy)
        config_bar.addWidget(QtWidgets.QLabel("皮肤:"))
        config_bar.addWidget(self.theme_combo, 1)
        config_bar.addWidget(self.deploy_btn)
        layout.addLayout(config_bar)

        # 路径展示
        self.path_display = QtWidgets.QLabel()
        layout.addWidget(self.path_display)

        # 拖拽区 - 稍微调窄一点，避免占地过大
        self.drag_area = QtWidgets.QLabel("将文件夹拖入此区域 (禁中文)")
        self.drag_area.setFixedHeight(120)
        self.drag_area.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.drag_area)

        # 队列框 - 调小一点
        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setFixedHeight(80)
        layout.addWidget(self.list_widget)

        # 开始按钮 - 紧跟其后
        self.start_btn = QtWidgets.QPushButton("🔥 开始同步并生成报表")
        self.start_btn.setFixedHeight(55)
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(self.on_start)
        layout.addWidget(self.start_btn)

        # 进度与日志
        self.prog_bar = QtWidgets.QProgressBar()
        self.prog_bar.setFixedHeight(10)
        layout.addWidget(self.prog_bar)
        self.log_view = QtWidgets.QPlainTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view)

    def on_theme_changed(self, theme_name):
        self.apply_theme(theme_name)
        # 实时保存皮肤选择
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                f.write(theme_name)
        except:
            pass

    def load_skin_config(self):
        default = "经典深绿 (Classic Green)"
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    saved = f.read().strip()
                    if saved in THEMES:
                        default = saved
            except:
                pass
        self.theme_combo.setCurrentText(default)
        self.apply_theme(default)

    def apply_theme(self, theme_name):
        t = THEMES[theme_name]
        self.bg_frame.setStyleSheet(
            f"QFrame#MainFrame {{ background-color: {t['main_bg']}; border-radius: 20px; border: 2px solid {t['accent']}; }} QLabel {{ color: {t['text']}; }}")

        btn_style = "border-radius: 4px; font-weight: bold; border: none;"
        self.min_btn.setStyleSheet(
            f"QPushButton {{ background: {t['input_bg']}; color: {t['text']}; {btn_style} }} QPushButton:hover {{ background: #444; }}")
        self.close_btn.setStyleSheet(
            f"QPushButton {{ background: {t['input_bg']}; color: {t['text']}; {btn_style} }} QPushButton:hover {{ background: #e81123; color: white; }}")

        self.theme_combo.setStyleSheet(
            f"QComboBox {{ background: {t['input_bg']}; color: {t['text']}; border: 1px solid {t['accent']}; border-radius: 6px; padding: 4px; }}")

        accent_btn = f"background: {t['accent']}; color: white; border-radius: 12px; font-weight: bold;"
        self.deploy_btn.setStyleSheet(accent_btn + "padding: 5px 15px;")
        self.start_btn.setStyleSheet(
            f"QPushButton {{ {accent_btn} font-size: 16px; }} QPushButton:hover {{ background: {t['btn_hover']}; }} QPushButton:disabled {{ background: #333; color: #666; }}")

        self.drag_area.setStyleSheet(
            f"background: {t['drag_gradient']}; border: 2px dashed {t['accent']}; border-radius: 15px; color: {t['text']}; font-weight: bold;")
        self.log_view.setStyleSheet(
            f"background: {t['log_bg']}; color: {t['text']}; border-radius: 8px; border: 1px solid #333; font-family: Consolas;")
        self.list_widget.setStyleSheet(
            f"background: {t['log_bg']}; color: {t['text']}; border-radius: 8px; border: 1px solid #333;")
        self.prog_bar.setStyleSheet(
            f"QProgressBar {{ background: {t['input_bg']}; border-radius: 5px; border: none; }} QProgressBar::chunk {{ background: {t['accent']}; }}")
        self.update_path_ui()

    def update_path_ui(self):
        is_git = os.path.exists(os.path.join(self.repo_path, ".git"))
        status = "[OK]" if is_git else "[WAIT]"
        t = THEMES[self.theme_combo.currentText()]
        self.path_display.setText(
            f"PATH: <span style='color:{t['accent']}; font-family:Consolas;'>{self.repo_path}</span> <b>{status}</b>")

    def run_deploy(self):
        try:
            os.chdir(self.repo_path)
            subprocess.run(["git", "init"], cwd=self.repo_path, check=True)
            subprocess.run(["git", "remote", "add", "origin", f"https://github.com/1372601383-web/QQai.git"],
                           cwd=self.repo_path)
            self.update_path_ui()
            self.log_view.appendPlainText("部署成功！")
        except Exception as e:
            self.log_view.appendPlainText(f"错误: {e}")

    # 拖拽与窗口移动逻辑保持不变
    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton: self._old_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self._old_pos is not None:
            delta = event.globalPosition().toPoint() - self._old_pos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self._old_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self._old_pos = None

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.acceptProposedAction()

    def dropEvent(self, e):
        for url in e.mimeData().urls():
            p = url.toLocalFile()
            if os.path.isdir(p):
                n = os.path.basename(p.rstrip(os.sep))
                if not re.search(r'[\u4e00-\u9fa5]', n) and p not in self.queue:
                    self.queue.append(p)
                    self.list_widget.addItem(n)
        self.start_btn.setEnabled(len(self.queue) > 0)

    def on_start(self):
        self.start_btn.setEnabled(False)
        worker = UploadWorker(self.queue, self.repo_path, "1372601383-web", "QQai", "main")
        worker.signals.log.connect(self.log_view.appendPlainText)
        worker.signals.progress.connect(lambda d, t: self.prog_bar.setRange(0, t) or self.prog_bar.setValue(d))
        worker.signals.finished.connect(self.on_done)
        self.pool.start(worker)

    def on_done(self, ok, msg):
        self.start_btn.setEnabled(True)
        self.queue = [];
        self.list_widget.clear()
        QtWidgets.QMessageBox.information(self, "完成", msg)


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())