# -*- coding: utf-8 -*-

# NNMN.py v1.1.0

import sys
import os
import datetime
import shutil
import traceback
import threading
import json
import ctypes
import time
import platform
import base64
from io import BytesIO

try:
    import resources_rc
except ImportError:
    print("警告: リソースファイルが見つかりません。アイコンが表示されない可能性があります。")

try:
    from pynput import keyboard
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False
    print("警告: pynput ライブラリが見つかりません。システムワイドホットキー機能は無効になります。")
    print("インストールするには、コマンドプロンプトで 'pip install pynput' を実行してください。")

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QSplitter, QTreeView, QTextEdit, QStatusBar, QLabel,
    QLineEdit, QMenu, QMessageBox, QInputDialog, QPushButton, QTabBar,
    QSizePolicy, QSpacerItem, QDialog, QFormLayout, QDialogButtonBox,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt6.QtGui import (
    QAction, QKeySequence, QShortcut, QFont, QPalette, QColor, QTextCursor,
    QPainter, QTextFormat, QActionGroup, QFileSystemModel, QIcon,
    QFontMetrics, QInputMethodEvent, QTextCharFormat, QPixmap
)
from PyQt6.QtCore import (
    Qt, QDir, QModelIndex, QTimer, QSettings, QPoint,
    QSize, QRect, pyqtSignal, QObject, QEvent, QMetaObject,
    QSharedMemory, QStandardPaths
)
try:
    from PyQt6.QtNetwork import QLocalServer, QLocalSocket
    QTNETWORK_AVAILABLE = True
except ImportError:
    QTNETWORK_AVAILABLE = False
    print("警告: PyQt6.QtNetwork モジュールが見つかりません。単一インスタンス機能は無効になります。")


# --- 設定 ---
APP_NAME = "NekoNyanMemoNote"
APP_VERSION = "v1.1.0"

# リソースファイル（アイコンなど）の場所を決定
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    # PyInstaller で onefile モードの場合
    RESOURCE_DIR = sys._MEIPASS
    print(f"DEBUG: Running as frozen (onefile). RESOURCE_DIR: {RESOURCE_DIR}")
elif getattr(sys, 'frozen', False):
    # PyInstaller で onedir モードの場合
    RESOURCE_DIR = os.path.dirname(sys.executable)
    print(f"DEBUG: Running as frozen (onedir). RESOURCE_DIR: {RESOURCE_DIR}")
else:
    # 通常のPythonスクリプトとして実行されている場合
    RESOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
    print(f"DEBUG: Running as script. RESOURCE_DIR: {RESOURCE_DIR}")

# ユーザーデータ（PyMemoNoteData）の場所を決定
if getattr(sys, 'frozen', False):
    # PyInstallerなどで実行ファイル化されている場合
    APP_DATA_BASE_DIR = os.path.dirname(sys.executable)
    print(f"DEBUG: APP_DATA_BASE_DIR (frozen): {APP_DATA_BASE_DIR}")
else:
    # 通常のPythonスクリプトとして実行されている場合
    APP_DATA_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    print(f"DEBUG: APP_DATA_BASE_DIR (script): {APP_DATA_BASE_DIR}")
BASE_MEMO_DIR = os.path.join(APP_DATA_BASE_DIR, "PyMemoNoteData")
PLUS_TAB_PROPERTY = "_is_plus_tab"
DEFAULT_FONT_SIZE = 10
PREEDIT_PROPERTY_ID = QTextFormat.Property.UserProperty + 1
UNIQUE_KEY = f"{APP_NAME}_Instance_{os.path.expanduser('~')}"
# ----------------

# --- 行番号表示用ウィジェット (変更なし) ---
class LineNumberArea(QWidget):
    def __init__(self, editor): super().__init__(editor); self.codeEditor = editor
    def sizeHint(self): return QSize(self.line_number_area_width(), 0)
    def line_number_area_width(self):
        digits = 1; doc = self.codeEditor.document()
        if not doc: return 30
        font_metrics = self.fontMetrics() if self.font() else self.codeEditor.fontMetrics()
        max_num = max(1, doc.blockCount())
        while max_num >= 10: max_num //= 10; digits += 1
        space = 5 + font_metrics.horizontalAdvance('9') * digits + 5
        return space
    def update_width(self): self.codeEditor.setViewportMargins(self.line_number_area_width(), 0, 0, 0)
    def paintEvent(self, event): self.codeEditor.line_number_area_paint_event(event)
    def set_font(self, font):
        self.setFont(font)
        self.update_width()

# --- 行番号付きテキストエディタ ---
class MemoTextEdit(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent); self.lineNumberArea = LineNumberArea(self); self.current_file_path = None
        self.document().blockCountChanged.connect(self.update_line_number_area_width)
        self.verticalScrollBar().valueChanged.connect(self.lineNumberArea.update)
        self.cursorPositionChanged.connect(self.highlight_current_line)
        self.cursorPositionChanged.connect(self.lineNumberArea.update)
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.update_line_number_area_width(0); self.highlight_current_line()
        self.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)

    # ★★★ 追加: プレーンテキストでのペースト処理 ★★★
    def insertFromMimeData(self, source):
        if source.hasText():
            self.insertPlainText(source.text())
        # else:
        #     super().insertFromMimeData(source) # 他のMIMEタイプを扱う場合はコメント解除

    def line_number_area_paint_event(self, event):
        painter = QPainter(self.lineNumberArea)
        bg_color = self.palette().color(QPalette.ColorRole.Base)
        painter.fillRect(event.rect(), bg_color)
        first_visible_cursor = self.cursorForPosition(QPoint(0, 0))
        block = first_visible_cursor.block()
        if not block.isValid(): return
        blockNumber = block.blockNumber(); offset = QPoint(self.horizontalScrollBar().value(), self.verticalScrollBar().value())
        top = self.document().documentLayout().blockBoundingRect(block).translated(-offset.x(), -offset.y()).top()
        bottom = top + self.document().documentLayout().blockBoundingRect(block).height()
        width = self.lineNumberArea.width(); height = self.fontMetrics().height()
        painter.setFont(self.lineNumberArea.font())
        default_pen_color = self.palette().color(QPalette.ColorRole.Text)
        current_line_pen_color = QColor(Qt.GlobalColor.blue)
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(blockNumber + 1); is_current_line = self.textCursor().blockNumber() == blockNumber
                pen_color = current_line_pen_color if is_current_line else default_pen_color
                painter.setPen(pen_color); painter.drawText(0, int(top), width - 5, height, Qt.AlignmentFlag.AlignRight, number)
            block = block.next()
            if block.isValid(): top = bottom; bottom = top + self.document().documentLayout().blockBoundingRect(block).height()
            blockNumber += 1
    def resizeEvent(self, event): super().resizeEvent(event); cr = self.contentsRect(); self.lineNumberArea.setGeometry(QRect(cr.left(), cr.top(), self.lineNumberArea.line_number_area_width(), cr.height()))
    def update_line_number_area_width(self, _=0): self.lineNumberArea.update_width(); self.lineNumberArea.update()
    def highlight_current_line(self):
        extraSelections = self.extraSelections()
        # 現在行ハイライト以外の ExtraSelection (IME未確定文字列など) は保持する
        extraSelections = [sel for sel in extraSelections if sel.format.property(QTextFormat.Property.FullWidthSelection) != True]
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            lineColor = QColor("#E8F0FF") # 現在行の背景色
            selection.format.setBackground(lineColor); selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            selection.cursor = self.textCursor(); selection.cursor.clearSelection()
            extraSelections.append(selection)
        self.setExtraSelections(extraSelections); self.lineNumberArea.update()
    def set_font_size(self, size):
        font = self.font(); font.setPointSize(size); self.setFont(font)
        self.lineNumberArea.set_font(font); self.update_line_number_area_width()

    def inputMethodEvent(self, event: QInputMethodEvent):
        try:
            current_extra_selections = self.extraSelections()
            # 以前の未確定文字列の選択 (PREEDIT_PROPERTY_IDを持つもの) をクリア
            non_preedit_selections = [sel for sel in current_extra_selections if sel.format.property(PREEDIT_PROPERTY_ID) != True]

            # デフォルトの inputMethodEvent を呼び出す
            super().inputMethodEvent(event)

            new_preedit_selections = []
            if event.preeditString():
                # 未確定文字列がある場合、その範囲を示す ExtraSelection を作成 (スタイルは適用しない)
                current_cursor_pos = self.textCursor().position()
                preedit_text = event.preeditString()
                preedit_len = len(preedit_text)
                preedit_start_pos = current_cursor_pos - preedit_len

                for attr in event.attributes():
                    if attr.type == QInputMethodEvent.AttributeType.TextFormat:
                        selection = QTextEdit.ExtraSelection()
                        selection.cursor = QTextCursor(self.document())

                        start = preedit_start_pos + attr.start
                        end = start + attr.length
                        doc_len = self.document().characterCount() - 1

                        if start < 0 or start > doc_len or end < start or end > doc_len + 1:
                            print(f"WARN: Invalid IME attr range: start={start}, len={attr.length}, doc_len={doc_len}")
                            continue

                        selection.cursor.setPosition(start)
                        selection.cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)

                        fmt = QTextCharFormat()
                        fmt.setProperty(PREEDIT_PROPERTY_ID, True) # 識別用プロパティ
                        selection.format = fmt
                        new_preedit_selections.append(selection)

            final_selections = non_preedit_selections + new_preedit_selections
            self.setExtraSelections(final_selections)

        except Exception as e:
            print(f"--- Error in inputMethodEvent ---")
            print(f"Preedit: '{event.preeditString()}', Commit: '{event.commitString()}'")
            print(traceback.format_exc())

    def focusOutEvent(self, event):
        try:
            extraSelections = self.extraSelections()
            extraSelections = [sel for sel in extraSelections if sel.format.property(PREEDIT_PROPERTY_ID) != True]
            self.setExtraSelections(extraSelections)
        except Exception as e:
            print(f"--- Error in focusOutEvent ---")
            print(traceback.format_exc())
        finally:
            super().focusOutEvent(event)

# --- 読み取り専用ファイル用ファイルシステムモデル (変更なし) ---
class ReadOnlyFileSystemModel(QFileSystemModel):
    def __init__(self, read_only_set, parent=None):
        super().__init__(parent); self.read_only_files = {os.path.normcase(os.path.abspath(p)) for p in read_only_set}
    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        value = super().data(index, role)
        if role == Qt.ItemDataRole.FontRole and not self.isDir(index):
            file_path = os.path.normcase(os.path.abspath(self.filePath(index)))
            if file_path in self.read_only_files:
                font = QFont()
                if isinstance(value, QFont): font = value
                font.setBold(True); return font
        return value
    def update_item(self, file_path):
        norm_path = os.path.normcase(os.path.abspath(file_path)); index = self.index(norm_path); index_orig = self.index(file_path)
        if index_orig.isValid(): self.dataChanged.emit(index_orig, index_orig, [Qt.ItemDataRole.FontRole])
        elif index.isValid(): self.dataChanged.emit(index, index, [Qt.ItemDataRole.FontRole])

# --- カスタム QTreeView クラス (変更なし) ---
class CustomTreeView(QTreeView):
    emptyAreaDoubleClicked = pyqtSignal()
    def mouseDoubleClickEvent(self, event):
        index = self.indexAt(event.pos())
        if not index.isValid() and event.button() == Qt.MouseButton.LeftButton: print("CustomTreeView: 空白領域ダブルクリック検知、シグナル発行"); self.emptyAreaDoubleClicked.emit()
        else: super().mouseDoubleClickEvent(event)

# --- CustomTabBar クラス (変更なし) ---
class CustomTabBar(QTabBar):
    plusTabClicked = pyqtSignal()
    def wheelEvent(self, event):
        delta = event.angleDelta().y(); tab_widget = self.parentWidget()
        if isinstance(tab_widget, QTabWidget):
            count = tab_widget.count(); plus_tab_index = -1
            for i in range(count):
                widget = tab_widget.widget(i)
                if widget and widget.property(PLUS_TAB_PROPERTY): plus_tab_index = i; break
            scrollable_count = count - 1 if plus_tab_index != -1 else count
            if scrollable_count <= 1: event.accept(); return
            current_index = tab_widget.currentIndex(); next_index = current_index
            if delta > 0: next_index = current_index - 1
            elif delta < 0: next_index = current_index + 1
            else: event.accept(); return
            if next_index < 0: next_index = scrollable_count - 1
            elif next_index >= scrollable_count: next_index = 0
            if plus_tab_index == -1 or next_index < plus_tab_index: tab_widget.setCurrentIndex(next_index)
        event.accept()
    def mousePressEvent(self, event):
        pos = event.pos(); index = self.tabAt(pos)
        if index != -1:
            tab_widget = self.parentWidget()
            if isinstance(tab_widget, QTabWidget):
                widget = tab_widget.widget(index)
                if widget and widget.property(PLUS_TAB_PROPERTY):
                    if event.button() == Qt.MouseButton.LeftButton: print("+タブがクリックされました。plusTabClickedシグナルを発行します。"); self.plusTabClicked.emit(); event.accept(); return
        super().mousePressEvent(event)

# --- メインアプリケーションウィンドウ ---
class MemoApp(QMainWindow):
    toggle_visibility_signal = pyqtSignal()
    def __init__(self):
        super().__init__()
        self.read_only_files = set()
        self.ignore_save = False
        self.settings = QSettings("MechaGodeh", APP_NAME)
        print(f"DEBUG: QSettings file path: {self.settings.fileName()}")
        self._last_selected_normal_tab_index = 0
        self.hotkey_listener = None
        self.hotkey_thread = None
        self.last_opened_files = {}
        self.current_font_size = DEFAULT_FONT_SIZE
        self.current_tab_order = []
        self.local_server = None
        self.last_hotkey_press_time = 0
        self.hotkey_debounce_time = 0.3

        # 自動入力テキストの設定を読み込む
        self.auto_texts = self.settings.value("autoTexts", [
            "こんにちは", "ありがとう", "お疲れ様です", "よろしくお願いします",
            "承知しました", "了解しました", "確認しました", "検討します",
            "後ほど", "失礼します"
        ], type=list)

        # 自動入力メニュー表示状態の管理
        self.auto_text_menu_visible = False
        self.auto_text_menu = None

        print(f"DEBUG: Final BASE_MEMO_DIR: {BASE_MEMO_DIR}")
        if not os.path.exists(BASE_MEMO_DIR):
            try:
                os.makedirs(BASE_MEMO_DIR)
                print(f"DEBUG: Created base memo directory: {BASE_MEMO_DIR}")
            except OSError as e:
                error_msg = f"ベースディレクトリを作成できませんでした: {e}\n{BASE_MEMO_DIR}\n\n{traceback.format_exc()}"
                print(f"!!! CRITICAL ERROR: {error_msg}")
                QMessageBox.critical(self, "致命的なエラー", error_msg)
                sys.exit(1)
        self.init_ui()
        self.load_settings()
        self.apply_font_size_to_all_editors()
        self.toggle_visibility_signal.connect(self._safe_toggle_window_visibility)
        if PYNPUT_AVAILABLE:
            os_name = platform.system()
            if os_name == "Darwin": print("macOS detected. Ensure accessibility permissions are granted for input monitoring.")
            elif os_name == "Linux": print("Linux detected. Input monitoring might require special permissions (e.g., root or input group).")
            self.start_hotkey_listener_global()
        else: QMessageBox.warning(self, "警告", "pynputライブラリが見つからないため、\nシステムワイドホットキー機能は利用できません。")
        self.insert_date_shortcut = QShortcut(QKeySequence("Ctrl+D"), self); self.insert_date_shortcut.activated.connect(self.insert_date)
        self.date_timer = QTimer(self); self.date_timer.timeout.connect(self.update_footer_date); self.date_timer.start(60000); self.update_footer_status()

    def init_ui(self):
        # ★★★ 追加: Windows APIによる前面表示処理 ★★★
        # (メソッド定義はクラス内であればどこでも良いが、関連する処理の近くに配置)
        if platform.system() == "Windows":
            def bring_to_front_windows_impl(self_ptr):
                try:
                    hwnd = self_ptr.winId()
                    if hwnd: # hwnd が None や 0 でないことを確認
                        # QTimer.singleShot を使って SetForegroundWindow の呼び出しを遅延させる
                        def deferred_set_foreground():
                            try:
                                hwnd_int = int(hwnd) # API呼び出し用に整数に変換
                                print(f"    Windows API (deferred): Attempting SetForegroundWindow for HWND {hwnd_int}")
                                # 呼び出し前にウィンドウが表示されているか確認 (デバッグ用)
                                # is_really_visible = ctypes.windll.user32.IsWindowVisible(hwnd_int)
                                # print(f"    Windows API (deferred): IsWindowVisible before SetForegroundWindow: {is_really_visible}")

                                success = ctypes.windll.user32.SetForegroundWindow(hwnd_int)
                                print(f"    Windows API (deferred): SetForegroundWindow called for HWND {hwnd_int}. Success: {success != 0}")
                                if not success:
                                     last_error = ctypes.windll.kernel32.GetLastError()
                                     print(f"    Windows API (deferred): SetForegroundWindow (1st attempt) failed. GetLastError: {last_error}")
                                     # ★★★ 修正: SetForegroundWindow失敗時のリカバリー処理 ★★★
                                     if last_error == 0: # 特にGetLastErrorが0の場合、より積極的な手段を試す
                                        print(f"    Windows API (deferred): Attempting minimize-restore-activate sequence for HWND {hwnd_int}")
                                        self_ptr.showMinimized()
                                        # QTimerを使ってシーケンスを分割実行
                                        def _restore_and_activate():
                                            print(f"    Windows API (deferred-restore): Restoring and attempting SetForegroundWindow again for HWND {hwnd_int}")
                                            self_ptr.showNormal() # 通常表示に戻す
                                            self_ptr.raise_()     # 最前面に
                                            # QApplication.processEvents() # Qtイベント処理を一度実行 (必要に応じて)
                                            
                                            success_retry = ctypes.windll.user32.SetForegroundWindow(hwnd_int)
                                            print(f"    Windows API (deferred-restore): SetForegroundWindow (2nd attempt) called. Success: {success_retry != 0}")
                                            if not success_retry:
                                                last_error_retry = ctypes.windll.kernel32.GetLastError()
                                                print(f"    Windows API (deferred-restore): SetForegroundWindow (2nd attempt) failed. GetLastError: {last_error_retry}")

                                            # Qtレベルでもアクティブでなければ再試行
                                            if not self_ptr.isActiveWindow():
                                                print(f"    Windows API (deferred-restore): Window still not active by Qt, trying Qt activation methods.")
                                                QApplication.setActiveWindow(self_ptr)
                                                self_ptr.activateWindow()
                                                print(f"    Windows API (deferred-restore): After re-activating with Qt: isActiveWindow() = {self_ptr.isActiveWindow()}")
                                        QTimer.singleShot(100, _restore_and_activate) # 100ms後に復元と再アクティブ化
                                        return # この後の処理は _restore_and_activate に任せる
                                # ★★★ ここまで修正 ★★★

                                # SetForegroundWindowが成功したか、上記リカバリー以外の場合のQtレベルのアクティブ化
                                if success and not self_ptr.isActiveWindow(): # API成功でもQtが非アクティブなら
                                    print(f"    Windows API (deferred): API success but Qt not active. Trying Qt activation.")
                                    QApplication.setActiveWindow(self_ptr); self_ptr.activateWindow()
                                    print(f"    Windows API (deferred): After Qt re-activation: isActiveWindow() = {self_ptr.isActiveWindow()}")

                            except Exception as e_deferred_api:
                                print(f"    Windows API (deferred): Error in deferred_set_foreground: {e_deferred_api}")
                                traceback.print_exc()

                        QTimer.singleShot(50, deferred_set_foreground) # 50ミリ秒後に実行
                        print(f"    Windows API: SetForegroundWindow call scheduled for HWND {int(hwnd)}")
                    else:
                        print(f"    Windows API: HWND is None or 0, cannot call SetForegroundWindow.")
                except Exception as e_api:
                    print(f"    Windows API: Error in bring_to_front_windows: {e_api}")
                    traceback.print_exc()
            self.bring_to_front_windows = lambda: bring_to_front_windows_impl(self)
        self.setWindowTitle(f"{APP_NAME} - {APP_VERSION}"); self.setGeometry(100, 100, 900, 700)
        # アイコンパスの決定 (RESOURCE_DIR を使用)
        # .spec ファイルで favicon.ico が RESOURCE_DIR のルートにコピーされる想定
        icon_filename = "favicon.ico"
        icon_path = os.path.join(RESOURCE_DIR, icon_filename)
        print(f"DEBUG: Final icon_path for window: {icon_path}")
        if os.path.exists(icon_path):
            try:
                self.setWindowIcon(QIcon(icon_path))
                print(f"ウィンドウアイコンを設定しました: {icon_path}")
            except Exception as e:
                error_msg = f"アイコンの設定中にエラーが発生しました。\n{icon_path}\n{e}\n\n{traceback.format_exc()}"
                print(f"!!! WARNING: {error_msg}")
                QMessageBox.warning(self, "警告", error_msg)
        else:
            print(f"警告: アイコンファイルが見つかりません: {icon_path}")
        main_widget = QWidget(); self.setCentralWidget(main_widget); main_layout = QVBoxLayout(main_widget); main_layout.setContentsMargins(5, 5, 5, 5); main_layout.setSpacing(5)
        self.tab_widget = QTabWidget(); custom_tab_bar = CustomTabBar(); self.tab_widget.setTabBar(custom_tab_bar)
        self.tab_widget.tabBar().setMovable(True); self.tab_widget.tabBar().tabMoved.connect(self.save_tab_order)
        self.tab_widget.setTabsClosable(False); self.tab_widget.currentChanged.connect(self.on_tab_changed)
        tab_bar = self.tab_widget.tabBar(); tab_bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu); tab_bar.customContextMenuRequested.connect(self.show_tab_context_menu)
        self.tab_widget.tabBarDoubleClicked.connect(self.on_tab_double_clicked); custom_tab_bar.plusTabClicked.connect(lambda: self.create_new_folder(use_default_on_empty=True, select_new_tab=True))
        main_layout.addWidget(self.tab_widget)
        self.status_bar = QStatusBar(); self.setStatusBar(self.status_bar)
        self.status_label_date = QLabel(); self.update_footer_date(); self.status_bar.addWidget(self.status_label_date)
        self.status_label_wrap = QLabel("折り返し: ウィンドウ幅"); self.status_bar.addWidget(self.status_label_wrap)
        self.status_label_cursor = QLabel("カーソル: -"); self.status_bar.addWidget(self.status_label_cursor)
        self.status_label_chars = QLabel("文字数: -"); self.status_bar.addWidget(self.status_label_chars)
        spacer = QWidget(); spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred); self.status_bar.addWidget(spacer)
        font_size_widget = QWidget(); font_size_layout = QHBoxLayout(font_size_widget); font_size_layout.setContentsMargins(0, 0, 0, 0); font_size_layout.setSpacing(2)
        font_decrease_button = QPushButton("-"); font_decrease_button.setFixedSize(20, 20); font_decrease_button.setToolTip("文字サイズを小さくする"); font_decrease_button.clicked.connect(self.decrease_font_size); font_size_layout.addWidget(font_decrease_button)
        self.font_size_label = QLabel(f"{self.current_font_size}pt"); self.font_size_label.setToolTip("現在の文字サイズ"); font_size_layout.addWidget(self.font_size_label)
        font_increase_button = QPushButton("+"); font_increase_button.setFixedSize(20, 20); font_increase_button.setToolTip("文字サイズを大きくする"); font_increase_button.clicked.connect(self.increase_font_size); font_size_layout.addWidget(font_increase_button)
        self.status_bar.addPermanentWidget(font_size_widget)
        wrap_menu = QMenu("折り返し", self); wrap_group = QActionGroup(self); wrap_group.setExclusive(True)
        no_wrap_action = QAction("折り返さない", self, checkable=True); no_wrap_action.triggered.connect(lambda: self.set_current_editor_wrap_mode(QTextEdit.LineWrapMode.NoWrap)); wrap_group.addAction(no_wrap_action); wrap_menu.addAction(no_wrap_action)
        char_wrap_action = QAction("72文字(目安)で折り返す", self, checkable=True); char_wrap_action.triggered.connect(lambda: self.set_current_editor_wrap_mode(QTextEdit.LineWrapMode.FixedPixelWidth, 72)); wrap_group.addAction(char_wrap_action); wrap_menu.addAction(char_wrap_action)
        window_wrap_action = QAction("ウィンドウ幅で折り返す", self, checkable=True); window_wrap_action.triggered.connect(lambda: self.set_current_editor_wrap_mode(QTextEdit.LineWrapMode.WidgetWidth)); wrap_group.addAction(window_wrap_action); wrap_menu.addAction(window_wrap_action)
        window_wrap_action.setChecked(True); wrap_button = QPushButton("折り返し設定"); wrap_button.setObjectName("wrap_button"); wrap_button.setMenu(wrap_menu); self.status_bar.addPermanentWidget(wrap_button)

        # 歯車アイコンを追加
        settings_button = QPushButton("自動挿入")
        settings_button.setToolTip("自動入力テキスト設定")
        settings_button.clicked.connect(self.show_auto_text_settings)
        self.status_bar.addPermanentWidget(settings_button)

        # Ctrl+W ショートカットを追加
        self.auto_text_shortcut = QShortcut(QKeySequence("Ctrl+W"), self)
        self.auto_text_shortcut.activated.connect(self.show_auto_text_menu)

        # 数字キーのショートカットを追加（通常キーとテンキーの両方に対応）
        # for i in range(10):
        #     # 通常の数字キー
        #     shortcut = QShortcut(QKeySequence(str(i)), self)
        #     shortcut.activated.connect(lambda checked, idx=i: self.handle_number_key(idx))
        #     # テンキー
        #     numpad_shortcut = QShortcut(QKeySequence(f"Keypad{i}"), self)
        #     numpad_shortcut.activated.connect(lambda checked, idx=i: self.handle_number_key(idx))

        self.installEventFilter(self)

    def eventFilter(self, obj, event):
        if self.auto_text_menu_visible and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            print(f"DEBUG: Key press in eventFilter: {key}")  # デバッグ用
            # 通常数字キー
            if Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
                number = key - Qt.Key.Key_0
                print(f"DEBUG: Regular number key pressed: {number}")  # デバッグ用
                # 1-9,0の順で対応
                if number == 0:
                    self.insert_auto_text(9)
                else:
                    self.insert_auto_text(number - 1)
                return True  # イベントを消費
            # テンキー
            elif Qt.KeypadModifier & event.modifiers() and Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
                number = key - Qt.Key.Key_0
                print(f"DEBUG: Numpad key pressed: {number}")  # デバッグ用
                # 1-9,0の順で対応
                if number == 0:
                    self.insert_auto_text(9)
                else:
                    self.insert_auto_text(number - 1)
                return True  # イベントを消費
        return super().eventFilter(obj, event)

    def get_current_widgets(self, index=None):
        target_index = index if index is not None else self.tab_widget.currentIndex()
        if target_index < 0 or target_index >= self.tab_widget.count(): return None, None, None, None
        widget = self.tab_widget.widget(target_index)
        if isinstance(widget, QSplitter) and widget.count() == 2:
            tree_widget_container = widget.widget(0); editor = widget.widget(1)
            if tree_widget_container:
                tree = tree_widget_container.findChild(CustomTreeView)
                if tree and isinstance(editor, MemoTextEdit):
                    model = tree.model()
                    if isinstance(model, QFileSystemModel): return widget, model, tree, editor
        return None, None, None, None
    def closeEvent(self, event):
        print("Closing application..."); self.update_last_opened_file_for_current_tab(); self.save_current_memo(); self.save_settings()
        if self.hotkey_listener:
            print("Stopping hotkey listener...")
            try: self.hotkey_listener.stop()
            except Exception as e: print(f"Error stopping hotkey listener: {e}"); traceback.print_exc()
            finally:
                if self.hotkey_thread and self.hotkey_thread.is_alive(): self.hotkey_thread.join(timeout=0.5)
                print("Hotkey listener stopped.")
        if self.local_server: print("Closing local server..."); self.local_server.close()
        if 'shared_memory' in globals() and shared_memory.isAttached(): shared_memory.detach(); print("Local server closed.")
        event.accept(); print("Application closed.")
    def load_settings(self):
        try:
            print("Loading settings..."); geometry = self.settings.value("geometry")
            if geometry: self.restoreGeometry(geometry)
            state = self.settings.value("windowState")
            if state: self.restoreState(state)
            self.current_font_size = self.settings.value("fontSize", DEFAULT_FONT_SIZE, type=int); self.font_size_label.setText(f"{self.current_font_size}pt")
            read_only_paths = self.settings.value("readOnlyFiles", "", type=str); self.read_only_files = {os.path.normcase(os.path.abspath(p)) for p in filter(None, read_only_paths.split('||'))}
            print(f"Loaded {len(self.read_only_files)} read-only files.")
            last_opened_json = self.settings.value("lastOpenedFiles", "{}", type=str)
            try: loaded_files = json.loads(last_opened_json); self.last_opened_files = {os.path.normcase(os.path.abspath(k)): os.path.normcase(os.path.abspath(v)) for k, v in loaded_files.items()}; print(f"Loaded {len(self.last_opened_files)} last opened file entries.")
            except json.JSONDecodeError as e: print(f"警告: 最後に開いていたファイルのリストを読み込めませんでした: {e}"); self.last_opened_files = {}
            tab_order_json = self.settings.value("tabOrder", "[]", type=str)
            try: saved_tab_order = json.loads(tab_order_json); self.saved_tab_order = [os.path.normcase(os.path.abspath(p)) for p in saved_tab_order]; print(f"Loaded tab order with {len(self.saved_tab_order)} entries.")
            except json.JSONDecodeError as e: print(f"警告: タブの順序を読み込めませんでした: {e}"); self.saved_tab_order = []
            self.load_folders(); last_tab_index = self.settings.value("lastTabIndex", 0, type=int); plus_tab_idx = self._find_plus_tab_index()
            valid_last_index = last_tab_index if plus_tab_idx == -1 or last_tab_index != plus_tab_idx else 0
            num_normal_tabs = self.tab_widget.count() - (1 if plus_tab_idx != -1 else 0); target_index = -1
            if 0 <= valid_last_index < num_normal_tabs: target_index = valid_last_index
            elif num_normal_tabs > 0: target_index = 0
            if target_index != -1: print(f"Setting initial tab index to: {target_index}"); self.tab_widget.setCurrentIndex(target_index)
            else: print("No normal tabs found to select.")
            print("Settings loaded.")
        except Exception as e:
            error_message = f"設定の読み込み中に予期せぬエラーが発生しました:\n{traceback.format_exc()}"
            print(f"!!! CRITICAL ERROR: {error_message}")
            QMessageBox.critical(self, "致命的なエラー", error_message)
    def save_settings(self):
        try:
            print("Saving settings..."); self.settings.setValue("geometry", self.saveGeometry()); self.settings.setValue("windowState", self.saveState())
            self.settings.setValue("fontSize", self.current_font_size); self.settings.setValue("readOnlyFiles", "||".join(self.read_only_files))
            try: last_opened_json = json.dumps(self.last_opened_files); self.settings.setValue("lastOpenedFiles", last_opened_json); print(f"Saved {len(self.last_opened_files)} last opened file entries.")
            except Exception as e: print(f"エラー: 最後に開いていたファイルの保存に失敗しました: {e}")
            self.save_tab_order()
            try: tab_order_json = json.dumps(self.current_tab_order); self.settings.setValue("tabOrder", tab_order_json); print(f"Saved tab order with {len(self.current_tab_order)} entries.")
            except Exception as e: print(f"エラー: タブ順序の保存に失敗しました: {e}")
            current_index = self.tab_widget.currentIndex(); widget = self.tab_widget.widget(current_index) if 0 <= current_index < self.tab_widget.count() else None
            if widget and widget.property(PLUS_TAB_PROPERTY): self.settings.setValue("lastTabIndex", self._last_selected_normal_tab_index); print(f"Saved last tab index (was plus tab): {self._last_selected_normal_tab_index}")
            elif current_index >= 0: self.settings.setValue("lastTabIndex", current_index); print(f"Saved last tab index: {current_index}")
            else: self.settings.setValue("lastTabIndex", 0); print("Saved last tab index: 0 (invalid index)")
            _, _, _, editor = self.get_current_widgets()
            if editor: self.settings.setValue("wrapMode", editor.lineWrapMode().value)
            if editor and editor.lineWrapMode() == QTextEdit.LineWrapMode.FixedPixelWidth: self.settings.setValue("wrapColumn", 72)
            elif editor: self.settings.setValue("wrapColumn", editor.lineWrapColumnOrWidth())
            print("Settings saved.")
        except Exception as e:
            error_message = f"設定の保存中に予期せぬエラーが発生しました:\n{traceback.format_exc()}"
            print(f"!!! WARNING: {error_message}")
            QMessageBox.warning(self, "エラー", error_message)
    def _safe_toggle_window_visibility(self): print(">>> _safe_toggle_window_visibility called (received signal)"); self.toggle_window_visibility(); print("<<< _safe_toggle_window_visibility finished")

    # ★★★ 修正: ウィンドウ表示/非表示ロジック変更 ★★★
    def toggle_window_visibility(self):
        is_visible = self.isVisible()
        is_minimized = self.isMinimized()
        is_active = self.isActiveWindow()
        current_state_desc = f"isVisible: {is_visible}, isMinimized: {is_minimized}, isActive: {is_active}, windowState: {self.windowState()}"
        print(f"--- toggle_window_visibility called --- Current state: {current_state_desc}")

        activated_by_qt = False
        if self.windowState() & Qt.WindowState.WindowMinimized: # 最小化されている場合
            print("    Action: Window is minimized. Restoring, raising and activating.")
            self.showNormal()
            self.raise_()
            self.activateWindow()
            QApplication.setActiveWindow(self)
            activated_by_qt = self.isActiveWindow()
            if platform.system() == "Windows" and hasattr(self, 'bring_to_front_windows') and not activated_by_qt:
                self.bring_to_front_windows()
        elif not is_visible: # 非表示の場合 (showMinimized() 以外で隠された場合など)
            print("    Action: Window is not visible. Showing, raising and activating.")
            self.showNormal()
            self.raise_()
            self.activateWindow()
            QApplication.setActiveWindow(self)
            activated_by_qt = self.isActiveWindow()
            if platform.system() == "Windows" and hasattr(self, 'bring_to_front_windows') and not activated_by_qt:
                self.bring_to_front_windows()
        elif not is_active: # 表示されているがアクティブではない場合
            print("    Action: Window is visible but not active. Showing normal, raising and activating.")
            self.setWindowState(Qt.WindowState.WindowNoState) # ★★★ 追加: ウィンドウ状態を一度リセット ★★★
            self.showNormal() # 状態を確実に通常に戻す
            self.raise_()
            print(f"    DEBUG: Before activateWindow: isActiveWindow() = {self.isActiveWindow()}")
            self.activateWindow()
            print(f"    DEBUG: After activateWindow, before QApplication.setActiveWindow: isActiveWindow() = {self.isActiveWindow()}")
            QApplication.setActiveWindow(self)
            print(f"    DEBUG: After QApplication.setActiveWindow: isActiveWindow() = {self.isActiveWindow()}")
            activated_by_qt = self.isActiveWindow()
            if platform.system() == "Windows" and hasattr(self, 'bring_to_front_windows'): # ★★★ 修正: Qtのアクティブ状態に関わらずWindows APIを試す ★★★
                print(f"    DEBUG: Calling bring_to_front_windows (Windows, visible but not active branch). activated_by_qt was: {activated_by_qt}")
                self.bring_to_front_windows()
            print(f"    DEBUG: After bring_to_front_windows (if called): isActiveWindow() = {self.isActiveWindow()}")
        else: # 表示されていてアクティブな場合
            print("    Action: Window is visible and active. Minimizing.")
            self.showMinimized()

        final_state_desc = f"isVisible: {self.isVisible()}, isMinimized: {self.isMinimized()}, isActive: {self.isActiveWindow()}, windowState: {self.windowState()}"
        print(f"--- toggle_window_visibility finished --- Final state: {final_state_desc}")
    def handle_new_connection(self):
        print("Received connection from new instance. Calling activate_window_from_external().")
        socket = self.local_server.nextPendingConnection()
        # ここでソケットからの読み取りや書き込みも可能だが、今回はアクティブ化のみ
        if socket:
            socket.readyRead.connect(lambda: self._handle_socket_ready_read(socket))
            # activate_window_from_external を直接呼ぶか、シグナル経由でも良い
            QTimer.singleShot(0, self.activate_window_from_external)

    def _handle_socket_ready_read(self, socket):
        # 念のためソケットからのデータを読み取る（今回は特に使わない）
        try:
            data = socket.readAll()
            print(f"Received data from socket: {data.data().decode() if data else 'No data'}")
            socket.disconnectFromServer()
        except Exception as e:
            print(f"Error reading from socket: {e}")


    def activate_window_from_external(self):
        print(">>> activate_window_from_external called")
        self.showNormal() # 最小化状態から復元
        self.raise_()     # 他のウィンドウより前面に        
        QApplication.setActiveWindow(self) # ウィンドウをアクティブにする
        print("<<< activate_window_from_external finished")

    def on_tab_changed(self, index):
        print(f"--- on_tab_changed --- new index: {index}, previous index: {self._last_selected_normal_tab_index}"); previous_index = self._last_selected_normal_tab_index
        if index < 0 or index >= self.tab_widget.count(): print("無効なインデックスのため処理をスキップ"); return
        widget = self.tab_widget.widget(index)
        if widget and widget.property(PLUS_TAB_PROPERTY): print("警告: +タブが選択状態になりました。前のタブに戻します。"); QTimer.singleShot(0, lambda idx=self._last_selected_normal_tab_index: self.tab_widget.setCurrentIndex(idx)); return
        if previous_index != index and 0 <= previous_index < self.tab_widget.count():
             prev_widget = self.tab_widget.widget(previous_index)
             if prev_widget and not prev_widget.property(PLUS_TAB_PROPERTY): print(f"タブ切り替え: 前のタブ {previous_index} の内容を保存試行"); self.save_current_memo(index=previous_index); self.update_last_opened_file_for_tab(previous_index)
        print(f"通常のタブ {index} が選択されました。"); self._last_selected_normal_tab_index = index; print(f"新しいタブ {index} の最後に開いていたファイルをロード試行"); self.load_last_opened_file_for_tab(index)
        self.update_footer_status(); self.update_wrap_menu_state(); _, _, _, editor = self.get_current_widgets(index); self.apply_font_size(editor)
        if editor: wrap_mode_val = self.settings.value("wrapMode", QTextEdit.LineWrapMode.WidgetWidth.value, type=int); wrap_mode = QTextEdit.LineWrapMode(wrap_mode_val); wrap_column = self.settings.value("wrapColumn", 72, type=int); self.set_current_editor_wrap_mode(wrap_mode, wrap_column)

    def on_tab_double_clicked(self, index):
        print(f"--- on_tab_double_clicked (シグナル) --- index: {index}")
        widget = self.tab_widget.widget(index)
        if index >= 0 and widget and not widget.property(PLUS_TAB_PROPERTY):
            print(f"既存タブ {index} ダブルクリック (シグナル)。rename_folder を呼び出します。")
            self.rename_folder(index)
        else:
            print(f"+タブ {index} がダブルクリックされましたが、何もしません。")

    def show_tab_context_menu(self, position):
        menu = QMenu(self); tab_bar = self.tab_widget.tabBar(); tab_index = tab_bar.tabAt(position); widget = self.tab_widget.widget(tab_index) if tab_index != -1 else None
        new_folder_action = QAction("新規フォルダを作成", self); new_folder_action.triggered.connect(lambda: self.create_new_folder(use_default_on_empty=True, select_new_tab=True)); menu.addAction(new_folder_action)
        if tab_index != -1 and widget and not widget.property(PLUS_TAB_PROPERTY): menu.addSeparator(); rename_action = QAction("フォルダ名を変更", self); rename_action.triggered.connect(lambda: self.rename_folder(tab_index)); menu.addAction(rename_action); delete_action = QAction("フォルダを削除", self); delete_action.triggered.connect(lambda: self.delete_folder(tab_index)); menu.addAction(delete_action)
        menu.exec(tab_bar.mapToGlobal(position))

    def on_file_tree_double_clicked(self, index):
        print("--- on_file_tree_double_clicked (既存アイテム) ---")
        tree = self.sender()
        if not isinstance(tree, CustomTreeView):
            print("エラー: sender が CustomTreeView ではありません。")
            return
        model = tree.model()
        if not isinstance(model, QFileSystemModel):
            print("エラー: 有効なファイルシステムモデルを取得できませんでした。")
            return

        if index.isValid():
            file_path = model.filePath(index)
            print(f"既存アイテムがダブルクリックされました: {file_path}")
            if not model.isDir(index):
                print("ファイルです。rename_memo を呼び出します。")
                self.rename_memo(index, model)
            else:
                print("ディレクトリです。何もしません（展開/折りたたみ）。")

    def on_file_tree_empty_area_double_clicked(self): print("--- on_file_tree_empty_area_double_clicked ---"); print("空白部分がダブルクリックされました。create_new_memo を呼び出します。"); self.create_new_memo()
    def on_file_selection_changed(self, selected, deselected):
        selection_model = self.sender()
        if not selection_model: return
        splitter, model, tree, editor = self.get_current_widgets()
        if not tree or tree.selectionModel() != selection_model: return
        print("ファイル選択変更: 現在のエディタ内容を保存試行"); self.save_current_memo(); indexes = selected.indexes()
        if indexes:
            index = indexes[0]
            file_path = model.filePath(index)
            if not model.isDir(index):
                print(f"ファイル選択: {file_path}")
                self.load_memo(file_path)
                self.update_last_opened_file(file_path)
            else:
                print(f"ディレクトリ選択: {file_path}")
                if editor and editor.current_file_path:
                    print("ディレクトリ選択によりエディタをクリア")
                    self.ignore_save = True
                    editor.clear()
                    editor.setReadOnly(True)
                    editor.current_file_path = None
                    self.update_footer_status()
                    self.ignore_save = False
                    self.clear_last_opened_file_for_current_tab()
        else:
            print("選択解除")
            if editor and editor.current_file_path:
                print("選択解除によりエディタをクリア")
                self.ignore_save = True
                editor.clear()
                editor.setReadOnly(True)
                editor.current_file_path = None
                self.update_footer_status()
                self.ignore_save = False
                self.clear_last_opened_file_for_current_tab()

    def show_file_tree_context_menu(self, position):
        splitter, model, tree, editor = self.get_current_widgets()
        if not tree: return
        index = tree.indexAt(position); menu = QMenu(self); new_memo_action = QAction("新規メモを作成", self); new_memo_action.triggered.connect(self.create_new_memo); menu.addAction(new_memo_action)
        if index.isValid():
            file_path = model.filePath(index); is_dir = model.isDir(index)
            if not is_dir: menu.addSeparator(); rename_action = QAction("メモ名を変更", self); rename_action.triggered.connect(lambda checked=False, idx=index, mdl=model: self.rename_memo(idx, mdl)); menu.addAction(rename_action); delete_action = QAction("メモを削除", self); delete_action.triggered.connect(lambda checked=False, idx=index, mdl=model: self.delete_memo(idx, mdl)); menu.addAction(delete_action); menu.addSeparator(); norm_path = os.path.normcase(os.path.abspath(file_path)); read_only_action = QAction("メモを編集不可にする", self, checkable=True); read_only_action.setChecked(norm_path in self.read_only_files); read_only_action.triggered.connect(lambda checked, path=file_path, mdl=model: self.toggle_read_only(path, checked, mdl)); menu.addAction(read_only_action)
        menu.exec(tree.viewport().mapToGlobal(position))
    def get_current_folder_path(self): splitter, _, _, _ = self.get_current_widgets(); return splitter.property("folder_path") if splitter else None
    def create_new_folder(self, default_name="新しいフォルダ", use_default_on_empty=False, select_new_tab=False):
        folder_name, ok = QInputDialog.getText(self, "新しいフォルダ", "フォルダ名を入力してください:", QLineEdit.EchoMode.Normal, default_name)
        if ok:
            input_name = folder_name.strip()
            base_folder_name = default_name if not input_name and use_default_on_empty else input_name if input_name else None
            if not base_folder_name:
                QMessageBox.warning(self, "エラー", "フォルダ名を入力してください。")
                return
            invalid_chars = '\\/:*?"<>|'
            if any(char in base_folder_name for char in invalid_chars):
                QMessageBox.warning(self, "エラー", f"フォルダ名に使用できない文字が含まれています: {invalid_chars}")
                return
            final_folder_name = base_folder_name
            new_folder_path = os.path.join(BASE_MEMO_DIR, final_folder_name)
            counter = 0
            while os.path.exists(new_folder_path):
                counter += 1
                final_folder_name = f"{base_folder_name}_{counter}"
                new_folder_path = os.path.join(BASE_MEMO_DIR, final_folder_name)
            try:
                print(f"DEBUG: Attempting to create folder: {new_folder_path}")
                os.makedirs(new_folder_path)
                print(f"フォルダ作成成功: {new_folder_path}")
                new_tab_index = self.add_folder_tab(final_folder_name, new_folder_path)
                if select_new_tab and new_tab_index is not None:
                    self.tab_widget.setCurrentIndex(new_tab_index)
                    self._last_selected_normal_tab_index = new_tab_index
            except OSError as e:
                error_msg = f"フォルダ '{final_folder_name}' を作成できませんでした: {e}\n\n{traceback.format_exc()}"
                print(f"!!! ERROR: {error_msg}")
                QMessageBox.warning(self, "エラー", error_msg)
            except Exception as e:
                error_message = f"フォルダ作成中に予期せぬエラーが発生しました:\n{traceback.format_exc()}"
                print(f"!!! CRITICAL ERROR: {error_message}")
                QMessageBox.critical(self, "エラー", error_message)

    def create_new_memo(self, default_name="新規メモ"):
        current_folder_path = self.get_current_folder_path()
        if not current_folder_path: QMessageBox.warning(self, "エラー", "メモを作成するフォルダが選択されていません。"); return
        print("create_new_memo: QInputDialog.getText を呼び出します。"); memo_name, ok = QInputDialog.getText(self, "新しいメモ", "メモ名を入力してください (.txt は自動付与):", QLineEdit.EchoMode.Normal, default_name)
        if ok:
            print(f"create_new_memo: ダイアログOK。入力名: '{memo_name}'"); input_name = memo_name.strip(); base_name = input_name if input_name else default_name; invalid_chars = '\\/:*?"<>|'
            if any(char in base_name for char in invalid_chars): QMessageBox.warning(self, "エラー", f"メモ名に使用できない文字が含まれています: {invalid_chars}"); return
            if not base_name.lower().endswith(".txt"): final_file_name_base = base_name; final_file_name = f"{final_file_name_base}.txt"
            else: final_file_name_base = base_name[:-4]; final_file_name = base_name
            new_file_path = os.path.normcase(os.path.abspath(os.path.join(current_folder_path, final_file_name))); counter = 0
            while os.path.exists(new_file_path): counter += 1; final_file_name = f"{final_file_name_base}_{counter}.txt"; new_file_path = os.path.normcase(os.path.abspath(os.path.join(current_folder_path, final_file_name)))
            print(f"create_new_memo: 最終ファイル名: '{final_file_name}'")
            print(f"DEBUG: Attempting to create memo file: {new_file_path}")
            try:
                with open(new_file_path, 'w', encoding='utf-8') as f: f.write("")
                print(f"create_new_memo: ファイル作成成功: '{new_file_path}'")
                _, model, tree, _ = self.get_current_widgets()
                if tree: QTimer.singleShot(200, lambda path=new_file_path, tr=tree: self.select_file_in_tree(path, tr))
            except OSError as e:
                error_msg = f"メモファイル '{final_file_name}' を作成できませんでした: {e}\n\n{traceback.format_exc()}"
                print(f"!!! ERROR: {error_msg}")
                QMessageBox.warning(self, "エラー", error_msg)
            except Exception as e:
                error_message = f"メモファイル作成中に予期せぬエラーが発生しました:\n{traceback.format_exc()}"
                print(f"!!! CRITICAL ERROR: {error_message}")
                QMessageBox.critical(self, "エラー", error_message)
        else: print("create_new_memo: ダイアログキャンセル。")
    def rename_folder(self, tab_index):
        widget = self.tab_widget.widget(tab_index)
        if not widget or widget.property(PLUS_TAB_PROPERTY):
            print(f"タブ {tab_index} はリネームできません (+タブ)")
            return
        old_name = self.tab_widget.tabText(tab_index)
        splitter = widget
        if not isinstance(splitter, QSplitter):
            return
        old_folder_path = os.path.normcase(os.path.abspath(splitter.property("folder_path")))
        new_name, ok = QInputDialog.getText(self, "フォルダ名を変更", "新しいフォルダ名:", QLineEdit.EchoMode.Normal, old_name)
        if ok and new_name.strip() and new_name != old_name:
            new_name = new_name.strip()
            invalid_chars = '\\/:*?"<>|'
            if any(char in new_name for char in invalid_chars):
                QMessageBox.warning(self, "エラー", f"フォルダ名に使用できない文字が含まれています: {invalid_chars}")
                return
            new_folder_path = os.path.normcase(os.path.abspath(os.path.join(BASE_MEMO_DIR, new_name)))
            if not os.path.exists(new_folder_path):
                try:
                    print(f"Renaming folder: {old_folder_path} -> {new_folder_path}")
                    os.rename(old_folder_path, new_folder_path)
                    self.tab_widget.setTabText(tab_index, new_name)
                    splitter.setProperty("folder_path", new_folder_path)

                    if old_folder_path in self.last_opened_files:
                        file_val = self.last_opened_files.pop(old_folder_path)
                        if file_val and file_val.startswith(old_folder_path + os.sep):
                            new_file_val = new_folder_path + file_val[len(old_folder_path):]
                            self.last_opened_files[new_folder_path] = new_file_val
                            print(f"Updated last opened file entry: {old_folder_path} -> {new_folder_path} ({os.path.basename(new_file_val)})")
                        else:
                            self.last_opened_files[new_folder_path] = file_val
                            print(f"Updated last opened file key only: {old_folder_path} -> {new_folder_path}")

                    updated_read_only = set()
                    for ro_path in self.read_only_files:
                        if ro_path.startswith(old_folder_path + os.sep):
                            new_ro_path = new_folder_path + ro_path[len(old_folder_path):]
                            updated_read_only.add(new_ro_path)
                            print(f"Updated read-only path: {ro_path} -> {new_ro_path}")
                        else:
                            updated_read_only.add(ro_path)
                    self.read_only_files = updated_read_only

                    if self.tab_widget.currentIndex() == tab_index:
                        _, model, tree, editor = self.get_current_widgets(tab_index)
                        if model and tree:
                            print(f"Updating tree root for renamed active tab: {new_folder_path}")
                            root_index = model.setRootPath(new_folder_path)
                            tree.setRootIndex(root_index)
                            if isinstance(model, ReadOnlyFileSystemModel):
                                model.read_only_files = self.read_only_files
                            if editor and editor.current_file_path and editor.current_file_path.startswith(old_folder_path + os.sep):
                                new_editor_path = new_folder_path + editor.current_file_path[len(old_folder_path):]
                                editor.current_file_path = new_editor_path
                                print(f"Updated editor path for active tab: {new_editor_path}")

                    self.save_tab_order()
                except OSError as e:
                    error_msg = f"フォルダ名を変更できませんでした: {e}\n\n{traceback.format_exc()}"
                    print(f"!!! ERROR: {error_msg}")
                    QMessageBox.warning(self, "エラー", error_msg)
                    splitter.setProperty("folder_path", old_folder_path)
                    self.tab_widget.setTabText(tab_index, old_name)
                except Exception as e:
                    error_message = f"フォルダ名変更中に予期せぬエラーが発生しました:\n{traceback.format_exc()}"
                    print(f"!!! CRITICAL ERROR: {error_message}")
                    QMessageBox.critical(self, "エラー", error_message)
                    splitter.setProperty("folder_path", old_folder_path)
                    self.tab_widget.setTabText(tab_index, old_name)
            else:
                QMessageBox.warning(self, "エラー", "同じ名前のフォルダが既に存在します。")
        elif ok and not new_name.strip():
            QMessageBox.warning(self, "エラー", "フォルダ名を入力してください。")
    def delete_folder(self, tab_index):
        widget = self.tab_widget.widget(tab_index)
        if not widget or widget.property(PLUS_TAB_PROPERTY): print(f"タブ {tab_index} は削除できません (+タブ)"); return
        folder_name = self.tab_widget.tabText(tab_index); splitter = widget
        if not isinstance(splitter, QSplitter): return
        folder_path = os.path.normcase(os.path.abspath(splitter.property("folder_path")))
        msg_box = QMessageBox(self); msg_box.setWindowTitle("フォルダの削除"); msg_box.setText(f"フォルダ '{folder_name}' を削除しますか？"); msg_box.setInformativeText("この操作は元に戻せません。\nフォルダ内のすべてのメモも削除されます。"); msg_box.setIcon(QMessageBox.Icon.Warning)
        delete_button = msg_box.addButton("削除する", QMessageBox.ButtonRole.DestructiveRole); cancel_button = msg_box.addButton("キャンセル", QMessageBox.ButtonRole.RejectRole); msg_box.setDefaultButton(cancel_button); msg_box.exec()
        if msg_box.clickedButton() == delete_button:
            print(f"Attempting to delete folder: {folder_path} (tab index: {tab_index})")
            try:
                current_idx = self.tab_widget.currentIndex(); removing_current = (current_idx == tab_index); index_to_select_after_remove = -1
                if removing_current:
                    if self.tab_widget.count() > 2: # +タブと削除対象タブ以外にもタブがある場合
                        index_to_select_after_remove = max(0, current_idx - 1)
                    # 他に通常タブがなければ、削除後に作成されるデフォルトタブが選択される
                elif current_idx > tab_index: index_to_select_after_remove = current_idx - 1
                else: index_to_select_after_remove = current_idx
                print(f"Calculated index to select after remove: {index_to_select_after_remove}")
                try: shutil.rmtree(folder_path); print(f"Successfully removed directory: {folder_path}")
                except OSError as e:
                    error_msg = f"フォルダ '{folder_name}' を物理的に削除できませんでした:\n{e}\n\nファイルが他のプログラムで使用されていないか確認してください。\n\n{traceback.format_exc()}"
                    print(f"!!! ERROR: {error_msg}")
                    QMessageBox.critical(self, "削除エラー", error_msg); return
                self.read_only_files = {p for p in self.read_only_files if not p.startswith(folder_path + os.sep)}
                if folder_path in self.last_opened_files: del self.last_opened_files[folder_path]; print(f"Removed folder from last_opened_files: {folder_path}")
                print(f"Removing tab at index: {tab_index}"); self.tab_widget.removeTab(tab_index); self.save_tab_order()
                plus_idx_after_remove = self._find_plus_tab_index(); num_normal_tabs_after_remove = self.tab_widget.count() - (1 if plus_idx_after_remove != -1 else 0)
                if num_normal_tabs_after_remove == 0: print("Last normal tab deleted. Creating default folder."); self.create_new_folder("デフォルト", use_default_on_empty=True, select_new_tab=True)
                elif index_to_select_after_remove != -1:
                     if plus_idx_after_remove != -1 and index_to_select_after_remove >= plus_idx_after_remove: index_to_select_after_remove = max(0, plus_idx_after_remove - 1)
                     if 0 <= index_to_select_after_remove < num_normal_tabs_after_remove: print(f"Setting current index after remove: {index_to_select_after_remove}"); self.tab_widget.setCurrentIndex(index_to_select_after_remove)
                     else:
                          if num_normal_tabs_after_remove > 0: print(f"Invalid index after remove ({index_to_select_after_remove}), selecting index 0."); self.tab_widget.setCurrentIndex(0)
                else: # index_to_select_after_remove == -1 (通常は起こらないはずだが念のため)
                     if num_normal_tabs_after_remove > 0: print("Index to select was -1, selecting index 0."); self.tab_widget.setCurrentIndex(0)
            except Exception as e:
                error_message = f"フォルダ削除中に予期せぬエラーが発生しました:\n{traceback.format_exc()}"
                print(f"!!! CRITICAL ERROR: {error_message}")
                QMessageBox.critical(self, "エラー", error_message)
    def select_file_in_tree(self, file_path, tree_view):
        if not tree_view:
            print("DEBUG: select_file_in_tree - tree_view is None, returning.")
            return
        model = tree_view.model()
        if not model:
            print("DEBUG: select_file_in_tree - model is None, returning.")
            return

        norm_path = os.path.normcase(os.path.abspath(file_path))
        print(f"DEBUG: select_file_in_tree - Attempting model.index for norm_path: {norm_path}")
        index = model.index(norm_path)
        if not index.isValid():
            print(f"DEBUG: select_file_in_tree - Index invalid for norm_path. Attempting model.index for original path: {file_path}")
            index = model.index(file_path)

        if index.isValid():
            print(f"Selecting file in tree: {norm_path}")
            tree_view.setCurrentIndex(index)
            tree_view.scrollTo(index, QTreeView.ScrollHint.PositionAtCenter)
            actual_path = model.filePath(index)
            print(f"DEBUG: select_file_in_tree - Actual path from model: {actual_path}")
            self.load_memo(actual_path)
            self.update_last_opened_file(actual_path)
        else:
            print(f"作成/選択したファイルが見つかりません: {file_path}")
            current_root = model.rootPath()
            if current_root:
                print(f"Refreshing model root ({current_root}) and retrying selection...")
                model.setRootPath("")
                model.setRootPath(current_root)
                QTimer.singleShot(100, lambda p=file_path, t=tree_view: self._select_file_in_tree_retry(p, t))

    def _select_file_in_tree_retry(self, file_path, tree_view):
        if not tree_view: return
        model = tree_view.model()
        if not model: return
        norm_path = os.path.normcase(os.path.abspath(file_path))
        index = model.index(norm_path)
        if not index.isValid(): index = model.index(file_path)

        if index.isValid():
            print(f"Selecting file in tree (retry): {norm_path}")
            tree_view.setCurrentIndex(index)
            tree_view.scrollTo(index, QTreeView.ScrollHint.PositionAtCenter)
            actual_path = model.filePath(index)
            self.load_memo(actual_path)
            self.update_last_opened_file(actual_path)
        else:
            print(f"File still not found after retry: {norm_path}")

    def rename_memo(self, index, model):
        if not index.isValid() or not model or model.isDir(index): return
        print("rename_memo: Saving current editor content before renaming..."); self.save_current_memo()
        old_file_path = model.filePath(index); old_name = model.fileName(index); folder_path = os.path.normcase(os.path.abspath(os.path.dirname(old_file_path))); old_file_path_norm = os.path.normcase(os.path.abspath(old_file_path))
        print("rename_memo: QInputDialog.getText を呼び出します。"); new_name, ok = QInputDialog.getText(self, "メモ名を変更", "新しいメモ名:", QLineEdit.EchoMode.Normal, old_name)
        if ok and new_name.strip() and new_name != old_name:
            print(f"rename_memo: ダイアログOK。入力名: '{new_name}'"); new_name_input = new_name.strip(); invalid_chars = '\\/:*?"<>|'
            if any(char in new_name_input for char in invalid_chars): QMessageBox.warning(self, "エラー", f"ファイル名に使用できない文字が含まれています: {invalid_chars}"); return
            if not new_name_input.lower().endswith(".txt"): new_file_name = f"{new_name_input}.txt"
            else: new_file_name = new_name_input
            new_file_path = os.path.normcase(os.path.abspath(os.path.join(folder_path, new_file_name)))
            if not os.path.exists(new_file_path):
                try:
                    _, _, _, editor_check = self.get_current_widgets()
                    is_renaming_current_file = (editor_check and editor_check.current_file_path == old_file_path_norm)
                    if is_renaming_current_file:
                        print("Saving editor content again just before os.rename...");
                        self.save_current_memo()

                    print(f"Renaming memo: {old_file_path_norm} -> {new_file_path}"); os.rename(old_file_path_norm, new_file_path); _, _, tree, editor = self.get_current_widgets()

                    if old_file_path_norm in self.read_only_files:
                        self.read_only_files.discard(old_file_path_norm)
                        self.read_only_files.add(new_file_path)
                        print(f"Updated read-only list: removed {old_file_path_norm}, added {new_file_path}")
                        if isinstance(model, ReadOnlyFileSystemModel):
                            model.read_only_files = self.read_only_files

                    if folder_path in self.last_opened_files and self.last_opened_files[folder_path] == old_file_path_norm:
                        self.last_opened_files[folder_path] = new_file_path
                        print(f"Updated last opened file for folder {folder_path}: {new_file_path}")

                    if isinstance(model, ReadOnlyFileSystemModel):
                         model.update_item(new_file_path)
                    current_root = model.rootPath()
                    if current_root:
                        print("Refreshing model...")
                        model.setRootPath("")
                        model.setRootPath(current_root)

                    if is_renaming_current_file and editor:
                        editor.current_file_path = new_file_path
                        print("Updated editor's current file path.")

                    if tree:
                        QTimer.singleShot(200, lambda path=new_file_path, tr=tree: self.select_file_in_tree(path, tr))

                except OSError as e:
                    error_msg = f"メモ名を変更できませんでした: {e}\n\n{traceback.format_exc()}"
                    print(f"!!! ERROR: {error_msg}")
                    QMessageBox.warning(self, "エラー", error_msg)
                except Exception as e:
                    error_message = f"メモ名変更中に予期せぬエラーが発生しました:\n{traceback.format_exc()}"
                    print(f"!!! CRITICAL ERROR: {error_message}")
                    QMessageBox.critical(self, "エラー", error_message)
            else: QMessageBox.warning(self, "エラー", "同じ名前のメモが既に存在します。")
        elif ok and not new_name.strip(): QMessageBox.warning(self, "エラー", "ファイル名を入力してください。")
        else: print("rename_memo: ダイアログキャンセルまたは名前変更なし。")
    def delete_memo(self, index, model):
        if not index.isValid() or not model or model.isDir(index): return
        file_path = model.filePath(index); file_name = model.fileName(index); file_path_norm = os.path.normcase(os.path.abspath(file_path)); folder_path_norm = os.path.dirname(file_path_norm)
        reply = QMessageBox.question(self, "メモの削除", f"メモ '{file_name}' を削除しますか？\nこの操作は元に戻せません。", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            print(f"Attempting to delete memo: {file_path_norm}")
            try:
                _, _, _, editor = self.get_current_widgets(); was_current_file = (editor and editor.current_file_path == file_path_norm)
                if was_current_file: print("Clearing editor for the file being deleted."); self.ignore_save = True; editor.clear(); editor.setReadOnly(True); editor.current_file_path = None; self.update_footer_status(); self.ignore_save = False
                self.read_only_files.discard(file_path_norm)
                if folder_path_norm in self.last_opened_files and self.last_opened_files[folder_path_norm] == file_path_norm: del self.last_opened_files[folder_path_norm]; print(f"Removed from last_opened_files: {file_path_norm}")
                remove_success = False
                if os.path.exists(file_path_norm):
                    try: os.remove(file_path_norm); print(f"File deleted successfully: {file_path_norm}"); remove_success = True
                    except OSError as e:
                        error_msg = f"メモ '{file_name}' を削除できませんでした: {e}\n\n{traceback.format_exc()}"
                        print(f"!!! ERROR: {error_msg}")
                        QMessageBox.warning(self, "エラー", error_msg); return
                else: print(f"File not found (already deleted?): {file_path_norm}"); remove_success = True

                if remove_success:
                    print("Attempting to remove item from model...")
                    current_root = model.rootPath()
                    if current_root:
                        print("Refreshing model after deletion...")
                        model.setRootPath("")
                        model.setRootPath(current_root)

            except Exception as e:
                error_message = f"メモ削除中に予期せぬエラーが発生しました:\n{traceback.format_exc()}"
                print(f"!!! CRITICAL ERROR: {error_message}")
                QMessageBox.critical(self, "エラー", error_message)
    def toggle_read_only(self, file_path, read_only, model):
        norm_path = os.path.normcase(os.path.abspath(file_path))
        if read_only: self.read_only_files.add(norm_path); print(f"読み取り専用に設定: {norm_path}")
        else: self.read_only_files.discard(norm_path); print(f"読み取り専用を解除: {norm_path}")
        if isinstance(model, ReadOnlyFileSystemModel): model.read_only_files = self.read_only_files; model.update_item(file_path)
        _, _, _, editor = self.get_current_widgets()
        if editor and editor.current_file_path == norm_path: editor.setReadOnly(read_only); self.update_footer_status()
    def load_memo(self, file_path):
        _, _, _, editor = self.get_current_widgets()
        if not editor: QMessageBox.warning(self, "エラー", "メモを表示するエディタが見つかりません。"); return
        norm_path = os.path.normcase(os.path.abspath(file_path)); print(f"Attempting to load memo: {norm_path}")
        if not os.path.isfile(norm_path):
            error_msg = f"ファイルが見つかりません: {norm_path}"; print(f"Error loading memo: {error_msg}"); QMessageBox.warning(self, "エラー", error_msg)
            self.ignore_save = True; editor.clear(); editor.setReadOnly(True); editor.current_file_path = None; self.update_footer_status(); self.ignore_save = False
            folder_path = os.path.dirname(norm_path)
            if folder_path in self.last_opened_files and self.last_opened_files[folder_path] == norm_path: print(f"Removing missing file from last_opened_files: {norm_path}"); del self.last_opened_files[folder_path]
            return
        self.ignore_save = True
        try:
            content = ""
            detected_encoding = None
            try:
                with open(norm_path, 'r', encoding='utf-8-sig') as f:
                    content = f.read()
                detected_encoding = 'utf-8-sig'
                print(f"Read file with utf-8-sig: {norm_path}")
            except UnicodeDecodeError:
                print(f"Failed reading with utf-8-sig, trying utf-8: {norm_path}")
                try:
                    with open(norm_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    detected_encoding = 'utf-8'
                    print(f"Read file with utf-8: {norm_path}")
                except UnicodeDecodeError:
                    print(f"Failed reading with utf-8, trying cp932: {norm_path}")
                    try:
                        with open(norm_path, 'r', encoding='cp932', errors='replace') as f:
                            content = f.read()
                        detected_encoding = 'cp932'
                        print(f"Read file with cp932 (replaced errors): {norm_path}")
                        QMessageBox.warning(self, "エンコーディング警告", f"ファイルを CP932 (Shift-JIS) として読み込みました。\n文字化けしている可能性があります。\nUTF-8 で保存し直すことを推奨します。\n{norm_path}")
                    except Exception as e_cp932:
                        raise IOError(f"ファイルの読み込みに失敗しました (エンコーディング不明): {e_cp932}") from e_cp932
            except Exception as e_read:
                 raise IOError(f"ファイルの読み込み中にエラーが発生しました: {e_read}") from e_read
            if detected_encoding is None:
                raise IOError("ファイルの読み込みに成功しましたが、エンコーディングが特定できませんでした。")
            is_read_only = norm_path in self.read_only_files
            editor.setPlainText(content); editor.current_file_path = norm_path; editor.setReadOnly(is_read_only)
            editor.document().setModified(False); editor.moveCursor(QTextCursor.MoveOperation.Start)
            self.update_footer_status(); editor.setFocus(); print(f"Memo loaded successfully: {norm_path}")
        except Exception as e:
            error_message = f"メモ '{os.path.basename(norm_path)}' を読み込めませんでした:\n{e}\n{traceback.format_exc()}"
            print(f"!!! ERROR: {error_message}")
            QMessageBox.critical(self, "読み込みエラー", error_message)
            if editor:
                editor.clear(); editor.setReadOnly(True); editor.current_file_path = None; self.update_footer_status()
        finally:
            self.ignore_save = False
    def save_current_memo(self, index=None):
        splitter, model, tree, editor = self.get_current_widgets(index)
        if not editor or self.ignore_save or not editor.current_file_path or editor.isReadOnly() or not editor.document().isModified(): return
        file_path = editor.current_file_path; content = editor.toPlainText(); print(f"Attempting to save memo: {file_path}")
        try:
            dir_path = os.path.dirname(file_path)
            if not os.path.exists(dir_path): print(f"Warning: Directory does not exist, creating: {dir_path}"); os.makedirs(dir_path)
            with open(file_path, 'w', encoding='utf-8') as f: f.write(content)
            editor.document().setModified(False); print(f"Memo saved successfully: {file_path}")
        except Exception as e:
            error_message = f"メモを保存できませんでした:\n{traceback.format_exc()}\n{file_path}"
            print(f"!!! ERROR: {error_message}")
            QMessageBox.critical(self, "保存エラー", error_message)
    def insert_date(self):
        focused_widget = QApplication.focusWidget()
        if isinstance(focused_widget, MemoTextEdit) and not focused_widget.isReadOnly(): today = datetime.date.today().strftime("%Y%m%d"); date_string = f"_{today}_"; focused_widget.textCursor().insertText(date_string)
    def set_current_editor_wrap_mode(self, mode, column_width=72):
        _, _, _, editor = self.get_current_widgets()
        if not editor: return
        current_mode_text = "不明"
        if mode == QTextEdit.LineWrapMode.NoWrap: editor.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap); current_mode_text = "折り返さない"
        elif mode == QTextEdit.LineWrapMode.FixedPixelWidth: editor.setLineWrapMode(QTextEdit.LineWrapMode.FixedPixelWidth); font_metrics = QFontMetrics(editor.font()); pixel_width = font_metrics.horizontalAdvance('W') * column_width; editor.setLineWrapColumnOrWidth(pixel_width); current_mode_text = f"{column_width}文字(目安)"
        elif mode == QTextEdit.LineWrapMode.WidgetWidth: editor.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth); current_mode_text = "ウィンドウ幅"
        else: editor.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth); current_mode_text = "ウィンドウ幅"
        self.status_label_wrap.setText(f"折り返し: {current_mode_text}"); self.update_wrap_menu_state()
    def update_wrap_menu_state(self):
        _, _, _, editor = self.get_current_widgets()
        wrap_button = self.status_bar.findChild(QPushButton, "wrap_button")
        if not editor or not wrap_button:
            return
        mode = editor.lineWrapMode()
        wrap_menu = wrap_button.menu()
        if not wrap_menu:
            return
        actions = wrap_menu.actions()
        if len(actions) < 3:
            return
        no_wrap_action = actions[0]
        char_wrap_action = actions[1]
        window_wrap_action = actions[2]
        no_wrap_action.setChecked(mode == QTextEdit.LineWrapMode.NoWrap)
        char_wrap_action.setChecked(mode == QTextEdit.LineWrapMode.FixedPixelWidth)
        window_wrap_action.setChecked(mode == QTextEdit.LineWrapMode.WidgetWidth)
    def load_folders(self):
        self.tab_widget.clear()
        print(f"DEBUG: load_folders - Start loading from: {BASE_MEMO_DIR}")
        try:
            folder_paths = {}
            if not os.path.exists(BASE_MEMO_DIR):
                print(f"ベースディレクトリが見つからないため作成します: {BASE_MEMO_DIR}")
                os.makedirs(BASE_MEMO_DIR)

            try:
                items = os.listdir(BASE_MEMO_DIR)
                print(f"DEBUG: load_folders - Found items in BASE_MEMO_DIR: {items}")
            except Exception as e_list:
                print(f"!!! ERROR: {BASE_MEMO_DIR} のリスト取得中にエラー: {e_list}\n{traceback.format_exc()}")
                items = []

            for item in items:
                item_path = os.path.join(BASE_MEMO_DIR, item)
                try:
                    if os.path.isdir(item_path):
                        norm_path = os.path.normcase(os.path.abspath(item_path))
                        folder_paths[norm_path] = item
                        print(f"DEBUG: load_folders - Found folder: {item} at {norm_path}")
                    else:
                        print(f"DEBUG: load_folders - Skipping non-directory item: {item}")
                except Exception as e_isdir:
                    print(f"!!! ERROR: {item_path} のisdirチェック中にエラー: {e_isdir}\n{traceback.format_exc()}")
                    continue

            if not folder_paths:
                print("No existing folders found. Creating default folder.")
                self.create_new_folder("デフォルト", use_default_on_empty=True, select_new_tab=False)
                self._add_plus_tab()
            else:
                ordered_paths = []
                if hasattr(self, 'saved_tab_order') and self.saved_tab_order:
                    print("Applying saved tab order.")
                    for path in self.saved_tab_order:
                        if path in folder_paths:
                            ordered_paths.append(path)
                    remaining_paths = sorted([p for p in folder_paths.keys() if p not in ordered_paths])
                    ordered_paths.extend(remaining_paths)
                else:
                    print("No saved tab order found. Sorting by name.")
                    ordered_paths = sorted(folder_paths.keys())

                print(f"Loading folders in order: {ordered_paths}")
                for norm_path in ordered_paths:
                    name = folder_paths[norm_path]
                    print(f"DEBUG: load_folders - Adding tab for: {name} ({norm_path})")
                    self.add_folder_tab(name, norm_path, add_plus_tab_after=False)

                self._add_plus_tab()
                self.save_tab_order()

        except FileNotFoundError:
            print(f"ベースディレクトリが見つかりません (FileNotFoundError): {BASE_MEMO_DIR}")
            self.create_new_folder("デフォルト", use_default_on_empty=True, select_new_tab=True)
        except Exception as e:
            error_message = f"フォルダの読み込み中に予期せぬエラーが発生しました:\n{traceback.format_exc()}"
            print(f"!!! CRITICAL ERROR: {error_message}")
            QMessageBox.critical(self, "致命的なエラー", error_message)

        plus_idx = self._find_plus_tab_index()
        num_normal_tabs = self.tab_widget.count() - (1 if plus_idx != -1 else 0)
        if num_normal_tabs == 0 and not folder_paths: # 修正: and not folder_paths を追加
             print("DEBUG: No normal tabs found after load_folders (and no folders existed), creating default.")
             self.create_new_folder("デフォルト", use_default_on_empty=True, select_new_tab=True)

    def add_folder_tab(self, name, path, add_plus_tab_after=True):
        plus_tab_index = self._find_plus_tab_index()
        if plus_tab_index != -1: self.tab_widget.removeTab(plus_tab_index)
        splitter = QSplitter(Qt.Orientation.Horizontal); norm_path = os.path.normcase(os.path.abspath(path)); splitter.setProperty("folder_path", norm_path)
        left_column_widget = QWidget(); left_layout = QVBoxLayout(left_column_widget); left_layout.setContentsMargins(0,0,0,0)
        file_model = ReadOnlyFileSystemModel(self.read_only_files); file_model.setFilter(QDir.Filter.NoDotAndDotDot | QDir.Filter.Files | QDir.Filter.Dirs)
        print(f"DEBUG: add_folder_tab - Setting root path for model: {norm_path}")
        root_index = file_model.setRootPath(norm_path)
        print(f"DEBUG: add_folder_tab - Root index valid: {root_index.isValid()}")
        file_tree = CustomTreeView(); file_tree.setModel(file_model); file_tree.setRootIndex(root_index); file_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        file_tree.customContextMenuRequested.connect(self.show_file_tree_context_menu); file_tree.doubleClicked.connect(self.on_file_tree_double_clicked); file_tree.emptyAreaDoubleClicked.connect(self.on_file_tree_empty_area_double_clicked)
        file_tree.selectionModel().selectionChanged.connect(self.on_file_selection_changed); file_tree.setHeaderHidden(True)
        for i in range(1, file_model.columnCount()): file_tree.hideColumn(i)
        left_layout.addWidget(file_tree); splitter.addWidget(left_column_widget)
        memo_edit = MemoTextEdit(); self.apply_font_size(memo_edit); memo_edit.setReadOnly(True); memo_edit.textChanged.connect(self.update_footer_status); memo_edit.cursorPositionChanged.connect(self.update_footer_status)
        splitter.addWidget(memo_edit); splitter.setStretchFactor(0, 1); splitter.setStretchFactor(1, 3)
        insert_index = plus_tab_index if plus_tab_index != -1 else self.tab_widget.count()
        new_index = self.tab_widget.insertTab(insert_index, splitter, name); print(f"タブ '{name}' 追加完了。 index: {new_index}, path: {norm_path}")
        if add_plus_tab_after: self._add_plus_tab()
        self.save_tab_order()
        return new_index
    def _add_plus_tab(self):
        if self._find_plus_tab_index() == -1: plus_widget = QWidget(); plus_widget.setProperty(PLUS_TAB_PROPERTY, True); plus_widget.setFocusPolicy(Qt.FocusPolicy.NoFocus); index = self.tab_widget.addTab(plus_widget, "+"); self.tab_widget.setTabToolTip(index, "新しいフォルダ（タブ）を作成します"); print(f"+タブ追加完了。 index: {index}")
    def _find_plus_tab_index(self):
        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)
            if widget and widget.property(PLUS_TAB_PROPERTY):
                return i
        return -1
    def update_footer_status(self):
        current_index = self.tab_widget.currentIndex()
        if current_index < 0 or current_index >= self.tab_widget.count(): self.status_label_chars.setText("文字数: -"); self.status_label_cursor.setText("カーソル: -"); return
        widget = self.tab_widget.widget(current_index)
        if widget and widget.property(PLUS_TAB_PROPERTY): self.status_label_chars.setText("文字数: -"); self.status_label_cursor.setText("カーソル: -"); return
        _, _, _, editor = self.get_current_widgets()
        if editor and editor.current_file_path:
            if editor.isReadOnly(): self.status_label_chars.setText("文字数: - (編集不可)"); self.status_label_cursor.setText("カーソル: -")
            else: char_count = len(editor.toPlainText()); self.status_label_chars.setText(f"文字数: {char_count}"); cursor = editor.textCursor(); line = cursor.blockNumber() + 1; col = cursor.columnNumber() + 1; self.status_label_cursor.setText(f"カーソル: {line}行 {col}桁")
        else: self.status_label_chars.setText("文字数: -"); self.status_label_cursor.setText("カーソル: -")
    def update_footer_date(self): now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M"); self.status_label_date.setText(now)
    def on_activate_toggle(self): print(f">>> on_activate_toggle called by hotkey ({'Insert' if PYNPUT_AVAILABLE else 'N/A'})"); print("Emitting toggle_visibility_signal..."); self.toggle_visibility_signal.emit(); print("<<< toggle_visibility_signal emitted.")

    # ★★★ 修正: ホットキーデバウンス処理追加 ★★★
    def on_press(self, key):
        print(f"--- pynput on_press --- key: {key}")
        try:
            if key == keyboard.Key.insert:
                current_time = time.time()
                if current_time - self.last_hotkey_press_time > self.hotkey_debounce_time:
                    self.last_hotkey_press_time = current_time
                    print(">>> Hotkey Insert detected in on_press (debounced).")
                    self.on_activate_toggle() # シグナル経由でメインスレッドの処理を呼び出す
                    print("<<< Hotkey Insert processed in on_press (debounced).")
                else:
                    print(">>> Hotkey Insert detected in on_press (ignored due to debounce).")
                return True # イベントの伝播を続ける
        except Exception as e:
            print(f"!!! Error in on_press: {e}")
            traceback.print_exc()
        return True # イベントの伝播を続ける

    def on_release(self, key): pass
    def start_hotkey_listener_global(self):
        if not PYNPUT_AVAILABLE: print("pynput が利用できないため、ホットキーリスナーを開始できません。"); return
        if self.hotkey_listener: print("Stopping existing hotkey listener before starting a new one...")
        try:
            hotkey_name_for_log = "Insert"; print(f">>> Attempting to start keyboard.Listener for hotkey: {hotkey_name_for_log}")
            self.hotkey_listener = keyboard.Listener(on_press=self.on_press, on_release=self.on_release, suppress=False); print("    Listener instance created.")
            self.hotkey_thread = threading.Thread(target=self.hotkey_listener.run, name="HotkeyListenerThread", daemon=True); print("    Listener thread created.")
            self.hotkey_thread.start(); print("    Listener thread started.")
            QTimer.singleShot(500, self._check_hotkey_thread_status); print("<<< Listener start process initiated.")
        except Exception as e:
            error_msg = f"!!! システムワイドホットキーリスナー ({hotkey_name_for_log}) の開始中に予期せぬエラーが発生しました:\n{e}\n{traceback.format_exc()}"
            print(error_msg)
            QMessageBox.warning(self, "ホットキーエラー", f"{error_msg}\n\nホットキー機能は利用できません。")
            self.hotkey_listener = None; self.hotkey_thread = None
    def _check_hotkey_thread_status(self):
        hotkey_name_for_log = "Insert"; print(f">>> Checking hotkey thread status ({hotkey_name_for_log})...")
        if self.hotkey_thread and self.hotkey_thread.is_alive(): print(f"    Hotkey listener thread ({hotkey_name_for_log}) is alive and running.")
        else: print(f"!!! WARNING: Hotkey listener thread ({hotkey_name_for_log}) is NOT alive. Hotkey will not work."); self.hotkey_listener = None; self.hotkey_thread = None
        print(f"<<< Hotkey thread status check finished.")
    def increase_font_size(self): self.current_font_size += 1; self.current_font_size = min(self.current_font_size, 72); self.font_size_label.setText(f"{self.current_font_size}pt"); self.apply_font_size_to_all_editors()
    def decrease_font_size(self): self.current_font_size -= 1; self.current_font_size = max(self.current_font_size, 6); self.font_size_label.setText(f"{self.current_font_size}pt"); self.apply_font_size_to_all_editors()
    def apply_font_size(self, editor):
        if editor: editor.set_font_size(self.current_font_size)
    def apply_font_size_to_all_editors(self):
        print(f"Applying font size: {self.current_font_size}pt to all editors")
        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)
            if isinstance(widget, QSplitter):
                editor = widget.widget(1)
                if isinstance(editor, MemoTextEdit):
                    self.apply_font_size(editor)
    def update_last_opened_file(self, file_path):
        current_folder_path = self.get_current_folder_path()
        if current_folder_path and file_path:
            norm_folder_path = os.path.normcase(os.path.abspath(current_folder_path))
            norm_file_path = os.path.normcase(os.path.abspath(file_path))
            if norm_file_path.startswith(norm_folder_path + os.sep):
                if self.last_opened_files.get(norm_folder_path) != norm_file_path:
                    self.last_opened_files[norm_folder_path] = norm_file_path
                    print(f"最後に開いたファイルを更新: {norm_folder_path} -> {os.path.basename(norm_file_path)}")
            else:
                print(f"警告: ファイル {norm_file_path} はフォルダ {norm_folder_path} 内にありません。最後に開いたファイルは更新されません。")
    def update_last_opened_file_for_current_tab(self):
        _, _, _, editor = self.get_current_widgets()
        if editor and editor.current_file_path: self.update_last_opened_file(editor.current_file_path)
        else: self.clear_last_opened_file_for_current_tab()
    def update_last_opened_file_for_tab(self, index):
         splitter, _, _, editor = self.get_current_widgets(index)
         if splitter:
             folder_path = splitter.property("folder_path")
             if folder_path:
                 norm_folder_path = os.path.normcase(os.path.abspath(folder_path))
                 if editor and editor.current_file_path:
                     norm_file_path = os.path.normcase(os.path.abspath(editor.current_file_path))
                     if norm_file_path.startswith(norm_folder_path + os.sep):
                         if self.last_opened_files.get(norm_folder_path) != norm_file_path:
                             self.last_opened_files[norm_folder_path] = norm_file_path
                             print(f"最後に開いたファイルを更新 (index {index}): {norm_folder_path} -> {os.path.basename(norm_file_path)}")
                     else:
                         if norm_folder_path in self.last_opened_files:
                             del self.last_opened_files[norm_folder_path]
                             print(f"最後に開いたファイルをクリア (index {index}, ファイルがフォルダ外): {norm_folder_path}")
                 else:
                     if norm_folder_path in self.last_opened_files:
                         del self.last_opened_files[norm_folder_path]
                         print(f"最後に開いたファイルをクリア (index {index}, ファイルなし): {norm_folder_path}")
             else:
                 print(f"警告: update_last_opened_file_for_tab - folder_path が見つかりません (index {index})")
         else:
             print(f"情報: update_last_opened_file_for_tab - 通常のフォルダタブではありません (index {index})")
    def load_last_opened_file_for_tab(self, index):
        folder_path = self.get_folder_path_for_tab(index)
        if folder_path:
            norm_folder_path = os.path.normcase(os.path.abspath(folder_path))
            last_opened = self.last_opened_files.get(norm_folder_path)
            _, _, tree, editor = self.get_current_widgets(index)

            if last_opened and os.path.isfile(last_opened):
                print(f"タブ (index {index}) の最後に開いていたファイルをロードします: {last_opened}")
                if editor:
                    if tree:
                        QTimer.singleShot(0, lambda p=last_opened, t=tree: self.select_file_in_tree_only(p, t))
                    self.load_memo(last_opened)
                else:
                    print(f"警告: load_last_opened_file_for_tab - エディタが見つかりません (index {index})")
            else:
                if last_opened:
                    print(f"最後に開いていたファイルが見つかりません: {last_opened}")
                    if norm_folder_path in self.last_opened_files:
                        del self.last_opened_files[norm_folder_path]
                else:
                    print(f"タブ (index {index}) に最後に開いていたファイルの記録がありません。")

                if editor and editor.current_file_path:
                    print(f"エディタをクリアします (index {index})")
                    self.ignore_save = True
                    editor.clear()
                    editor.setReadOnly(True)
                    editor.current_file_path = None
                    self.update_footer_status()
                    self.ignore_save = False
                if tree:
                    tree.clearSelection()

    def select_file_in_tree_only(self, file_path, tree_view):
        """指定されたファイルをツリービューで選択するだけ（ロードはしない）"""
        print(f"DEBUG: select_file_in_tree_only called with path: {file_path}")
        if not tree_view:
            print("DEBUG: select_file_in_tree_only - tree_view is None, returning.")
            return
        model = tree_view.model()
        if not model:
            print("DEBUG: select_file_in_tree_only - model is None, returning.")
            return

        norm_path = os.path.normcase(os.path.abspath(file_path))
        print(f"DEBUG: select_file_in_tree_only - Attempting model.index for norm_path: {norm_path}")
        index = model.index(norm_path)
        if not index.isValid():
            print(f"DEBUG: select_file_in_tree_only - Index invalid for norm_path. Attempting model.index for original path: {file_path}")
            index = model.index(file_path)

        if index.isValid():
            print(f"Selecting file in tree only: {norm_path}")
            tree_view.setCurrentIndex(index)
            tree_view.scrollTo(index, QTreeView.ScrollHint.PositionAtCenter)
        else:
            print(f"Cannot select file in tree (not found): {norm_path}")
            current_root = model.rootPath()
            if current_root:
                print(f"Refreshing model root ({current_root}) and retrying selection only...")
                model.setRootPath("")
                model.setRootPath(current_root)
                QTimer.singleShot(100, lambda p=file_path, t=tree_view: self._select_file_in_tree_only_retry(p, t))

    def _select_file_in_tree_only_retry(self, file_path, tree_view):
        """select_file_in_tree_only のリトライ用"""
        if not tree_view: return
        model = tree_view.model()
        if not model: return
        norm_path = os.path.normcase(os.path.abspath(file_path))
        index = model.index(norm_path)
        if not index.isValid(): index = model.index(file_path)

        if index.isValid():
            print(f"Selecting file in tree only (retry): {norm_path}")
            tree_view.setCurrentIndex(index)
            tree_view.scrollTo(index, QTreeView.ScrollHint.PositionAtCenter)
        else:
            print(f"File still not found after retry (selection only): {norm_path}")


    def clear_last_opened_file_for_current_tab(self):
        current_folder_path = self.get_current_folder_path()
        if current_folder_path:
            norm_folder_path = os.path.normcase(os.path.abspath(current_folder_path))
            if norm_folder_path in self.last_opened_files:
                del self.last_opened_files[norm_folder_path]
                print(f"最後に開いたファイルをクリア: {norm_folder_path}")
    def get_folder_path_for_tab(self, index):
        if 0 <= index < self.tab_widget.count():
            widget = self.tab_widget.widget(index)
            if isinstance(widget, QSplitter):
                return widget.property("folder_path")
        return None
    def save_tab_order(self, *args):
        """現在のタブの順序（フォルダパス）を self.current_tab_order に保存する"""
        new_order = []
        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)
            if isinstance(widget, QSplitter):
                folder_path = widget.property("folder_path")
                if folder_path:
                    new_order.append(os.path.normcase(os.path.abspath(folder_path)))
        if self.current_tab_order != new_order:
            print(f"タブ順序変更検知: {new_order}")
            self.current_tab_order = new_order

    def show_auto_text_settings(self):
        dialog = AutoTextSettingsDialog(self)
        dialog.set_texts(self.auto_texts)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.auto_texts = dialog.get_texts()
            self.settings.setValue("autoTexts", self.auto_texts)

    def show_auto_text_menu(self):
        if self.auto_text_menu_visible:
            return

        self.auto_text_menu = QMenu(self)
        # 1から9まで、最後に0を表示
        for i in range(1, 10):
            action = self.auto_text_menu.addAction(f"{i}: {self.auto_texts[i-1]}")
            action.triggered.connect(lambda checked, idx=i-1: self.insert_auto_text(idx))
        # 0を最後に追加
        action = self.auto_text_menu.addAction(f"0: {self.auto_texts[9]}")
        action.triggered.connect(lambda checked, idx=9: self.insert_auto_text(idx))
        
        # メニューを表示
        editor = self.get_current_widgets()[3]
        if editor:
            cursor_pos = editor.mapToGlobal(editor.cursorRect().bottomRight())
            self.auto_text_menu_visible = True
            self.auto_text_menu.aboutToHide.connect(self.on_menu_hidden)
            # メニューを表示する前にフォーカスを確保
            self.setFocus()
            # メニューを表示する前にイベントフィルターを設定
            QApplication.instance().installEventFilter(self)
            self.auto_text_menu.exec(cursor_pos)

    def on_menu_hidden(self):
        self.auto_text_menu_visible = False
        if self.auto_text_menu:
            self.auto_text_menu.aboutToHide.disconnect(self.on_menu_hidden)
            self.auto_text_menu = None
        # メニューが閉じられたらイベントフィルターを解除
        QApplication.instance().removeEventFilter(self)

    def handle_number_key(self, number):
        if self.auto_text_menu_visible:
            # 数字キーの処理を改善
            if number == 0:
                self.insert_auto_text(9)  # 0キーは最後の項目
            else:
                self.insert_auto_text(number - 1)  # 1-9キーは対応する項目
            if self.auto_text_menu:
                self.auto_text_menu.close()

    def insert_auto_text(self, index):
        if 0 <= index < len(self.auto_texts):
            editor = self.get_current_widgets()[3]
            if editor and not editor.isReadOnly():
                print(f"DEBUG: Inserting auto-text at index {index}: {self.auto_texts[index]}")  # デバッグ用
                editor.textCursor().insertText(self.auto_texts[index])
                # メニューを閉じる
                if self.auto_text_menu:
                    self.auto_text_menu.close()
                self.auto_text_menu_visible = False
                # エディタにフォーカスを戻す
                editor.setFocus()

class AutoTextSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("自動入力テキスト設定")
        self.setModal(True)
        self.resize(400, 500)

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        self.text_inputs = []
        for i in range(10):
            text_input = QLineEdit()
            self.text_inputs.append(text_input)
            form_layout.addRow(f"Ctrl+W+{i}:", text_input)

        layout.addLayout(form_layout)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def get_texts(self):
        return [input.text() for input in self.text_inputs]

    def set_texts(self, texts):
        for i, text in enumerate(texts):
            if i < len(self.text_inputs):
                self.text_inputs[i].setText(text)

# --- アプリケーション実行 (変更なし) ---
if __name__ == '__main__':
    if hasattr(Qt.ApplicationAttribute, 'AA_EnableHighDpiScaling'): QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    # ★★★ 追加: Windowsでフォアグラウンド設定を許可する試み ★★★
    if platform.system() == "Windows":
        try:
            ctypes.windll.user32.AllowSetForegroundWindow(-1) # ASFW_ANY (-1)
            print("DEBUG: Called AllowSetForegroundWindow(ASFW_ANY)")
        except Exception as e_allow:
            print(f"DEBUG: Failed to call AllowSetForegroundWindow: {e_allow}")
    if hasattr(Qt.ApplicationAttribute, 'AA_UseHighDpiPixmaps'): QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv); app.setStyle("Fusion")
    if QTNETWORK_AVAILABLE:
        shared_memory = QSharedMemory(UNIQUE_KEY)
        if shared_memory.attach(QSharedMemory.AccessMode.ReadOnly):
            print("Another instance detected (shared memory attached). Sending activation request.")
            shared_memory.detach()
            socket = QLocalSocket(); socket.connectToServer(UNIQUE_KEY)
            if socket.waitForConnected(500):
                print("Connected to existing instance. Sending message."); socket.write(b'activate'); socket.waitForBytesWritten(500); socket.disconnectFromServer(); print("Activation request sent. Exiting.")
            else:
                print(f"Error: Could not connect to existing instance server: {socket.errorString()}"); QMessageBox.warning(None, "起動エラー", f"既に起動している {APP_NAME} に接続できませんでした。\n({socket.errorString()})\n\nプロセスが残っている可能性があります。")
            sys.exit(0)
        else:
            print("No other instance detected or shared memory creation failed. Creating shared memory and starting server.")
            if not shared_memory.create(1):
                print(f"Error: Could not create shared memory: {shared_memory.errorString()}")
                QMessageBox.critical(None, "起動エラー", f"共有メモリの作成に失敗しました。\n{shared_memory.errorString()}")
                sys.exit(1)
            print("Shared memory created successfully.")

            if not PYNPUT_AVAILABLE: QMessageBox.warning(None, "ホットキー警告", "pynput ライブラリが見つかりません。\nシステムワイドホットキー機能は無効になります。\nインストールするには、コマンドプロンプト等で\n`pip install pynput`\nを実行してください。")
            main_win = MemoApp()
            main_win.local_server = QLocalServer(); QLocalServer.removeServer(UNIQUE_KEY) # 既存のサーバーがあれば削除試行
            if main_win.local_server.listen(UNIQUE_KEY):
                print(f"Local server listening on: {UNIQUE_KEY}"); main_win.local_server.newConnection.connect(main_win.handle_new_connection)
            else:
                print(f"Error: Could not start local server on {UNIQUE_KEY}."); QMessageBox.critical(main_win, "起動エラー", f"ローカルサーバーの起動に失敗しました。\n{main_win.local_server.errorString()}"); shared_memory.detach(); sys.exit(1)

            main_win.show(); exit_code = app.exec()
            if shared_memory.isAttached(): shared_memory.detach()
            sys.exit(exit_code)

    else: # QTNETWORK_AVAILABLE is False
        print("QtNetwork モジュールが利用できないため、単一インスタンスチェックをスキップします。")
        if not PYNPUT_AVAILABLE: QMessageBox.warning(None, "ホットキー警告", "pynput ライブラリが見つかりません。\nシステムワイドホットキー機能は無効になります。\nインストールするには、コマンドプロンプト等で\n`pip install pynput`\nを実行してください。")
        main_win = MemoApp(); main_win.show(); sys.exit(app.exec())
