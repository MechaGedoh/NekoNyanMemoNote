# -*- coding: utf-8 -*-

import os
import traceback
from PyQt6.QtWidgets import (
    QWidget, QTextEdit, QTreeView, QTabBar, QTabWidget, QDialog, 
    QFormLayout, QDialogButtonBox, QLineEdit, QVBoxLayout
)
from PyQt6.QtGui import (
    QPainter, QPalette, QColor, QTextCursor, QTextFormat, QFont, 
    QInputMethodEvent, QTextCharFormat, QFileSystemModel
)
from PyQt6.QtCore import (
    Qt, QSize, QRect, pyqtSignal, QPoint
)

from .constants import PREEDIT_PROPERTY_ID, PLUS_TAB_PROPERTY, DEFAULT_FONT_SIZE

# --- 行番号表示用ウィジェット ---
class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.codeEditor = editor
    
    def sizeHint(self):
        return QSize(self.line_number_area_width(), 0)

    def line_number_area_width(self):
        digits = 1
        doc = self.codeEditor.document()
        if not doc:
            return 50  # デフォルト3桁分の幅を確保
        font_metrics = self.fontMetrics() if self.font() else self.codeEditor.fontMetrics()
        max_num = max(1, doc.blockCount())
        while max_num >= 10:
            max_num //= 10
            digits += 1
        # 最低3桁分の幅を確保
        min_digits = 3
        actual_digits = max(digits, min_digits)
        space = 5 + font_metrics.horizontalAdvance('9') * actual_digits + 5
        return space
    
    def update_width(self):
        self.codeEditor.setViewportMargins(self.line_number_area_width(), 0, 0, 0)
    
    def paintEvent(self, event):
        self.codeEditor.line_number_area_paint_event(event)

    def set_font(self, font):
        self.setFont(font)
        self.update_width()

# --- 行番号付きテキストエディタ ---
class MemoTextEdit(QTextEdit):
    def __init__(self, parent=None, file_path=None):
        super().__init__(parent)
        self.lineNumberArea = LineNumberArea(self)
        self.file_path = file_path
        self.is_loaded = False
        self.document().blockCountChanged.connect(self.update_line_number_area_width)
        self.verticalScrollBar().valueChanged.connect(self.lineNumberArea.update)
        self.cursorPositionChanged.connect(self.highlight_current_line)
        self.cursorPositionChanged.connect(self.lineNumberArea.update)
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.update_line_number_area_width(0)
        self.highlight_current_line()
        self.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)
        
        # 初期フォントサイズを設定（CSSに上書きされないように）
        font = self.font()
        if font.pointSize() < 0:  # システムフォントサイズが不明な場合
            font.setPointSize(DEFAULT_FONT_SIZE)
            self.setFont(font)
            self.lineNumberArea.set_font(font)

    def insertFromMimeData(self, source):
        if source.hasText():
            self.insertPlainText(source.text())

    def line_number_area_paint_event(self, event):
        painter = QPainter(self.lineNumberArea)
        bg_color = self.palette().color(QPalette.ColorRole.Base)
        painter.fillRect(event.rect(), bg_color)
        first_visible_cursor = self.cursorForPosition(QPoint(0, 0))
        block = first_visible_cursor.block()
        if not block.isValid():
            return
        
        blockNumber = block.blockNumber()
        offset = QPoint(self.horizontalScrollBar().value(), self.verticalScrollBar().value())
        top = self.document().documentLayout().blockBoundingRect(block).translated(-offset.x(), -offset.y()).top()
        bottom = top + self.document().documentLayout().blockBoundingRect(block).height()
        width = self.lineNumberArea.width()
        height = self.fontMetrics().height()
        painter.setFont(self.lineNumberArea.font())
        default_pen_color = self.palette().color(QPalette.ColorRole.Text)
        current_line_pen_color = QColor("#bd93f9")  # アプリのプライマリー色に統一
        
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(blockNumber + 1)
                is_current_line = self.textCursor().blockNumber() == blockNumber
                pen_color = current_line_pen_color if is_current_line else default_pen_color
                painter.setPen(pen_color)
                painter.drawText(0, int(top), width - 5, height, Qt.AlignmentFlag.AlignRight, number)
            block = block.next()
            if block.isValid():
                top = bottom
                bottom = top + self.document().documentLayout().blockBoundingRect(block).height()
            blockNumber += 1

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.lineNumberArea.setGeometry(QRect(cr.left(), cr.top(), 
                                              self.lineNumberArea.line_number_area_width(), 
                                              cr.height()))
    
    def update_line_number_area_width(self, _=0):
        self.lineNumberArea.update_width()
        self.lineNumberArea.update()

    def highlight_current_line(self):
        extraSelections = self.extraSelections()
        extraSelections = [sel for sel in extraSelections if sel.format.property(QTextFormat.Property.FullWidthSelection) != True]
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            lineColor = QColor("#3d4152")  # 現在行のハイライト色（選択色より深い色）
            selection.format.setBackground(lineColor)
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extraSelections.append(selection)
        self.setExtraSelections(extraSelections)
        self.lineNumberArea.update()
    
    def set_font_size(self, size):
        print(f"DEBUG: MemoTextEdit.set_font_size() called with size={size}")
        print(f"DEBUG: Before - Current font size: {self.font().pointSize()}")
        font = self.font()
        print(f"DEBUG: Got font: {font.family()}, current size: {font.pointSize()}")
        font.setPointSize(size)
        print(f"DEBUG: Set font point size to: {font.pointSize()}")
        self.setFont(font)
        print(f"DEBUG: After setFont() - Current font size: {self.font().pointSize()}")
        self.lineNumberArea.set_font(font)
        self.update_line_number_area_width()
        print(f"DEBUG: Final - Font size after all operations: {self.font().pointSize()}")

    def inputMethodEvent(self, event: QInputMethodEvent):
        try:
            current_extra_selections = self.extraSelections()
            non_preedit_selections = [sel for sel in current_extra_selections if sel.format.property(PREEDIT_PROPERTY_ID) != True]
            super().inputMethodEvent(event)
            new_preedit_selections = []
            if event.preeditString():
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
                        fmt.setProperty(PREEDIT_PROPERTY_ID, True)
                        selection.format = fmt
                        new_preedit_selections.append(selection)

            final_selections = non_preedit_selections + new_preedit_selections
            self.setExtraSelections(final_selections)

        except Exception as e:
            print(f"!!! ERROR: Input method event error: {e}\n{traceback.format_exc()}")

    def focusOutEvent(self, event):
        try:
            extraSelections = self.extraSelections()
            extraSelections = [sel for sel in extraSelections if sel.format.property(PREEDIT_PROPERTY_ID) != True]
            self.setExtraSelections(extraSelections)
        except Exception as e:
            print(f"!!! ERROR: Focus out event error: {e}\n{traceback.format_exc()}")
        finally:
            super().focusOutEvent(event)

# --- 読み取り専用ファイル用ファイルシステムモデル ---
class ReadOnlyFileSystemModel(QFileSystemModel):
    def __init__(self, read_only_set, parent=None):
        super().__init__(parent)
        self.read_only_files = {os.path.normcase(os.path.abspath(p)) for p in read_only_set}

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        value = super().data(index, role)
        if role == Qt.ItemDataRole.FontRole and not self.isDir(index):
            file_path = os.path.normcase(os.path.abspath(self.filePath(index)))
            if file_path in self.read_only_files:
                font = QFont()
                if isinstance(value, QFont): font = value
                font.setBold(True)
                return font
        return value

    def update_item(self, file_path):
        norm_path = os.path.normcase(os.path.abspath(file_path))
        index = self.index(norm_path)
        index_orig = self.index(file_path)
        if index_orig.isValid(): self.dataChanged.emit(index_orig, index_orig, [Qt.ItemDataRole.FontRole])
        elif index.isValid(): self.dataChanged.emit(index, index, [Qt.ItemDataRole.FontRole])

# --- カスタム QTreeView クラス ---
class CustomTreeView(QTreeView):
    emptyAreaDoubleClicked = pyqtSignal()

    def mouseDoubleClickEvent(self, event):
        index = self.indexAt(event.pos())
        if not index.isValid() and event.button() == Qt.MouseButton.LeftButton:
            print("CustomTreeView: 空白領域ダブルクリック検知、シグナル発行")
            self.emptyAreaDoubleClicked.emit()
        else:
            super().mouseDoubleClickEvent(event)

# --- CustomTabBar クラス ---
class CustomTabBar(QTabBar):
    plusTabClicked = pyqtSignal()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        tab_widget = self.parentWidget()
        if isinstance(tab_widget, QTabWidget):
            count = tab_widget.count()
            plus_tab_index = -1
            for i in range(count):
                widget = tab_widget.widget(i)
                if widget and widget.property(PLUS_TAB_PROPERTY):
                    plus_tab_index = i
                    break
            scrollable_count = count - 1 if plus_tab_index != -1 else count
            if scrollable_count <= 1:
                event.accept()
                return
            current_index = tab_widget.currentIndex()
            next_index = current_index
            if delta > 0:
                next_index = current_index - 1
            elif delta < 0:
                next_index = current_index + 1
            else:
                event.accept()
                return
            if next_index < 0:
                next_index = scrollable_count - 1
            elif next_index >= scrollable_count:
                next_index = 0
            if plus_tab_index == -1 or next_index < plus_tab_index:
                tab_widget.setCurrentIndex(next_index)
        event.accept()

    def mousePressEvent(self, event):
        pos = event.pos()
        index = self.tabAt(pos)
        if index != -1:
            tab_widget = self.parentWidget()
            if isinstance(tab_widget, QTabWidget):
                widget = tab_widget.widget(index)
                if widget and widget.property(PLUS_TAB_PROPERTY):
                    if event.button() == Qt.MouseButton.LeftButton:
                        print("+タブがクリックされました。plusTabClickedシグナルを発行します。")
                        self.plusTabClicked.emit()
                        event.accept()
                        return
        super().mousePressEvent(event)

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
            # 1から始まる番号表示（10は0として表示）
            display_num = i + 1 if i < 9 else 0
            form_layout.addRow(f"Ctrl+W→{display_num}:", text_input)

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
