"""The V2.0 surrender workflow: declaration → demo → recording → verification.

The dialog owns no archive code. It records a temporary clip, asks the user's
own vision model to verify it, and hands the confirmed clip path upwards. A
technical failure (no configuration, network error, unparsable reply) can never
enable the confirmation button.
"""
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit, QProgressBar,
                               QPushButton, QStackedWidget, QVBoxLayout, QWidget)

from .action_verdict import check_evidence, decide, failure, prompt_for
from .async_task import run_async
from .camera_recorder import DEFAULT_CLIP_MS, CameraRecorder
from .frame_sampler import FrameSampler
from .supervision import DECLARATION
from .theme import STYLE
from .video_break import VideoBreak
from .vision_api import VisionClient, VisionError

PAGE_WRITING, PAGE_VIDEO, PAGE_RECORD, PAGE_RESULT = range(4)
VERIFY_WATCHDOG_MS = 90000


class ImageView(QLabel):
    def __init__(self):
        super().__init__()
        self.image = QImage()
        self.setMinimumSize(260, 160)
        self.setMaximumHeight(300)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background:white; border:1px solid #E3D7C1; border-radius:10px;")

    def show_image(self, image):
        self.image = image
        self._render()

    def _render(self):
        if self.image.isNull():
            self.clear()
        else:
            self.setPixmap(QPixmap.fromImage(self.image).scaled(
                self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event):
        self._render()
        super().resizeEvent(event)


class LiveVerifier:
    """Evaluates frames with the model the user configured; never fakes a pass."""

    def __init__(self, settings):
        self.settings = settings

    def evaluate(self, prompt, images):
        if self.settings is None or not self.settings.configured:
            raise VisionError("config", "尚未配置视觉 AI，动作挑战无法通过")
        return VisionClient(self.settings).evaluate(prompt, images)


class SurrenderDialog(QDialog):
    confirm_requested = Signal(str, str, object)
    ai_setup_requested = Signal()

    def __init__(self, controller, token, parent=None, camera_factory=CameraRecorder,
                 verifier=None, clip_ms=DEFAULT_CLIP_MS):
        # The main window may be minimized or hidden to tray while supervising.
        super().__init__(None, Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint)
        self.controller, self.token = controller, token
        self.camera_factory = camera_factory
        self.verifier = verifier
        self.clip_ms = clip_ms
        self.recorder = None
        self.guide = None
        self.clip_path = None
        self.verdict = None
        self.verifying = False
        self.submitting = False
        self.cleaned = False
        self._watchdog = QTimer(self)
        self._watchdog.setSingleShot(True)
        self._watchdog.setInterval(VERIFY_WATCHDOG_MS)
        self._watchdog.timeout.connect(self._verify_timeout)
        self.setWindowTitle("奶龙投降书")
        self.setStyleSheet(STYLE)
        self.resize(560, 560)
        self.setMinimumSize(440, 430)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        title = QLabel("再坚持一下，还是选择投降？")
        title.setStyleSheet("font-size:20px; font-weight:600;")
        layout.addWidget(title)
        self.pages = QStackedWidget()
        layout.addWidget(self.pages, 1)
        self._build_writing()
        self._build_video()
        self._build_record()
        self._build_result()
        self.message = QLabel("")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        self.cancel_button = QPushButton("继续坚持 / 取消")
        self.cancel_button.setObjectName("secondaryButton")
        self.cancel_button.clicked.connect(self.reject)
        layout.addWidget(self.cancel_button)
        self.finished.connect(lambda *_: self.cleanup())

    # --- pages ---------------------------------------------------------
    def _build_writing(self):
        page = QWidget()
        box = QVBoxLayout(page)
        self.ai_note = QLabel()
        self.ai_note.setWordWrap(True)
        box.addWidget(self.ai_note)
        intro = QLabel("第一步 · 手动准确输入下方宣言\n我是废物\n\n计时仍在继续，取消可返回继续坚持。")
        intro.setWordWrap(True)
        box.addWidget(intro)
        self.declaration = QLineEdit()
        self.declaration.setAccessibleName("投降宣言")
        self.declaration.setPlaceholderText("请手动输入宣言")
        box.addWidget(self.declaration)
        self.next_button = QPushButton("下一步 · 看示范")
        self.next_button.setEnabled(False)
        self.next_button.clicked.connect(self.next_step)
        self.declaration.textChanged.connect(lambda text: self.next_button.setEnabled(text == DECLARATION))
        box.addWidget(self.next_button)
        self.ai_button = QPushButton("配置视觉 AI")
        self.ai_button.setObjectName("secondaryButton")
        self.ai_button.clicked.connect(self.ai_setup_requested.emit)
        box.addWidget(self.ai_button)
        box.addStretch()
        self.pages.addWidget(page)

    def _build_video(self):
        page = QWidget()
        box = QVBoxLayout(page)
        note = QLabel("第二步 · 先看一遍奶龙的示范\n"
                      "记下动作：一只手放在腹部附近，身体明显前倾再回正，连续两组。不需要出声，也不要求表情。")
        note.setWordWrap(True)
        box.addWidget(note)
        self.guide_view = ImageView()
        box.addWidget(self.guide_view, 1)
        self.guide_message = QLabel("正在播放内置示范视频（静音）…")
        self.guide_message.setWordWrap(True)
        box.addWidget(self.guide_message)
        row = QHBoxLayout()
        self.replay_button = QPushButton("再看一遍")
        self.replay_button.setObjectName("secondaryButton")
        self.replay_button.clicked.connect(self.play_guide)
        self.start_record_button = QPushButton("开始录制（12 秒）")
        self.start_record_button.clicked.connect(self.begin_recording)
        row.addWidget(self.replay_button)
        row.addWidget(self.start_record_button)
        box.addLayout(row)
        self.pages.addWidget(page)

    def _build_record(self):
        page = QWidget()
        box = QVBoxLayout(page)
        self.record_note = QLabel("第三步 · 对着摄像头模仿\n"
                                  "至少一只手放在腹部附近，身体前倾回正两组；画面保持安静稳定，不需要说话。")
        self.record_note.setWordWrap(True)
        box.addWidget(self.record_note)
        self.upload_note = QLabel()
        self.upload_note.setObjectName("muted")
        self.upload_note.setWordWrap(True)
        box.addWidget(self.upload_note)
        self.preview = ImageView()
        box.addWidget(self.preview, 1)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, self.clip_ms)
        self.progress_bar.setTextVisible(False)
        box.addWidget(self.progress_bar)
        self.record_status = QLabel("准备录制…")
        self.record_status.setWordWrap(True)
        box.addWidget(self.record_status)
        row = QHBoxLayout()
        self.stop_button = QPushButton("结束录制")
        self.stop_button.setObjectName("secondaryButton")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_recording)
        self.reconnect_button = QPushButton("重新连接摄像头")
        self.reconnect_button.setObjectName("secondaryButton")
        self.reconnect_button.clicked.connect(self.begin_recording)
        row.addWidget(self.stop_button)
        row.addWidget(self.reconnect_button)
        box.addLayout(row)
        self.pages.addWidget(page)

    def _build_result(self):
        page = QWidget()
        box = QVBoxLayout(page)
        self.result_title = QLabel("正在核验动作…")
        self.result_title.setStyleSheet("font-size:16px; font-weight:600;")
        self.result_title.setWordWrap(True)
        box.addWidget(self.result_title)
        self.result_detail = QLabel("")
        self.result_detail.setWordWrap(True)
        box.addWidget(self.result_detail)
        self.thumb = ImageView()
        box.addWidget(self.thumb, 1)
        row = QHBoxLayout()
        self.retry_button = QPushButton("重新挑战")
        self.retry_button.setObjectName("secondaryButton")
        self.retry_button.clicked.connect(self.retry)
        self.confirm_button = QPushButton("确认投降")
        self.confirm_button.setEnabled(False)
        self.confirm_button.clicked.connect(self.confirm)
        row.addWidget(self.retry_button)
        row.addWidget(self.confirm_button)
        box.addLayout(row)
        self.result_ai_button = QPushButton("检查 AI 配置")
        self.result_ai_button.setObjectName("secondaryButton")
        self.result_ai_button.clicked.connect(self.ai_setup_requested.emit)
        box.addWidget(self.result_ai_button)
        self.pages.addWidget(page)

    # --- steps ---------------------------------------------------------
    def update_ai_note(self, status_text):
        self.ai_note.setText(status_text)
        configured = "未配置" not in status_text
        self.ai_button.setVisible(not configured)
        host = getattr(getattr(self.verifier, "settings", None), "host", "")
        if configured and host:
            self.upload_note.setText(
                f"录制结束后只把少量画面帧发送到 {host} 做判定（计入你的账号费用），原录像留在本机。")
        else:
            self.upload_note.setText("未配置视觉 AI 时无法上传画面，动作挑战不会通过。")

    def next_step(self):
        if not self.controller.accept_writing(self.token, self.declaration.text()):
            self.message.setText("宣言输入不正确，或本轮监督状态已变化。")
            return
        self.declaration.clear()
        self.pages.setCurrentIndex(PAGE_VIDEO)
        self.play_guide()

    def play_guide(self):
        if self.cleaned:
            return
        if self.guide is not None:
            self.guide.close()
            self.guide = None
        self.guide_view.show_image(QImage())
        self.guide = VideoBreak(self)
        self.guide.frame_ready.connect(self._guide_frame)
        self.guide.failed.connect(self._guide_failed)
        self.guide_message.setText("正在播放内置示范视频（静音）…")
        self.guide.start()

    def _guide_frame(self, image):
        if not self.cleaned and self.pages.currentIndex() == PAGE_VIDEO:
            self.guide_view.show_image(image)
            self.guide_message.setText("示范播放中。看清动作后点“开始录制”。")

    def _guide_failed(self, reason):
        if not self.cleaned:
            self.guide_message.setText(f"{reason}。可以直接开始录制。")

    def begin_recording(self):
        if self.cleaned:
            return
        self.stop_guide()
        if not self.controller.mark_video_watched(self.token):
            self.message.setText("本轮监督状态已变化，请重新开始。")
            return
        self.pages.setCurrentIndex(PAGE_RECORD)
        self.verdict, self.clip_path = None, None
        self.confirm_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.preview.show_image(QImage())
        self.record_status.setText("正在连接摄像头…")
        self.stop_button.setEnabled(False)
        if self.recorder is not None:
            self.recorder.stop()
            self.recorder.deleteLater()
            self.recorder = None
        self.recorder = self.camera_factory(self, clip_ms=self.clip_ms)
        self.recorder.preview.connect(self._live)
        self.recorder.started.connect(self._recording_started)
        self.recorder.progress.connect(self._recording_progress)
        self.recorder.finished.connect(self._clip_ready)
        self.recorder.failed.connect(self._recorder_failed)
        self.recorder.start()

    def _live(self, image):
        if not self.cleaned:
            self.preview.show_image(image)

    def _recording_started(self):
        if self.cleaned:
            return
        self.stop_button.setEnabled(True)
        self.record_status.setText("正在录制：请完成两组前倾—回正。提前结束需至少录满 6 秒。")

    def _recording_progress(self, elapsed, total):
        if self.cleaned:
            return
        self.progress_bar.setMaximum(max(1, total))
        self.progress_bar.setValue(min(elapsed, total))
        self.record_status.setText(f"正在录制… {elapsed / 1000:.1f} / {total / 1000:.1f} 秒")

    def stop_recording(self):
        if self.recorder is not None and not self.cleaned:
            self.stop_button.setEnabled(False)
            self.recorder.stop_recording()

    def _recorder_failed(self, text):
        if self.cleaned:
            return
        self.stop_button.setEnabled(False)
        self.record_status.setText(text)
        self.message.setText("录像未完成。可以重新连接摄像头，或取消返回继续坚持。")

    def _clip_ready(self, path, frames, span_ms):
        if self.cleaned:
            return
        self.clip_path = path
        self.pages.setCurrentIndex(PAGE_RESULT)
        self.stop_button.setEnabled(False)
        self.result_detail.setText("")
        self.thumb.show_image(frames[-1][1] if frames else QImage())
        blocked = check_evidence(len(frames), span_ms, self.clip_ms)
        if blocked is not None:
            self._show_verdict(blocked)
            return
        images = FrameSampler.select_even_images(frames, limit=10)
        encoded = FrameSampler.encode_jpeg(images)
        if not encoded:
            self._show_verdict(failure("录像画面无法编码，请重新录制。"))
            return
        motion = FrameSampler().motion_trace(images)
        prompt = prompt_for(len(encoded), span_ms / 1000)
        self.verifying = True
        self.result_title.setText("正在核验动作…")
        self.result_detail.setText("已抽取 %d 张画面交给所配置的视觉模型判断，请稍候。" % len(encoded))
        self.retry_button.setEnabled(False)
        self._watchdog.start()
        verifier = self.verifier or LiveVerifier(None)
        run_async(lambda: verifier.evaluate(prompt, encoded),
                  lambda answer, error: self._verified(answer, error, motion))

    def _verified(self, answer, error, motion):
        if self.cleaned:
            return
        self._watchdog.stop()
        self.verifying = False
        self.retry_button.setEnabled(True)
        if error is not None:
            message = error.user_message() if isinstance(error, VisionError) else "核验过程出现异常，请稍后重试。"
            self._show_verdict(failure(message))
            return
        if answer is None:
            self._show_verdict(failure("核验没有返回结果，未判定为通过。请重试。"))
            return
        self._show_verdict(decide(answer, motion))

    def _verify_timeout(self):
        if self.cleaned or not self.verifying:
            return
        self.verifying = False
        self.retry_button.setEnabled(True)
        self._show_verdict(failure("核验超时，未判定为通过。请检查网络后重试。"))

    def _show_verdict(self, verdict):
        self.verdict = verdict
        self.result_title.setText(verdict.label())
        if verdict.passed:
            self.result_detail.setText(verdict.reason + "\n确认后本段录像会保存在本机投降档案馆。")
            if self.controller.mark_verified(self.token):
                self.confirm_button.setEnabled(True)
                self.message.setText("动作验证通过。可以确认投降，或重新挑战。")
            else:
                self.confirm_button.setEnabled(False)
                self.message.setText("本轮监督状态已变化，无法确认。")
        else:
            self.result_detail.setText(verdict.reason)
            self.confirm_button.setEnabled(False)
            self.message.setText("未通过不影响重试：可以无限次重新录制。" if not verdict.technical
                                 else "这是技术性失败，不计为通过。请检查配置或网络后重试。")

    def retry(self):
        if self.cleaned:
            return
        self.controller.retake(self.token)
        if self.recorder is not None:
            self.recorder.cleanup_file()
        self.clip_path, self.verdict = None, None
        self.confirm_button.setEnabled(False)
        self.pages.setCurrentIndex(PAGE_RECORD)
        self.begin_recording()

    def confirm(self):
        if self.submitting or self.verdict is None or not self.verdict.passed:
            return
        if not self.controller.valid(self.token):
            return
        self.submitting = True
        self.confirm_button.setEnabled(False)
        self.confirm_requested.emit(self.token, self.clip_path or "", self.verdict)

    # --- teardown ------------------------------------------------------
    def stop_guide(self):
        if self.guide is not None:
            guide, self.guide = self.guide, None
            guide.close()
        self.guide_view.show_image(QImage())

    def cleanup(self):
        if self.cleaned:
            return
        self.cleaned = True
        self._watchdog.stop()
        self.stop_guide()
        if self.recorder is not None:
            self.recorder.stop()
            self.recorder.deleteLater()
            self.recorder = None
        # A clip that was never confirmed must not linger in the temp folder.
        if self.clip_path:
            try:
                Path(self.clip_path).unlink(missing_ok=True)
            except OSError:
                pass
            self.clip_path = None
        self.declaration.clear()
        self.preview.show_image(QImage())
        self.thumb.show_image(QImage())
