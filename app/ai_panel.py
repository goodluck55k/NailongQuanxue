"""AI connection UI: the settings tab and the first-run reminder dialog."""
import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QVBoxLayout, QWidget)

from .config_store import ConfigWriteError
from .ai_config import (PROTOCOLS, PROTOCOL_ORDER, AiConfigError, AiSettings, clear_settings,
                        read_settings, save_settings)
from .async_task import run_async
from .theme import STYLE
from .vision_api import VisionClient, VisionError


class AiSettingsPanel(QWidget):
    """Editable view of the user's own vision endpoint; saves through ConfigStore."""

    saved = Signal(object)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.settings = read_settings(config.values)
        layout = QVBoxLayout(self)
        note = QLabel("动作挑战由一个支持图像输入的模型核验。地址、密钥与模型都由你自行填写；\n"
                      "密钥只保存在本机 settings.json，不会写入日志或档案，也不会随录像上传到别处。")
        note.setWordWrap(True)
        layout.addWidget(note)
        protocol_row = QHBoxLayout()
        protocol_row.addWidget(QLabel("接口协议"))
        self.protocol = QComboBox()
        for key in PROTOCOL_ORDER:
            self.protocol.addItem(PROTOCOLS[key], key)
        self.protocol.setCurrentIndex(max(0, self.protocol.findData(self.settings.protocol)))
        protocol_row.addWidget(self.protocol, 1)
        layout.addLayout(protocol_row)
        for label, attribute, placeholder, password in (
                ("Base URL", "base_url", "https://api.example.com/v1", False),
                ("API Key", "api_key", "仅存本机；本地服务可留空", True),
                ("模型 ID", "model", "必须支持图像输入，例如某个多模态模型", False)):
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            edit = QLineEdit(getattr(self.settings, attribute))
            edit.setPlaceholderText(placeholder)
            edit.setAccessibleName(label)
            if password:
                edit.setEchoMode(QLineEdit.EchoMode.Password)
            setattr(self, attribute, edit)
            row.addWidget(edit, 1)
            layout.addLayout(row)
        buttons = QHBoxLayout()
        self.save_button = QPushButton("保存配置")
        self.save_button.clicked.connect(self.save)
        self.test_button = QPushButton("测试连接")
        self.test_button.setObjectName("secondaryButton")
        self.test_button.clicked.connect(self.test)
        self.clear_button = QPushButton("清除配置")
        self.clear_button.setObjectName("secondaryButton")
        self.clear_button.clicked.connect(self.clear)
        for button in (self.save_button, self.test_button, self.clear_button):
            buttons.addWidget(button)
        buttons.addStretch()
        layout.addLayout(buttons)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.hint = QLabel(
            "未配置时无法通过动作挑战解除限制；五分钟休息自动结束与紧急退出不受影响。\n"
            "判定只把你选中一轮动作的少量画面帧发送到上面这个服务地址，"
            "原录像留在本机；请求会计入你自己账号的费用，可随时在这里清空配置撤回授权。"
            "密钥用 Windows 账户加密后保存在本机。")
        self.hint.setObjectName("muted")
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        layout.addStretch()
        self.refresh()

    def refresh(self):
        self.settings = read_settings(self.config.values)
        self.status.setText(self.settings.status_text() + f" · 密钥 {self.settings.masked_key()}")

    def collect(self):
        return AiSettings(protocol=self.protocol.currentData(), base_url=self.base_url.text(),
                          api_key=self.api_key.text(), model=self.model.text(),
                          verified=self.settings.verified, verified_at=self.settings.verified_at)

    def save(self):
        try:
            candidate = self.collect()
            changed = ((candidate.protocol, candidate.base_url, candidate.api_key, candidate.model)
                       != (self.settings.protocol, self.settings.base_url, self.settings.api_key,
                           self.settings.model))
            written = save_settings(self.config, candidate, verified=False if changed else None)
        except ConfigWriteError as error:
            logging.getLogger("NailongQuanxue").error(
                "AI config save failed: %s", error, exc_info=error.__cause__)
            self.status.setText(str(error))
            return False
        except (AiConfigError, OSError, ValueError) as error:
            self.status.setText(f"未保存：{error}")
            return False
        self.settings = written
        self.api_key.setText(written.api_key)
        self.status.setText(written.status_text() + "（配置已保存，可点“测试连接”确认可用）")
        self.saved.emit(written)
        return True

    def test(self):
        try:
            candidate = self.collect()
            written = save_settings(self.config, candidate, verified=False)
        except ConfigWriteError as error:
            self.status.setText(str(error))
            return
        except (AiConfigError, OSError, ValueError) as error:
            self.status.setText(f"无法测试：{error}")
            return
        self.settings = written
        self.save_button.setEnabled(False)
        self.test_button.setEnabled(False)
        self.status.setText("正在测试连接（只发送一段文字，不上传画面）…")
        run_async(lambda: VisionClient(written).ping(), lambda result, error: self._tested(written, result, error))

    def _tested(self, settings, result, error):
        self.save_button.setEnabled(True)
        self.test_button.setEnabled(True)
        if error is not None:
            message = error.user_message() if isinstance(error, VisionError) else "连接测试失败"
            self.status.setText(f"连接失败：{message}。配置已保存，可修改后重试。")
            return
        try:
            written = save_settings(self.config, settings, verified=True)
        except ConfigWriteError as error:
            self.status.setText("连接成功，但%s" % str(error))
            return
        except (AiConfigError, OSError, ValueError) as error:
            self.status.setText(f"连接成功，但配置未能写入本地文件：{error}")
            return
        self.settings = written
        self.status.setText(written.status_text() + f" · 模型回复：{result}")
        self.saved.emit(written)

    def clear(self):
        try:
            clear_settings(self.config)
        except ConfigWriteError as error:
            self.status.setText(str(error))
            return
        except (OSError, ValueError) as error:
            self.status.setText(f"无法写入本地配置：{error}")
            return
        for edit in (self.base_url, self.api_key, self.model):
            edit.clear()
        self.protocol.setCurrentIndex(0)
        self.refresh()
        self.saved.emit(self.settings)


class AiSetupDialog(QDialog):
    """First-run reminder; '稍后配置' keeps the timer usable without the challenge."""

    configured = Signal(object)

    def __init__(self, config, parent=None):
        super().__init__(None, Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("奶龙劝学 — 配置视觉 AI")
        self.setStyleSheet(STYLE)
        self.resize(620, 480)
        self.setMinimumSize(460, 360)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        title = QLabel("还没有配置视觉 AI")
        title.setStyleSheet("font-size:20px; font-weight:600;")
        layout.addWidget(title)
        intro = QLabel("V2.0 的投降挑战需要核验你模仿奶龙的动作，所以要接入一个你自己提供的视觉模型。\n"
                       "现在可以先点“稍后配置”，计时和五分钟休息仍会正常工作；未配置时动作挑战不能通过。")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.panel = AiSettingsPanel(config, self)
        self.panel.saved.connect(self._saved)
        layout.addWidget(self.panel, 1)
        footer = QHBoxLayout()
        later = QPushButton("稍后配置")
        later.setObjectName("secondaryButton")
        later.clicked.connect(self.reject)
        save = QPushButton("保存配置")
        save.clicked.connect(self._save)
        footer.addWidget(later)
        footer.addStretch()
        footer.addWidget(save)
        layout.addLayout(footer)

    def _save(self):
        if self.panel.save() and self.panel.settings.configured:
            self.accept()

    def _saved(self, settings):
        if settings.configured:
            self.configured.emit(settings)


def message_for(error):
    return error.user_message() if isinstance(error, VisionError) else "AI 调用失败，请稍后重试。"
