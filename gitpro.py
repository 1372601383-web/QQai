# -*- coding: utf-8 -*-
import os, sys, shutil, subprocess, re, openpyxl, time
from datetime import datetime
from urllib.parse import quote
from PyQt6 import QtCore, QtWidgets, QtGui

# Windows 下彻底隐藏 CMD 窗口
CREATE_NO_WINDOW = 0x08000000


def get_resource_path():
    if getattr(sys, 'frozen', False): return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


REPO_ROOT = get_resource_path()
CONFIG_FILE = os.path.join(REPO_ROOT, "config.txt")
GITHUB_USERNAME = "1372601383-web"
GITHUB_REPO = "QQai"
GITHUB_BRANCH = "main"
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".bmp"}
EXCEL_SUFFIX = "_urls.xlsx"
BATCH_SIZE = 500

THEMES = {
    "经典深绿 (Classic Green)": {"main_bg": "#121212", "text": "#ffffff", "accent": "#2e8b57",
                                 "drag_gradient": "qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1, stop:0 #162b2b, stop:1 #1f2f2f)",
                                 "log_bg": "#0f1010", "btn_hover": "#3e9b67", "input_bg": "#252525"},
    "赛博朋克 (Cyber Pink)": {"main_bg": "#0d0221", "text": "#00f5ff", "accent": "#ff007f",
                              "drag_gradient": "qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1, stop:0 #2d0b3a, stop:1 #0d0221)",
                              "log_bg": "#050110", "btn_hover": "#ff4da6", "input_bg": "#1a0b35"},
    "深邃星空 (Space Blue)": {"main_bg": "#0b0e14", "text": "#ffffff", "accent": "#4a90e2",
                              "drag_gradient": "qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1, stop:0 #1a2332, stop:1 #0b0e14)",
                              "log_bg": "#080a0f", "btn_hover": "#64a4ed", "input_bg": "#1c222d"},
    "魅惑紫罗兰 (Violet)": {"main_bg": "#1a1625", "text": "#e0d7f2", "accent": "#8a2be2",
                            "drag_gradient": "qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1, stop:0 #241e30, stop:1 #1a1625)",
                            "log_bg": "#120f1a", "btn_hover": "#a052ee", "input_bg": "#282236"}
}


def ts(): return datetime.now().strftime("%H:%M:%S")


class CustomDialog(QtWidgets.QDialog):
    def __init__(self, parent, theme_name, title_text, msg, show_cancel=False):
        super().__init__(parent)
        self.setWindowFlags(QtCore.Qt.WindowType.FramelessWindowHint | QtCore.Qt.WindowType.Dialog)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.theme = THEMES[theme_name]
        layout = QtWidgets.QVBoxLayout(self)
        frame = QtWidgets.QFrame();
        frame.setObjectName("DlgFrame")
        frame.setStyleSheet(
            f"QFrame#DlgFrame {{ background: {self.theme['main_bg']}; border: 2px solid {self.theme['accent']}; border-radius: 12px; }}")
        layout.addWidget(frame)
        f_layout = QtWidgets.QVBoxLayout(frame)
        title = QtWidgets.QLabel(title_text);
        title.setStyleSheet(f"font-weight: bold; color: {self.theme['accent']}; font-size: 15px;")
        content = QtWidgets.QLabel(msg);
        content.setWordWrap(True);
        content.setStyleSheet(f"color: {self.theme['text']}; font-size: 12px; margin: 10px 0;")
        btn_box = QtWidgets.QHBoxLayout();
        btn_style = f"background: {self.theme['accent']}; color: white; border-radius: 5px; padding: 6px 15px; font-weight: bold; border: none;"
        self.ok_btn = QtWidgets.QPushButton("关你屁事" if show_cancel else "知道了");
        self.ok_btn.setStyleSheet(btn_style);
        self.ok_btn.clicked.connect(self.accept)
        btn_box.addStretch()
        if show_cancel:
            self.cancel_btn = QtWidgets.QPushButton("朕要三思");
            self.cancel_btn.setStyleSheet(
                f"background: {self.theme['input_bg']}; color: {self.theme['text']}; border-radius: 5px; padding: 6px 15px;");
            self.cancel_btn.clicked.connect(self.reject)
            btn_box.addWidget(self.cancel_btn)
        btn_box.addWidget(self.ok_btn);
        f_layout.addWidget(title);
        f_layout.addWidget(content);
        f_layout.addLayout(btn_box);
        self.setFixedSize(320, 160)


class WorkerSignals(QtCore.QObject):
    log = QtCore.pyqtSignal(str);
    progress = QtCore.pyqtSignal(int, int);
    finished = QtCore.pyqtSignal(bool, str)


class UploadWorker(QtCore.QRunnable):
    def __init__(self, folder_list, repo_path, username, repo, branch, accent_color):
        super().__init__()
        self.folder_list, self.repo_root = folder_list, repo_path
        self.username, self.repo, self.branch = username, repo, branch
        self.accent_color = accent_color
        self.signals = WorkerSignals()

    def run_git_safe(self, cmd, desc):
        # 1. 强行先清理现场（防止锁死）
        subprocess.run(["git", "rebase", "--abort"], cwd=self.repo_root, creationflags=CREATE_NO_WINDOW)
        subprocess.run(["git", "merge", "--abort"], cwd=self.repo_root, creationflags=CREATE_NO_WINDOW)

        # 2. 如果是同步环节，强制改写为安全模式
        if desc == "快好了":
            cmd = ["git", "pull", "origin", self.branch, "--no-rebase", "-X", "ours"]

        # 3. 设置 Git 编码
        subprocess.run(["git", "config", "core.quotepath", "false"], cwd=self.repo_root, creationflags=CREATE_NO_WINDOW)

        # 4. 【关键步骤】正式定义并启动 process
        # 确保这一行在任何使用 process 变量的代码之前执行
        process = subprocess.Popen(
            cmd, cwd=self.repo_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding='utf-8',
            errors='replace',
            creationflags=CREATE_NO_WINDOW
        )

        raw_logs = []
        # 5. 现在可以安全地使用 process 了
        while True:
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break
            if line:
                s_line = line.strip()
                raw_logs.append(s_line)
                self.signals.log.emit(f"   <span style='color:#888;'>[🐷🐷🐷-{desc}] {s_line}</span>")

        if process.poll() != 0:
            full_err = "\n".join(raw_logs)
            if "commit" in cmd and ("nothing to commit" in full_err or "no changes added" in full_err):
                return 0
            raise Exception(f"{desc}环节失败！<br>报错反馈：<br>{full_err}")
        return 0

    def run(self):
        try:
            for src in self.folder_list:
                f_name = os.path.basename(src.rstrip(os.sep))
                dest = os.path.join(self.repo_root, f_name)
                os.makedirs(dest, exist_ok=True)

                imgs = [f for f in os.listdir(src) if os.path.splitext(f)[1].lower() in IMAGE_EXT]
                total = len(imgs)
                self.signals.log.emit(f"<b>[{ts()}] 正在搬运: {f_name} ({total}张)</b>")

                # 批量搬运
                for b in imgs:
                    shutil.copy2(os.path.join(src, b), os.path.join(dest, b))

                # 一次性 add
                subprocess.run(["git", "add", "."], cwd=self.repo_root, creationflags=CREATE_NO_WINDOW)

                self.signals.log.emit(
                    f"<b><span style='color:{self.accent_color};'>[{ts()}] 弹药装填完毕，开始发射</span></b>")

                # 发射序列
                self.run_git_safe(["git", "commit", "-m", f"Up {f_name}"], "没好")
                self.run_git_safe(["git", "pull", "origin", self.branch], "快好了")
                self.run_git_safe(["git", "push", "origin", self.branch], "马上好了")

                self.signals.progress.emit(total, total)

                # 生成 Excel
                wb = openpyxl.Workbook()
                ws = wb.active
                ws.append(["文件名", "凑数列", "URL"])
                for f in sorted(os.listdir(dest)):
                    if os.path.splitext(f)[1].lower() in IMAGE_EXT:
                        ws.append([os.path.splitext(f)[0], "",
                                   f"https://cdn.jsdelivr.net/gh/{self.username}/{self.repo}/{f_name}/{quote(f)}"])
                wb.save(os.path.join(self.repo_root, f"{f_name}{EXCEL_SUFFIX}"))

            self.signals.log.emit(f"<b>[{ts()}] 任务全数达成！</b>")
            self.signals.finished.emit(True, "OK")
        except Exception as e:
            self.signals.log.emit(f"<span style='color:#ff4d4d;'><b>[{ts()}] 坠机详情：</b><br>{str(e)}</span>")
            self.signals.finished.emit(False, "FAIL")


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__();
        self.repo_path, self.queue, self._old_pos = REPO_ROOT, [], None
        self.setWindowFlags(QtCore.Qt.WindowType.FramelessWindowHint);
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.init_ui();
        self.load_skin_config()

    def init_ui(self):
        self.setFixedSize(640, 580)
        self.bg_frame = QtWidgets.QFrame(self);
        self.bg_frame.setObjectName("MainFrame");
        self.setCentralWidget(self.bg_frame)
        layout = QtWidgets.QVBoxLayout(self.bg_frame);
        layout.setContentsMargins(12, 10, 12, 12);
        layout.setSpacing(6)
        tb = QtWidgets.QHBoxLayout();
        self.title_label = QtWidgets.QLabel('🚀 <b>GITHUB MISSION CONTROL</b>')
        bw = QtWidgets.QWidget();
        bl = QtWidgets.QHBoxLayout(bw);
        bl.setContentsMargins(0, 0, 0, 0);
        bl.setSpacing(2)
        self.min_btn, self.close_btn = QtWidgets.QPushButton("–"), QtWidgets.QPushButton("✕")
        for b in [self.min_btn, self.close_btn]: b.setFixedSize(30, 24); bl.addWidget(b)
        self.min_btn.clicked.connect(self.showMinimized);
        self.close_btn.clicked.connect(self.close)
        tb.addWidget(self.title_label);
        tb.addStretch();
        tb.addWidget(bw);
        layout.addLayout(tb)

        cb = QtWidgets.QHBoxLayout();
        self.theme_combo = QtWidgets.QComboBox();
        self.theme_combo.addItems(THEMES.keys())
        self.theme_combo.currentTextChanged.connect(self.on_theme_changed)
        self.deploy_btn = QtWidgets.QPushButton("⚡ 初始化");
        self.clean_btn = QtWidgets.QPushButton("🧹 修复")
        self.deploy_btn.clicked.connect(self.run_deploy);
        self.clean_btn.clicked.connect(self.run_clean)
        cb.addWidget(self.theme_combo, 1);
        cb.addWidget(self.deploy_btn);
        cb.addWidget(self.clean_btn);
        layout.addLayout(cb)

        self.path_display = QtWidgets.QLabel();
        self.path_display.setStyleSheet("font-size: 9px;");
        layout.addWidget(self.path_display)
        self.drag_area = QtWidgets.QLabel("拖拽文件夹到这里(可批量)\n注意文件夹不要包含中文，带点特色更好");
        self.drag_area.setFixedHeight(60);
        self.drag_area.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter);
        layout.addWidget(self.drag_area)
        self.list_widget = QtWidgets.QListWidget();
        self.list_widget.setFixedHeight(40);
        layout.addWidget(self.list_widget)
        self.start_btn = QtWidgets.QPushButton("🚀 弹 射 起 步 🚀");
        self.start_btn.setFixedHeight(45);
        self.start_btn.setEnabled(False);
        self.start_btn.clicked.connect(self.on_start_confirm);
        layout.addWidget(self.start_btn)
        pl = QtWidgets.QHBoxLayout();
        self.prog_bar = QtWidgets.QProgressBar();
        self.prog_bar.setFixedHeight(8);
        self.speed_label = QtWidgets.QLabel("READY")
        pl.addWidget(self.prog_bar, 1);
        pl.addWidget(self.speed_label);
        layout.addLayout(pl)
        self.log_view = QtWidgets.QTextBrowser();
        layout.addWidget(self.log_view)

    def apply_theme(self, theme_name):
        t = THEMES[theme_name]
        self.bg_frame.setStyleSheet(
            f"QFrame#MainFrame {{ background-color: {t['main_bg']}; border-radius: 12px; border: 2px solid {t['accent']}; }} QLabel {{ color: {t['text']}; }}")
        btn_style = "border-radius: 4px; font-weight: bold; border: none; font-size: 11px;"
        self.min_btn.setStyleSheet(f"QPushButton {{ background: {t['input_bg']}; color: {t['text']}; {btn_style} }}")
        self.close_btn.setStyleSheet(f"QPushButton {{ background: {t['input_bg']}; color: {t['text']}; {btn_style} }}")
        self.theme_combo.setStyleSheet(
            f"QComboBox {{ background: {t['input_bg']}; color: {t['text']}; border: 1px solid {t['accent']}; border-radius: 4px; padding: 2px; }}")
        accent_btn = f"background: {t['accent']}; color: white; border-radius: 5px; font-weight: bold; padding: 3px 8px;"
        self.deploy_btn.setStyleSheet(accent_btn);
        self.clean_btn.setStyleSheet(accent_btn)
        self.start_btn.setStyleSheet(f"QPushButton {{ {accent_btn} font-size: 14px; }}")
        self.drag_area.setStyleSheet(
            f"background: {t['drag_gradient']}; border: 1px dashed {t['accent']}; border-radius: 8px; color: {t['text']}; font-weight: bold;")
        self.log_view.setStyleSheet(
            f"background: {t['log_bg']}; color: {t['text']}; border-radius: 5px; border: 1px solid #333; font-family: Consolas; font-size: 12px;")
        self.list_widget.setStyleSheet(
            f"background: {t['log_bg']}; color: {t['text']}; border-radius: 5px; border: 1px solid #333;")
        self.prog_bar.setStyleSheet(
            f"QProgressBar {{ background: {t['input_bg']}; border-radius: 4px; border: none; text-align: center; color: transparent; }} QProgressBar::chunk {{ background: {t['accent']}; border-radius: 4px; }}")
        self.update_path_ui()

    def run_deploy(self):
        MY_TOKEN = "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"
        try:
            if not os.path.exists(os.path.join(self.repo_path, ".git")):
                subprocess.run(["git", "init"], cwd=self.repo_path, creationflags=0x08000000)

            # 强行对齐身份
            subprocess.run(["git", "config", "user.email", "1372601383@qq.com"], cwd=self.repo_path,
                           creationflags=0x08000000)
            subprocess.run(["git", "config", "user.name", "1372601383-web"], cwd=self.repo_path,
                           creationflags=0x08000000)

            # --- 关键：先写忽略名单，再加远程地址 ---
            with open(os.path.join(self.repo_path, ".gitignore"), "w", encoding="utf-8") as f:
                f.write("*.exe\ngit_last.exe\nconfig.txt\n*.xlsx\n*.py\n.gitignore\n")

            # 强制重刷远程地址（防止 Token 没写进去）
            auth_url = f"https://1372601383-web:{MY_TOKEN}@github.com/1372601383-web/QQai.git"
            subprocess.run(["git", "remote", "remove", "origin"], cwd=self.repo_path, creationflags=0x08000000)
            subprocess.run(["git", "remote", "add", "origin", auth_url], cwd=self.repo_path, creationflags=0x08000000)

            # 确保在 main 分支
            subprocess.run(["git", "checkout", "-b", "main"], cwd=self.repo_path, creationflags=0x08000000)
            subprocess.run(["git", "branch", "-M", "main"], cwd=self.repo_path, creationflags=0x08000000)

            self.log_view.append(f"<b>[{ts()}] ✅ 基地防御系统已升级：EXE 已被永久隔离！</b>")
            self.update_path_ui()
        except Exception as e:
            self.log_view.append(f"部署失败: {str(e)}")

    def run_clean(self):
        try:
            # 1. 强制把“手动删除”的行为登记到暂存盘
            # git add -A 会告诉 Git：本地删了的，仓库也要标记删除
            subprocess.run(["git", "add", "-A"], cwd=self.repo_path, creationflags=0x08000000)

            # 2. 提交这个删除动作（如果不提交，重置还是会回来）
            subprocess.run(["git", "commit", "-m", "Clean Folders", "--allow-empty"],
                           cwd=self.repo_path, creationflags=0x08000000)

            # 3. 现在执行清理，把那些没追踪的垃圾彻底抹除
            # 同时排除掉我们要保命的 EXE 和 config.txt
            clean_cmd = ["git", "clean", "-fd", "-e", "*.exe", "-e", "config.txt"]
            subprocess.run(clean_cmd, cwd=self.repo_path, creationflags=0x08000000)

            self.log_view.append(f"<b>[{ts()}] 🧹 基地已净空</b>")
            self.log_view.append(f"<span style='color:#888;'>   [提示] 已同步删除记录，那些东西再也不会回来了。</span>")

            # 清空 UI 列表
            self.queue = [];
            self.list_widget.clear();
            self.start_btn.setEnabled(False)
        except Exception as e:
            self.log_view.append(f"清场失败: {str(e)}")
    def update_path_ui(self):
        is_git = os.path.exists(os.path.join(self.repo_path, ".git"));
        self.path_display.setText(f"本地仓库位置: {self.repo_path} {'🟢' if is_git else '🔴'}")

    def on_theme_changed(self, n):
        self.apply_theme(n); open(CONFIG_FILE, "w", encoding="utf-8").write(n)

    def load_skin_config(self):
        n = "经典深绿 (Classic Green)"
        if os.path.exists(CONFIG_FILE):
            try:
                s = open(CONFIG_FILE, "r", encoding="utf-8").read().strip(); n = s if s in THEMES else n
            except:
                pass
        self.theme_combo.setCurrentText(n);
        self.apply_theme(n)

    def mousePressEvent(self, e):
        if e.button() == QtCore.Qt.MouseButton.LeftButton: self._old_pos = e.globalPosition().toPoint()

    def mouseMoveEvent(self, e):
        if self._old_pos: delta = e.globalPosition().toPoint() - self._old_pos; self.move(self.x() + delta.x(),
                                                                                          self.y() + delta.y()); self._old_pos = e.globalPosition().toPoint()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.acceptProposedAction()

    def dropEvent(self, e):
        for url in e.mimeData().urls():
            p = url.toLocalFile()
            if os.path.isdir(p) and p not in self.queue: self.queue.append(p); self.list_widget.addItem(
                os.path.basename(p))
        self.start_btn.setEnabled(len(self.queue) > 0)

    def on_start_confirm(self):
        confirm_dlg = CustomDialog(self, self.theme_combo.currentText(), "桥豆麻袋",
                                   "冲动\n图片尺寸改好了吗？\n确认无误才开始上传。", show_cancel=True)
        if confirm_dlg.exec(): self.start_mission()

    def start_mission(self):
        self.start_btn.setEnabled(False);
        self.log_view.clear()
        accent = THEMES[self.theme_combo.currentText()]['accent']
        worker = UploadWorker(self.queue, self.repo_path, GITHUB_USERNAME, GITHUB_REPO, GITHUB_BRANCH, accent)
        worker.signals.log.connect(self.log_view.append)
        worker.signals.progress.connect(lambda d, t: self.prog_bar.setRange(0, t) or self.prog_bar.setValue(d))
        worker.signals.finished.connect(self.on_done)
        QtCore.QThreadPool.globalInstance().start(worker)

    def on_done(self, ok, msg):
        self.start_btn.setEnabled(True);
        self.queue = [];
        self.list_widget.clear()
        if ok:
            report_dlg = CustomDialog(self, self.theme_combo.currentText(), "大王！事情办清楚了", "标题+URL表格已生成，存放于本地仓库目录下。",
                                      show_cancel=False)
            report_dlg.ok_btn.setText("查看目录");
            report_dlg.ok_btn.clicked.disconnect()
            report_dlg.ok_btn.clicked.connect(lambda: [os.startfile(self.repo_path), report_dlg.accept()]);
            report_dlg.exec()


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv);
    w = MainWindow();
    w.show();
    sys.exit(app.exec())