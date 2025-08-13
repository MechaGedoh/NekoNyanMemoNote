# -*- coding: utf-8 -*-

import os
import shutil
import traceback
import time
from pathlib import Path
from PyQt6.QtWidgets import QMessageBox, QInputDialog, QLineEdit
from PyQt6.QtCore import QThread, QObject, pyqtSignal, QTimer, QMutex, QMutexLocker

from .constants import APP_DATA_BASE_DIR, ENABLE_DEBUG_OUTPUT, ENABLE_ASYNC_PERFORMANCE_MONITORING
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

def validate_windows_filename(filename):
    """
    Windowsファイル名のバリデーション
    
    Args:
        filename (str): 検証するファイル名
        
    Returns:
        tuple: (is_valid: bool, error_message: str)
    """
    if not filename:
        return False, "ファイル名が空です"
    
    # 無効文字チェック
    invalid_chars = '\\/:*?"<>|'
    if any(char in filename for char in invalid_chars):
        return False, f"名前に使用できない文字が含まれています: {invalid_chars}"
    
    # Windows予約名チェック
    windows_reserved = {
        'CON', 'PRN', 'AUX', 'NUL',
        'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
        'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
    }
    
    # ファイル名の基本部分（拡張子を除く）を取得
    base_name = filename.upper()
    if '.' in base_name:
        base_name = base_name.split('.')[0]
    
    if base_name in windows_reserved:
        return False, f"'{filename}' はWindowsの予約名のため使用できません"
    
    # 末尾のドットや空白チェック
    if filename.endswith('.') or filename.endswith(' '):
        return False, "ファイル名の末尾にドット（.）や空白を使用することはできません"
    
    # 先頭の空白チェック
    if filename.startswith(' '):
        return False, "ファイル名の先頭に空白を使用することはできません"
    
    # 長さ制限チェック（Windows NTFS制限）
    if len(filename) > 255:
        return False, "ファイル名が長すぎます（255文字まで）"
    
    return True, ""

BASE_MEMO_DIR = get_safe_path(APP_DATA_BASE_DIR, "PyMemoNoteData")

# --- 非同期ファイルI/O操作クラス ---

class FileIOWorker(QObject):
    """ファイルI/O操作を非同期で実行するワーカークラス（完全版）"""
    
    # シグナル定義（出力用）
    content_loaded = pyqtSignal(str, str)  # file_path, content
    content_saved = pyqtSignal(str, bool)  # file_path, success
    file_created = pyqtSignal(str, bool)   # file_path, success
    chunk_loaded = pyqtSignal(str, str, int, int)  # file_path, chunk_content, current_pos, total_size
    streaming_completed = pyqtSignal(str)  # file_path
    progress_updated = pyqtSignal(str, int, int)  # file_path, current, total
    error_occurred = pyqtSignal(str, str, str)  # operation, file_path, error_message
    
    # スロット定義（入力用）
    load_requested = pyqtSignal(str)  # file_path
    save_requested = pyqtSignal(str, str)  # file_path, content
    streaming_requested = pyqtSignal(str)  # file_path
    
    def __init__(self):
        super().__init__()
        self.mutex = QMutex()
        self.chunk_size = 64 * 1024  # 64KB チャンクサイズ
        self.large_file_threshold = 512 * 1024  # 512KB以上でストリーミング読み込み（改善）
        self.max_chunk_size = 256 * 1024  # 最大チャンクサイズ（256KB）
        self.min_chunk_size = 16 * 1024   # 最小チャンクサイズ（16KB）
        
        # 進行中のファイル操作を管理
        self._active_operations = set()
        self._canceled_operations = set()
        
        # 停止フラグ（重要な追加）
        self._stop_requested = False
        
        # 内部シグナル・スロット接続
        self.load_requested.connect(self.load_file_async)
        self.save_requested.connect(self.save_file_async)
        self.streaming_requested.connect(self.load_file_streaming)
    
    # シグナル追加
    finished = pyqtSignal()  # 停止完了シグナル
    
    def request_stop(self):
        """停止要求"""
        print("DEBUG: FileIOWorker 停止要求を受信")
        self._stop_requested = True
        # 進行中の操作をキャンセル
        self._canceled_operations.update(self._active_operations)
        # finished.emit()は実際に停止した時に呼ぶ（ここでは呼ばない）
        
        # アクティブな操作がない場合は即座に終了
        if not self._active_operations:
            print("DEBUG: アクティブな操作がないため即座に終了")
            self.finished.emit()
    
    def _check_and_emit_finished(self):
        """停止要求があり、全ての操作が完了した場合にfinishedを発火"""
        if self._stop_requested and not self._active_operations:
            print("DEBUG: 全ての操作が完了、finished信号を発火")
            self.finished.emit()
    
    def load_file_async(self, file_path):
        """ファイルを非同期で読み込み（パフォーマンス監視付き）"""
        start_time = time.time() if ENABLE_ASYNC_PERFORMANCE_MONITORING else None
        
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
                    # エンコーディング警告は別途処理
                    self.error_occurred.emit("encoding_warning", file_path, "CP932として読み込まれました")
            
            # パフォーマンス監視
            if ENABLE_ASYNC_PERFORMANCE_MONITORING and start_time:
                elapsed_time = time.time() - start_time
                file_size = len(content.encode('utf-8'))
                print(f"⚡ 非同期読み込み完了: {os.path.basename(file_path)} "
                      f"({file_size:,} bytes, {elapsed_time:.3f}s)")
            
            self.content_loaded.emit(file_path, content)
            
        except FileNotFoundError:
            self.error_occurred.emit("load", file_path, "ファイルが見つかりません")
        except PermissionError:
            self.error_occurred.emit("load", file_path, "ファイルを読み込む権限がありません")
        except Exception as e:
            self.error_occurred.emit("load", file_path, f"読み込みエラー: {str(e)}")
    
    def save_file_async(self, file_path, content):
        """ファイルを非同期で保存（強化版）"""
        operation_id = f"async_save_{file_path}"
        
        # キャンセルチェックと操作登録のみロック
        with QMutexLocker(self.mutex):
            if operation_id in self._canceled_operations:
                self._canceled_operations.discard(operation_id)
                return
            
            self._active_operations.add(operation_id)
        
        try:
            start_time = time.time() if ENABLE_ASYNC_PERFORMANCE_MONITORING else None
            
            # ディレクトリ確認・作成
            dir_path = os.path.dirname(file_path)
            if not os.path.exists(dir_path):
                os.makedirs(dir_path)
            
            # バックアップファイル作成（既存ファイルがある場合）
            backup_path = None
            if os.path.exists(file_path):
                backup_path = file_path + ".backup"
                try:
                    shutil.copy2(file_path, backup_path)
                except Exception as e:
                    print(f"バックアップ作成に失敗: {e}")
            
            # 大容量ファイル用のチャンク保存
            content_size = len(content.encode('utf-8'))
            if content_size > self.large_file_threshold:
                self._save_file_chunked(file_path, content, operation_id)
            else:
                # 通常の一括保存
                with open(file_path, 'w', encoding='utf-8-sig') as f:
                    f.write(content)
            
            # バックアップファイル削除
            if backup_path and os.path.exists(backup_path):
                try:
                    os.remove(backup_path)
                except Exception as e:
                    print(f"バックアップファイル削除に失敗: {e}")
            
            # パフォーマンス監視
            if ENABLE_ASYNC_PERFORMANCE_MONITORING and start_time:
                elapsed_time = time.time() - start_time
                throughput = content_size / elapsed_time / 1024 / 1024  # MB/s
                print(f"💾 非同期保存完了: {os.path.basename(file_path)} "
                      f"({content_size:,} bytes, {elapsed_time:.3f}s, {throughput:.2f}MB/s)")
            
            self.content_saved.emit(file_path, True)
            
            # アクティブ操作から削除（正常完了）
            operation_id = f"async_save_{file_path}"
            self._active_operations.discard(operation_id)
            self._check_and_emit_finished()
            
        except PermissionError:
            # バックアップファイル復元
            if backup_path and os.path.exists(backup_path):
                try:
                    shutil.move(backup_path, file_path)
                except Exception:
                    pass
            self.error_occurred.emit("save", file_path, "ファイルを保存する権限がありません")
            self.content_saved.emit(file_path, False)
        except OSError as e:
            # バックアップファイル復元
            if backup_path and os.path.exists(backup_path):
                try:
                    shutil.move(backup_path, file_path)
                except Exception:
                    pass
            self.error_occurred.emit("save", file_path, f"保存エラー: {str(e)}")
            self.content_saved.emit(file_path, False)
        finally:
            # 操作完了の登録もロック
            with QMutexLocker(self.mutex):
                self._active_operations.discard(operation_id)
                # 停止要求がある場合の最終チェック
                self._check_and_emit_finished()
    
    def _save_file_chunked(self, file_path, content, operation_id):
        """大容量ファイルをチャンクに分けて保存（バイナリベース）"""
        # コンテンツをUTF-8バイトデータに変換
        content_bytes = content.encode('utf-8-sig')
        total_bytes = len(content_bytes)
        current_pos = 0
        
        with open(file_path, 'wb') as f:
            while current_pos < total_bytes:
                if operation_id in self._canceled_operations:
                    self._canceled_operations.discard(operation_id)
                    break
                
                end_pos = min(current_pos + self.chunk_size, total_bytes)
                chunk_bytes = content_bytes[current_pos:end_pos]
                f.write(chunk_bytes)
                
                current_pos = end_pos
                self.progress_updated.emit(file_path, current_pos, total_bytes)
                
                # 停止要求チェック
                if self._stop_requested or QThread.currentThread().isInterruptionRequested():
                    print("DEBUG: ファイル保存処理が中断されました")
                    # アクティブ操作から削除
                    operation_id = f"async_save_{file_path}"
                    self._active_operations.discard(operation_id)
                    self._check_and_emit_finished()
                    return
                
                # UI応答性のため少し待機
                QThread.msleep(1)
    
    def create_file_async(self, file_path):
        """ファイルを非同期で作成"""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write("")
            self.file_created.emit(file_path, True)
            
        except PermissionError:
            self.error_occurred.emit("create", file_path, "ファイルを作成する権限がありません")
            self.file_created.emit(file_path, False)
        except OSError as e:
            self.error_occurred.emit("create", file_path, f"作成エラー: {str(e)}")
            self.file_created.emit(file_path, False)
    
    def _get_optimal_chunk_size(self, file_size):
        """ファイルサイズに応じた最適なチャンクサイズを計算"""
        if file_size < 1024 * 1024:  # 1MB未満
            return self.min_chunk_size
        elif file_size < 10 * 1024 * 1024:  # 10MB未満
            return self.chunk_size
        else:  # 10MB以上
            return self.max_chunk_size
    
    def cancel_operation(self, file_path):
        """ファイル操作のキャンセル"""
        # 保存・読み込み両方の operation_id を追加
        save_operation_id = f"async_save_{file_path}"
        load_operation_id = f"stream_load_{file_path}"
        
        self._canceled_operations.add(file_path)  # 互換性のため
        self._canceled_operations.add(save_operation_id)
        self._canceled_operations.add(load_operation_id)
    
    def load_file_streaming(self, file_path):
        """大容量ファイルをストリーミングで読み込み（強化版）"""
        operation_id = f"stream_load_{file_path}"
        
        # キャンセルチェックと操作登録のみロック
        with QMutexLocker(self.mutex):
            if operation_id in self._canceled_operations:
                self._canceled_operations.discard(operation_id)
                return
            
            self._active_operations.add(operation_id)
        
        try:
            start_time = time.time() if ENABLE_ASYNC_PERFORMANCE_MONITORING else None
            
            # ファイルサイズをチェック
            file_size = os.path.getsize(file_path)
            
            if file_size <= self.large_file_threshold:
                # 小さいファイルは通常読み込み（操作を削除してから）
                with QMutexLocker(self.mutex):
                    self._active_operations.discard(operation_id)
                self.load_file_async(file_path)
                return
            
            # 最適なチャンクサイズを決定
            optimal_chunk_size = self._get_optimal_chunk_size(file_size)
            
            # ストリーミング読み込み
            encoding_used = 'utf-8-sig'
            chunks_processed = 0
            
            try:
                with open(file_path, 'r', encoding=encoding_used) as f:
                    while True:
                        # キャンセルチェック
                        if operation_id in self._canceled_operations:
                            self._canceled_operations.discard(operation_id)
                            break
                        
                        # バイナリファイルでファイル位置を取得（正確な進捗計算）
                        current_pos = f.tell()
                        if current_pos >= file_size:
                            break
                        
                        chunk = f.read(optimal_chunk_size // 4)  # 文字単位のため4で割る（UTF-8想定）
                        if not chunk:
                            break
                        
                        # ファイル位置を再取得（読み込み後の正確な位置）
                        new_pos = f.tell()
                        self.chunk_loaded.emit(file_path, chunk, current_pos, file_size)
                        self.progress_updated.emit(file_path, new_pos, file_size)
                        chunks_processed += 1
                        
                        # 停止要求チェック
                        if self._stop_requested or QThread.currentThread().isInterruptionRequested():
                            print("DEBUG: ファイル読み込み処理が中断されました")
                            # アクティブ操作から削除
                            operation_id = f"async_load_{file_path}"
                            self._active_operations.discard(operation_id)
                            self._check_and_emit_finished()
                            return
                        
                        # 大容量ファイルでは適度に待機（UI応答性向上）
                        if chunks_processed % 10 == 0:
                            QThread.msleep(2)
                        else:
                            QThread.msleep(1)
                
                # パフォーマンス監視
                if ENABLE_ASYNC_PERFORMANCE_MONITORING and start_time:
                    elapsed_time = time.time() - start_time
                    throughput = file_size / elapsed_time / 1024 / 1024  # MB/s
                    print(f"⚡ ストリーミング読み込み完了: {os.path.basename(file_path)} "
                          f"({file_size:,} bytes, {elapsed_time:.3f}s, {throughput:.2f}MB/s)")
                
                self.streaming_completed.emit(file_path)
                
            except UnicodeDecodeError:
                    # エンコーディングを変更して再試行
                    encoding_used = 'cp932'
                    
                    try:
                        with open(file_path, 'r', encoding=encoding_used, errors='replace') as f:
                            while True:
                                if operation_id in self._canceled_operations:
                                    self._canceled_operations.discard(operation_id)
                                    break
                                
                                # ファイル位置を取得（正確な進捗計算）
                                current_pos = f.tell()
                                if current_pos >= file_size:
                                    break
                                
                                chunk = f.read(optimal_chunk_size // 4)
                                if not chunk:
                                    break
                                
                                # ファイル位置を再取得（読み込み後の正確な位置）
                                new_pos = f.tell()
                                self.chunk_loaded.emit(file_path, chunk, current_pos, file_size)
                                self.progress_updated.emit(file_path, new_pos, file_size)
                                
                                # 停止要求チェック
                                if self._stop_requested or QThread.currentThread().isInterruptionRequested():
                                    print("DEBUG: ストリーミング読み込み処理が中断されました")
                                    # アクティブ操作から削除
                                    operation_id = f"stream_load_{file_path}"
                                    self._active_operations.discard(operation_id)
                                    self._check_and_emit_finished()
                                    return
                                
                                QThread.msleep(1)
                            
                            self.error_occurred.emit("encoding_warning", file_path, "CP932として読み込まれました")
                            self.streaming_completed.emit(file_path)
                    
                    except Exception:
                        self.error_occurred.emit("stream", file_path, "エンコーディングエラー")
                
        except FileNotFoundError:
            self.error_occurred.emit("stream", file_path, "ファイルが見つかりません")
        except PermissionError:
            self.error_occurred.emit("stream", file_path, "ファイルを読み込む権限がありません")
        except Exception as e:
            self.error_occurred.emit("stream", file_path, f"ストリーミング読み込みエラー: {str(e)}")
        finally:
            # 操作完了の登録もロック
            with QMutexLocker(self.mutex):
                self._active_operations.discard(operation_id)
    
    def get_file_size(self, file_path):
        """ファイルサイズを取得"""
        try:
            return os.path.getsize(file_path)
        except (FileNotFoundError, PermissionError, OSError):
            return 0


class AsyncFileSystemManager(IFileSystemManager):
    """非同期ファイルI/O機能を持つファイルシステムマネージャー"""
    
    # シグナル定義
    content_loaded = pyqtSignal(str, str)  # file_path, content
    content_saved = pyqtSignal(str, bool)  # file_path, success
    file_created = pyqtSignal(str, bool)   # file_path, success
    chunk_loaded = pyqtSignal(str, str, int, int)  # file_path, chunk_content, current_pos, total_size
    streaming_completed = pyqtSignal(str)  # file_path
    error_occurred = pyqtSignal(str, str, str)  # operation, file_path, error_message
    
    def __init__(self, parent_widget=None):
        super().__init__()
        self.parent = parent_widget
        
        # ワーカースレッドの設定
        self.worker_thread = QThread()
        self.worker_thread.setObjectName("AsyncFileIOWorkerThread")  # スレッド名を設定
        self.worker = FileIOWorker()
        self.worker.moveToThread(self.worker_thread)
        
        # シグナル接続
        self.worker.content_loaded.connect(self.content_loaded.emit)
        self.worker.content_saved.connect(self.content_saved.emit)
        self.worker.file_created.connect(self.file_created.emit)
        self.worker.chunk_loaded.connect(self.chunk_loaded.emit)
        self.worker.streaming_completed.connect(self.streaming_completed.emit)
        self.worker.progress_updated.connect(lambda f, c, t: None)  # プログレス更新シグナル
        self.worker.error_occurred.connect(self._handle_error)
        
        # スレッド開始
        self.worker_thread.start()
    
    def _handle_error(self, operation, file_path, error_message):
        """エラーハンドリング"""
        self.error_occurred.emit(operation, file_path, error_message)
        
        if operation == "encoding_warning":
            QMessageBox.warning(
                self.parent, 
                strings.TITLE_ENCODING_WARNING, 
                f"ファイルを CP932 (Shift-JIS) として読み込みました。文字化けしている可能性があります。UTF-8 で保存し直すことを推奨します。{file_path}"
            )
        elif operation == "load":
            if "権限" in error_message:
                QMessageBox.critical(self.parent, "権限エラー", f"メモファイル '{os.path.basename(file_path)}' を{error_message}")
            else:
                QMessageBox.critical(self.parent, strings.TITLE_READ_ERROR, f"メモ '{os.path.basename(file_path)}' を読み込めませんでした。\n{error_message}")
        elif operation == "save":
            if "権限" in error_message:
                QMessageBox.critical(self.parent, "権限エラー", f"メモを{error_message}")
            else:
                QMessageBox.critical(self.parent, "OSエラー", f"メモを保存できませんでした。\n{error_message}")
        elif operation == "create":
            if "権限" in error_message:
                QMessageBox.warning(self.parent, "権限エラー", f"メモファイルを{error_message}")
            else:
                QMessageBox.warning(self.parent, "OSエラー", f"メモファイルを作成できませんでした。\n{error_message}")
    
    def load_memo_content_async(self, file_path):
        """メモ内容を非同期で読み込み"""
        QTimer.singleShot(0, lambda: self.worker.load_file_async(file_path))
    
    def save_memo_content_async(self, file_path, content):
        """メモ内容を非同期で保存"""
        QTimer.singleShot(0, lambda: self.worker.save_file_async(file_path, content))
    
    def create_memo_file_async(self, file_path):
        """メモファイルを非同期で作成"""
        QTimer.singleShot(0, lambda: self.worker.create_file_async(file_path))
    
    def load_memo_content_streaming(self, file_path):
        """メモ内容をストリーミングで読み込み"""
        QTimer.singleShot(0, lambda: self.worker.load_file_streaming(file_path))
    
    def get_file_size(self, file_path):
        """ファイルサイズを取得（同期処理）"""
        try:
            return os.path.getsize(file_path)
        except Exception as e:
            print(f"ファイルサイズ取得エラー: {e}")
            return 0
    
    def cleanup(self):
        """リソースクリーンアップ"""
        print("DEBUG: AsyncFileSystemManager クリーンアップ開始")
        
        if hasattr(self, 'worker_thread') and self.worker_thread:
            try:
                if self.worker_thread.isRunning():
                    print("DEBUG: AsyncFileIOWorker スレッドを停止中...")
                    
                    # スレッドの正常終了を待機
                    self.worker_thread.quit()
                    if self.worker_thread.wait(3000):  # 3秒待機
                        print("DEBUG: AsyncFileIOWorker スレッドが正常終了")
                    else:
                        print("WARNING: AsyncFileIOWorker スレッドを強制終了中...")
                        self.worker_thread.terminate()
                        if self.worker_thread.wait(1000):
                            print("DEBUG: AsyncFileIOWorker スレッドを強制終了完了")
                        else:
                            print("ERROR: AsyncFileIOWorker スレッドの強制終了に失敗")
                else:
                    print("DEBUG: AsyncFileIOWorker スレッドは既に停止済み")
                    
            except Exception as e:
                print(f"AsyncFileIOWorker スレッド停止エラー: {e}")
            finally:
                # リソース解放
                if hasattr(self, 'worker_thread'):
                    self.worker_thread.deleteLater()
                    self.worker_thread = None
                print("DEBUG: AsyncFileSystemManager クリーンアップ完了")
    
    # IFileSystemManagerの抽象メソッド実装
    def create_new_folder(self, current_folder_path: str, default_name: str = "新規フォルダ") -> str:
        """新しいフォルダの作成（委譲処理）"""
        # 実際の処理は別途実装するか、FileSystemManagerに委譲
        return None
    
    def create_new_memo(self, current_folder_path: str, default_name: str = "新規メモ") -> str:
        """新しいメモファイルの作成（委譲処理）"""
        # 実際の処理は別途実装するか、FileSystemManagerに委譲
        return None
    
    def load_memo_content(self, file_path: str, force_sync: bool = False) -> str:
        """メモ内容を読み込み（同期処理）"""
        # 同期処理で直接ファイル内容を返す
        try:
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                return f.read()
        except UnicodeDecodeError:
            # CP932で再試行
            with open(file_path, 'r', encoding='cp932', errors='replace') as f:
                return f.read()
        except Exception as e:
            print(f"ファイル読み込みエラー: {e}")
            return ""
    
    def save_memo_content(self, file_path: str, content: str, force_sync: bool = False) -> bool:
        """メモ内容を保存（同期処理）"""
        # 同期処理で直接ファイル保存
        try:
            # ディレクトリ確認・作成
            dir_path = os.path.dirname(file_path)
            if not os.path.exists(dir_path):
                os.makedirs(dir_path)
            
            with open(file_path, 'w', encoding='utf-8-sig') as f:
                f.write(content)
            return True
        except Exception as e:
            print(f"ファイル保存エラー: {e}")
            return False

# --- ファイル・フォルダ操作 --- 

class FileSystemManager(IFileSystemManager):
    def __init__(self, parent_widget=None):
        self.parent = parent_widget
        
        # シンプルな同期処理のみ使用（QThreadエラー回避）
        print("DEBUG: FileSystemManager - QThreadを使用しない同期版で初期化")
        self.worker_thread = None  # QThreadを作らない
        self.worker = None  # Workerも作らない
        
        # コールバック管理
        self._load_callbacks = {}
        self._save_callbacks = {}
        
        # QThreadを使わないため、シグナル接続は不要
        # self.worker.content_loaded.connect(self._on_content_loaded)
        # self.worker.content_saved.connect(self._on_content_saved)
        # self.worker.chunk_loaded.connect(self._on_chunk_loaded)
        # self.worker.streaming_completed.connect(self._on_streaming_completed)
        # self.worker.progress_updated.connect(lambda f, c, t: None)  # プログレス更新シグナル
        
        # QThreadを使わないため、終了処理設定は不要
        # self.worker.finished.connect(self.worker_thread.quit)
        # self.worker.finished.connect(self.worker.deleteLater)
        # self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        
        # QThreadを使わないため、スレッド開始は不要
        # self.worker_thread.start()
        self._streaming_callbacks = {}
        
        # ストリーミング読み込み用バッファ
        self._streaming_buffers = {}
        
        # シグナル接続は既に上で実施済み
    
    def _on_content_loaded(self, file_path, content):
        """非同期読み込み完了時のコールバック"""
        callback = self._load_callbacks.pop(file_path, None)
        if callback:
            callback(content)
    
    def _on_content_saved(self, file_path, success):
        """非同期保存完了時のコールバック"""
        callback = self._save_callbacks.pop(file_path, None)
        if callback:
            callback(success)
    
    def _on_chunk_loaded(self, file_path, chunk_content, current_pos, total_size):
        """ストリーミング読み込みチャンク受信時のコールバック"""
        if file_path not in self._streaming_buffers:
            self._streaming_buffers[file_path] = ""
        
        self._streaming_buffers[file_path] += chunk_content
        
        # プログレス情報を提供
        callback = self._streaming_callbacks.get(file_path)
        if callback and hasattr(callback, '__call__'):
            # コールバックが呼び出し可能で、引数が3つ以上受け入れられる場合
            try:
                callback(chunk_content, current_pos, total_size)
            except TypeError:
                # 引数数が合わない場合は従来の方式
                callback(chunk_content)
    
    def _on_streaming_completed(self, file_path):
        """ストリーミング読み込み完了時のコールバック"""
        complete_content = self._streaming_buffers.pop(file_path, "")
        callback = self._streaming_callbacks.pop(file_path, None)
        
        if callback:
            if hasattr(callback, '__call__'):
                try:
                    # 完了時は完全なコンテンツを渡す
                    callback(complete_content, -1, -1)  # -1, -1 で完了を示す
                except TypeError:
                    callback(complete_content)

    def create_new_folder(self, default_name="新しいフォルダ", use_default_on_empty=False):
        folder_name, ok = QInputDialog.getText(self.parent, strings.TITLE_NEW_FOLDER, strings.MSG_INPUT_FOLDER_NAME, QLineEdit.EchoMode.Normal, default_name)
        if ok:
            input_name = folder_name.strip()
            base_folder_name = default_name if not input_name and use_default_on_empty else input_name if input_name else None
            if not base_folder_name:
                QMessageBox.warning(self.parent, strings.TITLE_ERROR, strings.MSG_FOLDER_NAME_EMPTY)
                return None, None
            # 新しいバリデータを使用
            is_valid, validation_error = validate_windows_filename(base_folder_name)
            if not is_valid:
                QMessageBox.warning(self.parent, strings.TITLE_ERROR, validation_error)
                return None, None
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
            # 新しいバリデータを使用（拡張子なしの名前をチェック）
            is_valid, validation_error = validate_windows_filename(base_name)
            if not is_valid:
                QMessageBox.warning(self.parent, strings.TITLE_ERROR, validation_error)
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
            # 新しいバリデータを使用
            is_valid, validation_error = validate_windows_filename(new_name)
            if not is_valid:
                QMessageBox.warning(self.parent, strings.TITLE_ERROR, validation_error)
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
            # 新しいバリデータを使用
            is_valid, validation_error = validate_windows_filename(new_name_input)
            if not is_valid:
                QMessageBox.warning(self.parent, strings.TITLE_ERROR, validation_error)
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

    def load_memo_content(self, file_path, force_sync=True):
        """メモ内容を読み込み（デフォルトは同期、必要に応じて非同期）
        
        Args:
            file_path (str): 読み込むファイルのパス
            force_sync (bool): 同期読み込みを行う場合はTrue（デフォルト）
            
        Returns:
            str or None: 同期読み込みの場合は内容、非同期の場合はNone
        """
        if force_sync:
            return self._load_memo_content_sync(file_path)
        
        # force_sync=False の場合のみ非同期読み込み
        self.load_memo_content_async(file_path)
        return None
    
    def _load_memo_content_sync(self, file_path):
        """メモ内容を同期で読み込み（内部使用）"""
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

    def save_memo_content(self, file_path, content, force_sync=True):
        """メモ内容を保存（デフォルトは同期、必要に応じて非同期）
        
        Args:
            file_path (str): 保存するファイルのパス
            content (str): 保存する内容
            force_sync (bool): 同期保存を行う場合はTrue（デフォルト）
            
        Returns:
            bool: 同期保存の場合は成功/失敗、非同期の場合は常にTrue
        """
        if force_sync:
            return self._save_memo_content_sync(file_path, content)
        
        # force_sync=False の場合のみ非同期保存
        self.save_memo_content_async(file_path, content)
        return True
    
    def _save_memo_content_sync(self, file_path, content):
        """メモ内容を同期で保存（内部使用）"""
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
    
    def load_memo_content_async(self, file_path, callback=None):
        """メモ内容を同期で読み込み（非同期メソッド名だが実際は同期）
        
        Args:
            file_path (str): 読み込むファイルのパス
            callback (callable): 読み込み完了時のコールバック関数 callback(content)
        """
        # 同期処理で直接読み込み
        content = self.load_memo_content(file_path)
        
        # コールバックがあれば実行
        if callback:
            callback(content)
    
    def save_memo_content_async(self, file_path, content, callback=None):
        """メモ内容を同期で保存（非同期メソッド名だが実際は同期）
        
        Args:
            file_path (str): 保存するファイルのパス
            content (str): 保存する内容
            callback (callable): 保存完了時のコールバック関数 callback(success)
        """
        # 同期処理で直接保存
        success = self.save_memo_content(file_path, content)
        
        # コールバックがあれば実行
        if callback:
            callback(success)
    
    def load_memo_content_streaming(self, file_path, callback=None):
        """メモ内容を同期読み込み（ストリーミング名だが実際は一括読み込み）
        
        Args:
            file_path (str): 読み込むファイルのパス
            callback (callable): チャンク受信時のコールバック関数
                                 callback(chunk_content, current_pos, total_size)
                                 完了時は callback(complete_content, -1, -1)
        """
        # 同期処理で一括読み込み
        content = self.load_memo_content(file_path)
        
        # コールバックがあれば完了として実行
        if callback:
            callback(content, -1, -1)  # 完了時の形式
    
    def get_file_size(self, file_path):
        """ファイルサイズを取得（同期処理）
        
        Args:
            file_path (str): チェックするファイルのパス
            
        Returns:
            int: ファイルサイズ（バイト）。エラーの場合は0
        """
        try:
            return os.path.getsize(file_path)
        except Exception as e:
            print(f"ファイルサイズ取得エラー: {e}")
            return 0
    
    def is_large_file(self, file_path):
        """大容量ファイルかどうか判定
        
        Args:
            file_path (str): チェックするファイルのパス
            
        Returns:
            bool: 512KB以上の場合True（改善）
        """
        return self.get_file_size(file_path) >= (512 * 1024)
    
    def cancel_file_operation(self, file_path):
        """進行中のファイル操作をキャンセル（同期版では不要）
        
        Args:
            file_path (str): キャンセルするファイルのパス
        """
        # 同期処理のため、キャンセルする操作はない
        print(f"DEBUG: cancel_file_operation called for {file_path} (同期版では不要)")
    
    def get_active_operations(self):
        """進行中の操作一覧を取得（同期版では常に空）
        
        Returns:
            set: 進行中の操作ID
        """
        # 同期処理のため、常に空のセットを返す
        return set()
    
    def get_file_load_strategy(self, file_path):
        """ファイル読み込み戦略を判定
        
        Args:
            file_path (str): チェックするファイルのパス
            
        Returns:
            str: 'sync' | 'async' | 'streaming'
        """
        if not os.path.exists(file_path):
            return 'sync'  # 存在しないファイル
        
        file_size = self.get_file_size(file_path)
        
        if file_size < 64 * 1024:  # 64KB未満
            return 'sync'
        elif file_size < 512 * 1024:  # 512KB未満
            return 'async'
        else:  # 512KB以上
            return 'streaming'
    
    def auto_load_memo_content(self, file_path, callback=None):
        """ファイルサイズに応じて最適な方法で読み込み
        
        Args:
            file_path (str): 読み込むファイルのパス
            callback (callable): 読み込み完了時のコールバック関数
        """
        strategy = self.get_file_load_strategy(file_path)
        
        if strategy == 'sync':
            # 同期読み込み
            content = self.load_memo_content(file_path, force_sync=True)
            if callback:
                callback(content, -1, -1)  # 完了時の形式
        elif strategy == 'async':
            # 非同期読み込み
            def async_callback(content):
                if callback:
                    callback(content, -1, -1)  # 完了時の形式
            self.load_memo_content_async(file_path, async_callback)
        else:
            # ストリーミング読み込み
            self.load_memo_content_streaming(file_path, callback)
    
    def cleanup(self):
        """リソースクリーンアップ（同期版）"""
        print("DEBUG: FileSystemManager クリーンアップ開始（同期版）")
        
        # QThreadを使わないので、特にクリーンアップするものはない
        if hasattr(self, '_load_callbacks'):
            self._load_callbacks.clear()
        if hasattr(self, '_save_callbacks'):
            self._save_callbacks.clear()
        if hasattr(self, '_streaming_callbacks'):
            self._streaming_callbacks.clear()
        if hasattr(self, '_streaming_buffers'):
            self._streaming_buffers.clear()
            
        print("DEBUG: FileSystemManager クリーンアップ完了（同期版）")
    
    def _cancel_all_operations(self):
        """実行中の操作をすべてキャンセル"""
        try:
            if hasattr(self, 'worker') and self.worker:
                # 進行中の操作があれば停止フラグを設定
                if hasattr(self.worker, '_stop_requested'):
                    self.worker._stop_requested = True
                # キャンセル可能な操作を停止
                for file_path in list(self._load_callbacks.keys()):
                    self.cancel_operation(file_path)
                print("DEBUG: すべての操作をキャンセルしました")
        except Exception as e:
            print(f"操作キャンセルエラー: {e}")
