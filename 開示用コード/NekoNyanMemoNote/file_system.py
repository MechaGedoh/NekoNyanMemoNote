# -*- coding: utf-8 -*-

import os
import shutil
import traceback
from pathlib import Path
from PyQt6.QtWidgets import QMessageBox, QInputDialog, QLineEdit

from .constants import APP_DATA_BASE_DIR, ENABLE_DEBUG_OUTPUT
from . import strings
from .interfaces import IFileSystemManager

# --- ヘルパー関数 ---
def get_safe_path(base_path, relative_path):
    """
    パストラバーサル攻撃を防ぐためのセキュアなパス結合
    """
    try:
        base = Path(base_path).resolve()
        target = (base / relative_path).resolve()
        target.relative_to(base)
        return str(target)
    except (ValueError, OSError):
        raise ValueError(f"不正なパスが指定されました: {relative_path}")

def normalize_path_for_comparison(path):
    """
    パス比較用の正規化（大文字小文字を統一）
    Windowsでは大文字小文字を区別しないため、比較用のみに使用
    """
    return os.path.normcase(os.path.abspath(path))

def safe_error_message(user_message, technical_details=""):
    """
    セキュアなエラーメッセージを生成
    本番環境では技術的詳細を隠す
    """
    if ENABLE_DEBUG_OUTPUT:
        return f"{user_message}\n\n詳細情報:\n{technical_details}" if technical_details else user_message
    else:
        return user_message

BASE_MEMO_DIR = get_safe_path(APP_DATA_BASE_DIR, "PyMemoNoteData")

# --- ファイル・フォルダ操作 --- 

class FileSystemManager(IFileSystemManager):
    def __init__(self, parent_widget=None):
        self.parent = parent_widget

    def create_new_folder(self, default_name="新しいフォルダ", use_default_on_empty=False):
        folder_name, ok = QInputDialog.getText(self.parent, strings.TITLE_NEW_FOLDER, strings.MSG_INPUT_FOLDER_NAME, QLineEdit.EchoMode.Normal, default_name)
        if ok:
            input_name = folder_name.strip()
            base_folder_name = default_name if not input_name and use_default_on_empty else input_name if input_name else None
            if not base_folder_name:
                QMessageBox.warning(self.parent, strings.TITLE_ERROR, strings.MSG_FOLDER_NAME_EMPTY)
                return None, None
            invalid_chars = '\\/:*?"<>|'
            if any(char in base_folder_name for char in invalid_chars):
                QMessageBox.warning(self.parent, strings.TITLE_ERROR, f"名前に使用できない文字が含まれています: {invalid_chars}")
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
                return final_folder_name, new_folder_path
            except PermissionError as e:
                error_msg = safe_error_message(
                    f"フォルダ '{final_folder_name}' を作成する権限がありません。",
                    f"エラー詳細: {e}\n{traceback.format_exc()}"
                )
                print(f"!!! ERROR: {error_msg}")
                QMessageBox.warning(self.parent, "権限エラー", error_msg)
            except FileExistsError as e:
                error_msg = safe_error_message(
                    f"フォルダまたは同名のファイルが既に存在します: '{final_folder_name}'",
                    f"エラー詳細: {e}\n{traceback.format_exc()}"
                )
                print(f"!!! ERROR: {error_msg}")
                QMessageBox.warning(self.parent, strings.TITLE_CREATION_ERROR, error_msg)
            except OSError as e:
                error_msg = safe_error_message(
                    f"フォルダ '{final_folder_name}' を作成できませんでした。OSエラーが発生しました。",
                    f"エラー詳細: {e}\n{traceback.format_exc()}"
                )
                print(f"!!! ERROR: {error_msg}")
                QMessageBox.warning(self.parent, "OSエラー", error_msg)
        return None, None

    def create_new_memo(self, current_folder_path, default_name="新規メモ"):
        if not current_folder_path:
            QMessageBox.warning(self.parent, strings.TITLE_ERROR, strings.MSG_SELECT_FOLDER_FOR_MEMO)
            return None
        memo_name, ok = QInputDialog.getText(self.parent, strings.TITLE_NEW_MEMO, strings.MSG_INPUT_MEMO_NAME, QLineEdit.EchoMode.Normal, default_name)
        if ok:
            input_name = memo_name.strip()
            base_name = input_name if input_name else default_name
            invalid_chars = '\\/:*?"<>|'
            if any(char in base_name for char in invalid_chars):
                QMessageBox.warning(self.parent, strings.TITLE_ERROR, f"名前に使用できない文字が含まれています: {invalid_chars}")
                return None
            if not base_name.lower().endswith(".txt"): 
                final_file_name_base = base_name
                final_file_name = f"{final_file_name_base}.txt"
            else: 
                final_file_name_base = base_name[:-4]
                final_file_name = base_name
            new_file_path = os.path.abspath(os.path.join(current_folder_path, final_file_name))
            counter = 0
            while os.path.exists(new_file_path):
                counter += 1
                final_file_name = f"{final_file_name_base}_{counter}.txt"
                new_file_path = os.path.abspath(os.path.join(current_folder_path, final_file_name))
            try:
                with open(new_file_path, 'w', encoding='utf-8') as f: f.write("")
                return new_file_path
            except PermissionError as e:
                error_msg = safe_error_message(
                    f"メモファイル '{final_file_name}' を作成する権限がありません。",
                    f"エラー詳細: {e}\n{traceback.format_exc()}"
                )
                print(f"!!! ERROR: {error_msg}")
                QMessageBox.warning(self.parent, "権限エラー", error_msg)
            except OSError as e:
                error_msg = safe_error_message(
                    f"メモファイル '{final_file_name}' を作成できませんでした。OSエラーが発生しました。",
                    f"エラー詳細: {e}\n{traceback.format_exc()}"
                )
                print(f"!!! ERROR: {error_msg}")
                QMessageBox.warning(self.parent, "OSエラー", error_msg)
        return None

    def rename_folder(self, old_folder_path, old_name):
        new_name, ok = QInputDialog.getText(self.parent, "フォルダ名を変更", "新しいフォルダ名:", QLineEdit.EchoMode.Normal, old_name)
        if ok and new_name.strip() and new_name != old_name:
            new_name = new_name.strip()
            invalid_chars = '\\/:*?"<>|'
            if any(char in new_name for char in invalid_chars):
                QMessageBox.warning(self.parent, strings.TITLE_ERROR, f"名前に使用できない文字が含まれています: {invalid_chars}")
                return None, None
            new_folder_path = os.path.abspath(os.path.join(BASE_MEMO_DIR, new_name))
            if not os.path.exists(new_folder_path):
                try:
                    os.rename(old_folder_path, new_folder_path)
                    return new_name, new_folder_path
                except PermissionError as e:
                    error_msg = safe_error_message("フォルダ名の変更に必要な権限がありません。", f"エラー詳細: {e}\n{traceback.format_exc()}")
                    print(f"!!! ERROR: {error_msg}")
                    QMessageBox.warning(self.parent, "権限エラー", error_msg)
                except OSError as e:
                    error_msg = safe_error_message("フォルダ名を変更できませんでした。OSエラーが発生しました。", f"エラー詳細: {e}\n{traceback.format_exc()}")
                    print(f"!!! ERROR: {error_msg}")
                    QMessageBox.warning(self.parent, "OSエラー", error_msg)
            else:
                QMessageBox.warning(self.parent, "エラー", "同じ名前のフォルダが既に存在します。")
        elif ok and not new_name.strip():
            QMessageBox.warning(self.parent, strings.TITLE_ERROR, strings.MSG_FILE_NAME_EMPTY)
        return None, None

    def delete_folder(self, folder_path, folder_name):
        msg_box = QMessageBox(self.parent)
        msg_box.setWindowTitle("フォルダの削除")
        msg_box.setText(f"フォルダ '{folder_name}' を削除しますか？")
        msg_box.setInformativeText(strings.MSG_CANNOT_UNDO + "\n" + strings.MSG_ALL_MEMOS_DELETED)
        msg_box.setIcon(QMessageBox.Icon.Warning)
        delete_button = msg_box.addButton("削除する", QMessageBox.ButtonRole.DestructiveRole)
        cancel_button = msg_box.addButton("キャンセル", QMessageBox.ButtonRole.RejectRole)
        msg_box.setDefaultButton(cancel_button)
        msg_box.exec()
        if msg_box.clickedButton() == delete_button:
            try:
                shutil.rmtree(folder_path)
                return True
            except PermissionError as e:
                error_msg = safe_error_message(
                    f"フォルダ '{folder_name}' を削除する権限がありません。",
                    f"エラー詳細: {e}\n{traceback.format_exc()}"
                )
                print(f"!!! ERROR: {error_msg}")
                QMessageBox.critical(self.parent, "権限エラー", error_msg)
            except FileNotFoundError as e:
                error_msg = safe_error_message(
                    f"削除しようとしたフォルダ '{folder_name}' が見つかりません。",
                    f"エラー詳細: {e}\n{traceback.format_exc()}"
                )
                print(f"!!! ERROR: {error_msg}")
                QMessageBox.critical(self.parent, "エラー", error_msg)
            except OSError as e:
                error_msg = safe_error_message(
                    f"フォルダ '{folder_name}' を削除できませんでした。OSエラーが発生しました。\n\nファイルが他のプログラムで使用されていないか確認してください。",
                    f"エラー詳細: {e}\n{traceback.format_exc()}"
                )
                print(f"!!! ERROR: {error_msg}")
                QMessageBox.critical(self.parent, strings.TITLE_DELETE_ERROR, error_msg)
        return False

    def rename_memo(self, old_file_path, old_name):
        folder_path = os.path.abspath(os.path.dirname(old_file_path))
        new_name, ok = QInputDialog.getText(self.parent, "メモ名を変更", "新しいメモ名:", QLineEdit.EchoMode.Normal, old_name)
        if ok and new_name.strip() and new_name != old_name:
            new_name_input = new_name.strip()
            invalid_chars = '\\/:*?"<>|'
            if any(char in new_name_input for char in invalid_chars):
                QMessageBox.warning(self.parent, strings.TITLE_ERROR, f"名前に使用できない文字が含まれています: {invalid_chars}")
                return None
            if not new_name_input.lower().endswith(".txt"): 
                new_file_name = f"{new_name_input}.txt"
            else: 
                new_file_name = new_name_input
            new_file_path = os.path.abspath(os.path.join(folder_path, new_file_name))
            if not os.path.exists(new_file_path):
                try:
                    os.rename(old_file_path, new_file_path)
                    return new_file_path
                except PermissionError as e:
                    error_msg = safe_error_message("メモ名の変更に必要な権限がありません。", f"エラー詳細: {e}\n{traceback.format_exc()}")
                    print(f"!!! ERROR: {error_msg}")
                    QMessageBox.warning(self.parent, "権限エラー", error_msg)
                except OSError as e:
                    error_msg = safe_error_message("メモ名を変更できませんでした。OSエラーが発生しました。", f"エラー詳細: {e}\n{traceback.format_exc()}")
                    print(f"!!! ERROR: {error_msg}")
                    QMessageBox.warning(self.parent, "OSエラー", error_msg)
            else:
                QMessageBox.warning(self.parent, strings.TITLE_ERROR, strings.MSG_MEMO_ALREADY_EXISTS)
        elif ok and not new_name.strip():
            QMessageBox.warning(self.parent, strings.TITLE_ERROR, strings.MSG_FILE_NAME_EMPTY)
        return None

    def delete_memo(self, file_path, file_name):
        reply = QMessageBox.question(self.parent, strings.TITLE_DELETE_MEMO, f"メモ '{file_name}' を削除しますか？\n{strings.MSG_CANNOT_UNDO}", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                return True
            except PermissionError as e:
                error_msg = safe_error_message(f"メモ '{file_name}' を削除する権限がありません。", f"エラー詳細: {e}\n{traceback.format_exc()}")
                print(f"!!! ERROR: {error_msg}")
                QMessageBox.warning(self.parent, "権限エラー", error_msg)
            except FileNotFoundError as e:
                error_msg = safe_error_message(f"削除しようとしたメモ '{file_name}' が見つかりません。", f"エラー詳細: {e}\n{traceback.format_exc()}")
                print(f"!!! ERROR: {error_msg}")
                QMessageBox.warning(self.parent, strings.TITLE_ERROR, error_msg)
            except OSError as e:
                error_msg = safe_error_message(f"メモ '{file_name}' を削除できませんでした。OSエラーが発生しました。", f"エラー詳細: {e}\n{traceback.format_exc()}")
                print(f"!!! ERROR: {error_msg}")
                QMessageBox.warning(self.parent, "OSエラー", error_msg)
        return False

    def load_memo_content(self, file_path):
        try:
            content = ""
            try:
                with open(file_path, 'r', encoding='utf-8-sig') as f:
                    content = f.read()
            except UnicodeDecodeError:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                except UnicodeDecodeError:
                    with open(file_path, 'r', encoding='cp932', errors='replace') as f:
                        content = f.read()
                    QMessageBox.warning(self.parent, strings.TITLE_ENCODING_WARNING, f"ファイルを CP932 (Shift-JIS) として読み込みました。文字化けしている可能性があります。UTF-8 で保存し直すことを推奨します。{file_path}")
            return content
        except FileNotFoundError:
            error_message = safe_error_message(f"メモファイルが見つかりません: {os.path.basename(file_path)}")
            print(f"!!! ERROR: {error_message}")
            QMessageBox.critical(self.parent, strings.TITLE_ERROR, error_message)
            return None
        except PermissionError:
            error_message = safe_error_message(f"メモファイル '{os.path.basename(file_path)}' を読み込む権限がありません。")
            print(f"!!! ERROR: {error_message}")
            QMessageBox.critical(self.parent, "権限エラー", error_message)
            return None
        except Exception as e:
            error_message = safe_error_message(f"メモ '{os.path.basename(file_path)}' を読み込めませんでした。", f"エラー詳細: {e}\n{traceback.format_exc()}")
            print(f"!!! ERROR: {error_message}")
            QMessageBox.critical(self.parent, strings.TITLE_READ_ERROR, error_message)
            return None

    def save_memo_content(self, file_path, content):
        try:
            dir_path = os.path.dirname(file_path)
            if not os.path.exists(dir_path):
                os.makedirs(dir_path)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        except PermissionError:
            error_message = safe_error_message("メモを保存する権限がありません。", f"ファイルパス: {file_path}\n{traceback.format_exc()}")
            print(f"!!! ERROR: {error_message}")
            QMessageBox.critical(self.parent, "権限エラー", error_message)
            return False
        except OSError as e:
            error_message = safe_error_message("メモを保存できませんでした。OSエラーが発生しました。", f"エラー詳細: {e}\nファイルパス: {file_path}\n{traceback.format_exc()}")
            print(f"!!! ERROR: {error_message}")
            QMessageBox.critical(self.parent, "OSエラー", error_message)
            return False
