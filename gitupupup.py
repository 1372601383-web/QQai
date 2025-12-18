# -*- coding: utf-8 -*-
"""
PyQt6 GitHub 图片上传器（专业增强版）
功能：
1. 自动合并/覆盖同名文件夹（不再阻止上传）
2. 自动分批提交：每 900 张图片执行一次 commit/push，提高稳定性
3. 新增“清除暂存区”功能，解决 git index 锁定问题
4. 增强版 Git 实时日志流解析
"""

import os
import sys
import shutil
import subprocess
import time
from urllib.parse import quote
from datetime import datetime

from PyQt6 import QtCore, QtWidgets, QtGui
import openpyxl

# ---------------- CONFIG ----------------
GITHUB_USERNAME = "1372601383-web"
GITHUB_TOKEN = ""  # 如果是私有仓库或需要鉴权，请填写 Token
GITHUB_REPO = "QQai"
GITHUB_BRANCH = "main"
REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".bmp"}
EXCEL_SUFFIX = "_urls.xlsx"
BATCH_SIZE = 900  # 每批次上传的最大图片数量


# ----------------------------------------

def ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class WorkerSignals(QtCore.QObject):
    log = QtCore.pyqtSignal(str)
    progress = QtCore.pyqtSignal(int, int)
    speed = QtCore.pyqtSignal(str)
    finished = QtCore.pyqtSignal(bool, str)


class UploadWorker(QtCore.QRunnable):
    def __init__(self, src_folder, repo_root, username, repo, branch):
        super().__init__()
        self.src_folder = src_folder
        self.repo_root = repo_root
        self.username = username
        self.repo = repo
        self.branch = branch
        self.signals = WorkerSignals()

    def log(self, msg):
        self.signals.log.emit(f"[{ts()}] {msg}")

    def run_command(self, cmd, cwd=None):
        """运行命令并实时获取输出"""
        self.log(f"执行命令: {' '.join(cmd)}")
        process = subprocess.Popen(
            cmd, cwd=cwd or self.repo_root,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, encoding='utf-8', errors='replace'
        )
        output = []
        while True:
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break
            if line:
                clean_line = line.strip()
                self.log(f"  [Git] {clean_line}")
                output.append(clean_line)
                # 尝试解析速度
                if "/s" in clean_line:
                    parts = clean_line.split()
                    for p in parts:
                        if "/s" in p:
                            self.signals.speed.emit(p)
        return process.returncode, "\n".join(output)

    def run(self):
        try:
            folder_name = os.path.basename(self.src_folder.rstrip(os.sep))
            dest_dir = os.path.join(self.repo_root, folder_name)

            # 1. 扫描所有图片
            all_images = []
            for root, _, files in os.walk(self.src_folder):
                for f in files:
                    if os.path.splitext(f)[1].lower() in IMAGE_EXT:
                        all_images.append(os.path.join(root, f))

            total_count = len(all_images)
            if total_count == 0:
                self.signals.finished.emit(False, "文件夹内未找到支持的图片。")
                return

            self.log(f"检测到 {total_count} 张图片，准备开始分批上传（每批最多 {BATCH_SIZE} 张）...")

            # 2. 复制文件（覆盖模式）
            self.log(f"正在同步文件到仓库: {dest_dir}")
            os.makedirs(dest_dir, exist_ok=True)
            for img_path in all_images:
                rel_path = os.path.relpath(img_path, self.src_folder)
                target_path = os.path.join(dest_dir, rel_path)
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                shutil.copy2(img_path, target_path)

            # 3. 分批 Git 操作
            for i in range(0, total_count, BATCH_SIZE):
                batch_num = (i // BATCH_SIZE) + 1
                batch_files = all_images[i: i + BATCH_SIZE]
                self.log(f"--- 正在处理第 {batch_num} 批次 ({len(batch_files)} 张图片) ---")

                # Git Add - 仅 add 当前批次对应的文件（相对于仓库的路径）
                for img_path in batch_files:
                    rel_to_repo = os.path.relpath(
                        os.path.join(dest_dir, os.path.relpath(img_path, self.src_folder)),
                        self.repo_root
                    )
                    subprocess.run(["git", "add", rel_to_repo], cwd=self.repo_root)

                # Commit
                commit_msg = f"Upload {folder_name} batch {batch_num} ({ts()})"
                self.run_command(["git", "commit", "-m", commit_msg])

                # Pull & Push
                self.log("同步远程仓库状态...")
                self.run_command(["git", "pull", "origin", self.branch, "--rebase"])

                self.log(f"正在推送第 {batch_num} 批次到 GitHub...")
                rc, _ = self.run_command(["git", "push", "origin", self.branch])

                if rc != 0:
                    self.signals.finished.emit(False, f"第 {batch_num} 批次推送失败，程序终止。")
                    return

                self.signals.progress.emit(min(i + BATCH_SIZE, total_count), total_count)

            # 4. 生成 Excel
            self.log("所有批次推送完成，正在生成 Excel URL 列表...")
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.append(["文件名", "占位", "jsDelivr URL"])

            processed_excel = 0
            for root, _, files in os.walk(dest_dir):
                for fname in files:
                    if os.path.splitext(fname)[1].lower() in IMAGE_EXT:
                        name_no_ext = os.path.splitext(fname)[0]
                        rel_path = os.path.relpath(os.path.join(root, fname), start=self.repo_root)
                        rel_posix = rel_path.replace(os.sep, "/")
                        encoded = "/".join(quote(p) for p in rel_posix.split("/"))
                        cdn_url = f"https://cdn.jsdelivr.net/gh/{self.username}/{self.repo}/{encoded}"
                        ws.append([name_no_ext, "", cdn_url])
                        processed_excel += 1

            excel_path = os.path.join(self.repo_root, f"{folder_name}{EXCEL_SUFFIX}")
            wb.save(excel_path)
            self.log(f"Excel 已生成: {excel_path}")
            self.signals.finished.emit(True, f"全部成功上传！\n文件数：{total_count}\nExcel：{excel_path}")

        except Exception as e:
            self.log(f"关键错误: {str(e)}")
            self.signals.finished.emit(False, str(e))


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.pool = QtCore.QThreadPool.globalInstance()
        self.selected_folder = None

    def init_ui(self):
        self.setWindowTitle("GitHub 图片上传器 Pro")
        self.resize(900, 700)
        self.setAcceptDrops(True)

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)

        # 顶部状态
        header = QtWidgets.QGroupBox("仓库配置")
        header_layout = QtWidgets.QHBoxLayout(header)
        header_layout.addWidget(QtWidgets.QLabel(f"<b>仓库:</b> {GITHUB_REPO} | <b>分支:</b> {GITHUB_BRANCH}"))
        header_layout.addStretch()

        self.clean_btn = QtWidgets.QPushButton("清除 Git 暂存区 (Unlock)")
        self.clean_btn.setToolTip("如果遇到 'index.lock' 错误或 Git 状态异常，请点击此按钮")
        self.clean_btn.clicked.connect(self.clear_git_index)
        header_layout.addWidget(self.clean_btn)
        layout.addWidget(header)

        # 拖拽区
        self.drag_area = QtWidgets.QLabel("拖拽图片文件夹到此处\n(支持覆盖上传 | 自动 900 张分批)")
        self.drag_area.setFixedHeight(120)
        self.drag_area.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.drag_area.setStyleSheet("""
            QLabel {
                background: #1e1e1e; color: #50fa7b; border: 2px dashed #50fa7b;
                border-radius: 10px; font-size: 15px; font-weight: bold;
            }
        """)
        layout.addWidget(self.drag_area)

        # 控制区
        ctrl_layout = QtWidgets.QHBoxLayout()
        self.count_label = QtWidgets.QLabel("未选择文件夹")
        self.start_btn = QtWidgets.QPushButton("开始分批同步")
        self.start_btn.setEnabled(False)
        self.start_btn.setMinimumHeight(40)
        self.start_btn.setStyleSheet("background: #44475a; color: white; font-weight: bold;")
        self.start_btn.clicked.connect(self.on_start)
        ctrl_layout.addWidget(self.count_label)
        ctrl_layout.addStretch()
        ctrl_layout.addWidget(self.start_btn)
        layout.addLayout(ctrl_layout)

        # 进度与速度
        prog_row = QtWidgets.QHBoxLayout()
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setStyleSheet("""
            QProgressBar { border: 1px solid #444; border-radius: 5px; text-align: center; }
            QProgressBar::chunk { background-color: #50fa7b; }
        """)
        self.speed_label = QtWidgets.QLabel("速度: --")
        prog_row.addWidget(self.progress_bar)
        prog_row.addWidget(self.speed_label)
        layout.addLayout(prog_row)

        # 日志区
        self.log_view = QtWidgets.QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet("background: #282a36; color: #f8f8f2; font-family: 'Consolas'; font-size: 12px;")
        layout.addWidget(self.log_view)

    def append_log(self, text):
        self.log_view.appendPlainText(text)
        self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())

    def clear_git_index(self):
        lock_file = os.path.join(REPO_ROOT, ".git", "index.lock")
        if os.path.exists(lock_file):
            try:
                os.remove(lock_file)
                self.append_log(f"[{ts()}] 成功移除 index.lock 锁定文件。")
            except Exception as e:
                self.append_log(f"[{ts()}] 移除锁定文件失败: {e}")

        subprocess.run(["git", "reset"], cwd=REPO_ROOT)
        self.append_log(f"[{ts()}] 已执行 git reset 清除暂存区状态。")
        QtWidgets.QMessageBox.information(self, "Git 修复", "暂存区已重置，锁定已解除。")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        path = event.mimeData().urls()[0].toLocalFile()
        if os.path.isdir(path):
            count = 0
            for _, _, files in os.walk(path):
                count += sum(1 for f in files if os.path.splitext(f)[1].lower() in IMAGE_EXT)

            if count > 0:
                self.selected_folder = path
                self.count_label.setText(f"已选: {os.path.basename(path)} ({count} 张图片)")
                self.start_btn.setEnabled(True)
                self.start_btn.setStyleSheet("background: #6272a4; color: white; font-weight: bold;")
                self.append_log(f"[{ts()}] 载入文件夹: {path}")
            else:
                self.append_log(f"[{ts()}] 错误: 文件夹内没有图片。")

    def on_start(self):
        self.start_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        worker = UploadWorker(self.selected_folder, REPO_ROOT, GITHUB_USERNAME, GITHUB_REPO, GITHUB_BRANCH)
        worker.signals.log.connect(self.append_log)
        worker.signals.progress.connect(lambda d, t: self.progress_bar.setRange(0, t) or self.progress_bar.setValue(d))
        worker.signals.speed.connect(lambda s: self.speed_label.setText(f"速度: {s}"))
        worker.signals.finished.connect(self.on_finished)
        self.pool.start(worker)

    def on_finished(self, success, message):
        self.start_btn.setEnabled(True)
        if success:
            QtWidgets.QMessageBox.information(self, "任务完成", message)
        else:
            QtWidgets.QMessageBox.critical(self, "任务失败", message)


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())