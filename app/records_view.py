from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
                               QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

EVENT_NAMES = {"EARLY_SURRENDER": "提前停止", "BREAK_SURRENDER": "全屏解除",
               "BREAK_COMPLETED": "休息成功", "EMERGENCY_EXIT": "紧急退出", "INTERRUPTED": "异常中断"}
PHOTO_NAMES = {"saved": "已保存", "quota_exceeded": "容量超限，未保存", "save_failed": "保存失败",
               "deleted": "照片已删除", "not_applicable": "无照片"}
VIDEO_NAMES = {"saved": "已保存", "quota_exceeded": "容量超限，未保存", "save_failed": "保存失败",
               "deleted": "录像已删除", "not_applicable": "无录像"}


def status_text(names, row, status_key, path_key):
    status = row.get(status_key) or "not_applicable"
    if status == "saved" and not Path(row.get(path_key) or "").is_file():
        return "文件已删除 / 不存在"
    return names.get(status, "未保存")


def short_time(value):
    """Compact timestamp for the table; the full ISO value stays in the details."""
    text = str(value or "")
    try:
        return datetime.fromisoformat(text).strftime("%m-%d %H:%M")
    except ValueError:
        return text[:16].replace("T", " ")


class RecordsView(QWidget):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.rows = []
        layout = QVBoxLayout(self)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["时间", "事件", "轮次", "录像", "照片"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self.table.horizontalHeader()
        for column in range(5):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self.selected)
        layout.addWidget(self.table, 1)
        self.details = QLabel("选择记录查看详情；列表不会加载照片或录像缩略图。")
        self.details.setWordWrap(True)
        layout.addWidget(self.details)
        buttons = QHBoxLayout()
        for text, callback in (("查看录像", self.view_video), ("删除录像", self.delete_video),
                               ("查看照片", self.view_photo), ("删除照片", self.delete_photo),
                               ("删除本条档案", self.delete_event), ("清空档案", self.clear)):
            button = QPushButton(text)
            button.setObjectName("secondaryButton")
            button.clicked.connect(callback)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        note = QLabel("删除档案只删除事件，不连带删除录像或照片；清理媒体需另行确认。")
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.refresh()

    def refresh(self):
        try:
            self.rows = self.store.all() if self.store is not None else []
            stats = self.store.stats() if self.store is not None else {}
            self.summary.setText(f"累计投降 {stats.get('SURRENDERS', 0)} 次  ·  提前停止 {stats.get('EARLY_SURRENDER', 0)}"
                                 f"  ·  全屏解除 {stats.get('BREAK_SURRENDER', 0)}\n"
                                 f"休息完成 {stats.get('BREAK_COMPLETED', 0)}  ·  紧急退出 {stats.get('EMERGENCY_EXIT', 0)}")
            self.table.setRowCount(len(self.rows))
            for index, row in enumerate(self.rows):
                values = [short_time(row["occurred_at"]), EVENT_NAMES.get(row["event_type"], row["event_type"]),
                          row["round_index"], self.video_status(row), self.photo_status(row)]
                for column, value in enumerate(values):
                    self.table.setItem(index, column, QTableWidgetItem(str(value or "—")))
        except Exception:
            self.summary.setText("档案无法读取。原数据库保留，请检查本地数据目录。")

    @staticmethod
    def photo_status(row):
        return status_text(PHOTO_NAMES, row, "photo_status", "photo_path")

    @staticmethod
    def video_status(row):
        return status_text(VIDEO_NAMES, row, "video_status", "video_path")

    def current(self):
        index = self.table.currentRow()
        return self.rows[index] if 0 <= index < len(self.rows) else None

    def selected(self):
        row = self.current()
        if row:
            self.details.setText(f"设定使用：{row.get('configured_seconds') or 0:g} 秒   "
                                 f"有效使用：{row.get('usage_seconds') or 0:g} 秒   "
                                 f"休息累计：{row.get('break_seconds') or 0:g} 秒\n"
                                 f"模式：{'自动循环' if row.get('mode') == 'automatic' else '手动计时'}   "
                                 f"宣言：{'已确认' if row.get('declaration_confirmed') else '不适用'}\n"
                                 f"动作验证：{self.video_status(row)}   "
                                 f"组数：{row.get('ai_cycles') if row.get('ai_cycles') is not None else '—'}   "
                                 f"照片：{self.photo_status(row)}\n"
                                 f"核验说明：{row.get('ai_reason') or '—'}")

    def view_video(self):
        row = self.current()
        path = Path(row.get("video_path") or "") if row else None
        if not path or not path.is_file():
            QMessageBox.information(self, "录像", "录像已删除 / 未保存。")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def view_photo(self):
        row = self.current()
        path = Path(row.get("photo_path") or "") if row else None
        if not path or not path.is_file():
            QMessageBox.information(self, "照片", "照片已删除 / 未保存。")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _confirmed(self, title, text):
        return QMessageBox.question(self, title, text, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                    QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes

    def delete_video(self):
        row = self.current()
        if row and self._confirmed("删除录像", "只删除这段录像，保留档案记录？"):
            try:
                self.store.delete_video(row["event_id"])
                self.refresh()
            except Exception:
                QMessageBox.warning(self, "删除失败", "录像未能删除，请检查文件权限。")

    def delete_photo(self):
        row = self.current()
        if row and self._confirmed("删除照片", "只删除这张照片，保留档案记录？"):
            try:
                self.store.delete_photo(row["event_id"])
                self.refresh()
            except Exception:
                QMessageBox.warning(self, "删除失败", "照片未能删除，请检查文件权限。")

    def delete_event(self):
        row = self.current()
        if row and self._confirmed("删除档案", "删除本条档案？录像与照片将保留，不会连带删除。"):
            try:
                self.store.delete_event(row["event_id"])
                self.refresh()
            except Exception:
                QMessageBox.warning(self, "删除失败", "档案未能删除，请检查数据目录。")

    def clear(self):
        if self.store is not None and self._confirmed("清空档案", "清空全部事件记录？磁盘上的录像与照片将保留。"):
            try:
                self.store.clear()
                self.refresh()
            except Exception:
                QMessageBox.warning(self, "清空失败", "档案未能清空，请检查数据目录。")
