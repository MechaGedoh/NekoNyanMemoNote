# -*- coding: utf-8 -*-

import time
from PyQt6.QtCore import QObject, pyqtSignal, QThread
from .interfaces import IHotkeyManager

try:
    from pynput import keyboard
    PYNPUT_AVAILABLE = True  # 元に戻す
except ImportError:
    PYNPUT_AVAILABLE = False

class HotkeyWorker(QThread):
    """ホットキーリスナーをQThreadで実行するワーカー"""
    
    toggle_visibility_signal = pyqtSignal()
    auto_text_signal = pyqtSignal()
    
    def __init__(self, auto_text_settings=None, parent=None):
        super().__init__(parent)
        self.setObjectName("HotkeyWorkerThread")  # スレッド名を設定
        self.auto_text_settings = auto_text_settings or {
            'enabled': False,
            'text': '',
            'hotkey': 'ctrl+shift+v'
        }
        self.hotkey_listener = None
        self._stop_requested = False
    
    def __del__(self):
        """デストラクタ - リソースの確実な解放"""
        try:
            if hasattr(self, 'hotkey_listener') and self.hotkey_listener:
                self.hotkey_listener.stop()
        except:
            pass
    
    def parse_hotkey(self, hotkey_str):
        """ホットキー文字列をパース"""
        if not PYNPUT_AVAILABLE:
            return None
            
        try:
            keys = []
            parts = hotkey_str.lower().split('+')
            
            for part in parts:
                part = part.strip()
                if part == 'ctrl':
                    keys.append(keyboard.Key.ctrl_l)
                elif part == 'shift':
                    keys.append(keyboard.Key.shift_l)
                elif part == 'alt':
                    keys.append(keyboard.Key.alt_l)
                elif part == 'cmd' or part == 'win':
                    keys.append(keyboard.Key.cmd)
                elif len(part) == 1:
                    keys.append(keyboard.KeyCode.from_char(part))
                else:
                    # 特殊キーの処理
                    special_keys = {
                        'space': keyboard.Key.space,
                        'enter': keyboard.Key.enter,
                        'tab': keyboard.Key.tab,
                        'esc': keyboard.Key.esc,
                        'delete': keyboard.Key.delete,
                        'backspace': keyboard.Key.backspace,
                        'insert': keyboard.Key.insert,
                        'f1': keyboard.Key.f1, 'f2': keyboard.Key.f2,
                        'f3': keyboard.Key.f3, 'f4': keyboard.Key.f4,
                        'f5': keyboard.Key.f5, 'f6': keyboard.Key.f6,
                        'f7': keyboard.Key.f7, 'f8': keyboard.Key.f8,
                        'f9': keyboard.Key.f9, 'f10': keyboard.Key.f10,
                        'f11': keyboard.Key.f11, 'f12': keyboard.Key.f12,
                    }
                    if part in special_keys:
                        keys.append(special_keys[part])
                    else:
                        print(f"未知のキー: {part}")
                        return None
            
            return keys
        except Exception as e:
            print(f"ホットキーのパースエラー: {e}")
            return None
    
    def run(self):
        """QThreadのrunメソッド - ホットキーリスナーを実行"""
        if not PYNPUT_AVAILABLE:
            print("pynputが利用できません。ホットキー機能は無効です。")
            return
        
        try:
            print("DEBUG: HotkeyWorker.run() 開始")
            
            # メイン表示切り替えホットキー (Ctrl+Shift+M)
            main_hotkey = keyboard.HotKey(
                keyboard.HotKey.parse('<ctrl>+<shift>+m'),
                self.toggle_visibility_signal.emit
            )
            
            # 自動テキストホットキー
            auto_text_hotkey = None
            if self.auto_text_settings['enabled']:
                auto_keys = self.parse_hotkey(self.auto_text_settings['hotkey'])
                if auto_keys:
                    auto_text_hotkey = keyboard.HotKey(
                        set(auto_keys),
                        self.auto_text_signal.emit
                    )
            
            def on_press(key):
                if self._stop_requested:
                    return False
                
                # Insertキー単体の処理
                if key == keyboard.Key.insert:
                    print("DEBUG: Insertキーが押されました")
                    self.toggle_visibility_signal.emit()
                    return
                
                try:
                    main_hotkey.press(key)
                    if auto_text_hotkey:
                        auto_text_hotkey.press(key)
                except Exception as e:
                    print(f"キー押下処理エラー: {e}")
            
            def on_release(key):
                if self._stop_requested:
                    return False
                
                try:
                    main_hotkey.release(key)
                    if auto_text_hotkey:
                        auto_text_hotkey.release(key)
                except Exception as e:
                    print(f"キー離上処理エラー: {e}")
            
            # リスナーを作成して開始
            self.hotkey_listener = keyboard.Listener(
                on_press=on_press,
                on_release=on_release,
                suppress=False
            )
            
            print("DEBUG: keyboard.Listener開始")
            self.hotkey_listener.start()
            
            # ポーリングループ（join()を使わない）
            print("DEBUG: ポーリングループ開始")
            while not self._stop_requested and self.hotkey_listener.running:
                self.msleep(50)  # 50ms間隔でチェック
            
            print("DEBUG: ポーリングループ終了")
            
        except Exception as e:
            print(f"ホットキーリスナーエラー: {e}")
        finally:
            print("DEBUG: HotkeyWorker.run() 終了処理開始")
            if hasattr(self, 'hotkey_listener') and self.hotkey_listener:
                try:
                    self.hotkey_listener.stop()
                    print("DEBUG: keyboard.Listener停止完了")
                except:
                    pass
            print("DEBUG: HotkeyWorker.run() 完全終了")
    
    def stop(self):
        """スレッドの停止要求"""
        print("DEBUG: HotkeyWorker停止要求を受信")
        self._stop_requested = True
        
        if hasattr(self, 'hotkey_listener') and self.hotkey_listener:
            try:
                print("DEBUG: pynput keyboard.Listener停止中...")
                self.hotkey_listener.stop()
                print("DEBUG: pynput keyboard.Listener停止完了")
            except Exception as e:
                print(f"ホットキーリスナー停止エラー: {e}")
            finally:
                self.hotkey_listener = None

class HotkeyManager(QObject):
    """ホットキー管理を担当するクラス"""
    
    toggle_visibility_signal = pyqtSignal()
    auto_text_signal = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.hotkey_worker = None
        self.auto_text_settings = {
            'enabled': False,
            'text': '',
            'hotkey': 'ctrl+shift+v'
        }
    
    def start_hotkey_listener_global(self):
        """グローバルホットキーリスナーの開始（QThread使用）"""
        if not PYNPUT_AVAILABLE:
            print("pynputが利用できません。ホットキー機能は無効です。")
            return
        
        # 既存のワーカーを停止
        if self.hotkey_worker:
            self.stop_hotkey_listener()
        
        # 新しいQThreadワーカーを作成
        self.hotkey_worker = HotkeyWorker(self.auto_text_settings, self)
        
        # シグナルの接続
        self.hotkey_worker.toggle_visibility_signal.connect(self.toggle_visibility_signal.emit)
        self.hotkey_worker.auto_text_signal.connect(self.auto_text_signal.emit)
        
        # スレッド開始
        self.hotkey_worker.start()
        print("グローバルホットキーが有効になりました (Ctrl+Shift+M)")
    
    def stop_hotkey_listener(self):
        """ホットキーリスナーの停止（QThread版）"""
        print("DEBUG: ホットキーリスナーの停止を開始...")
        
        if self.hotkey_worker:
            try:
                print("DEBUG: HotkeyWorkerを停止中...")
                # ワーカーに停止要求を送信
                self.hotkey_worker.stop()
                
                # QThreadの終了を待機（長めに設定）
                if self.hotkey_worker.wait(2000):  # 2秒待機
                    print("DEBUG: HotkeyWorkerが正常に終了しました")
                else:
                    print("WARNING: HotkeyWorkerが指定時間内に終了しませんでした。強制終了します。")
                    self.hotkey_worker.terminate()
                    if self.hotkey_worker.wait(1000):  # 強制終了後1秒待機
                        print("DEBUG: HotkeyWorkerを強制終了しました")
                    else:
                        print("ERROR: HotkeyWorkerの強制終了に失敗しました")
                    
            except Exception as e:
                print(f"HotkeyWorker停止エラー: {e}")
            finally:
                # スレッドが完全に終了するまで待機
                if self.hotkey_worker and self.hotkey_worker.isRunning():
                    print("DEBUG: スレッドの完全終了を待機中...")
                    self.hotkey_worker.wait(1000)
                
                # Qt式のリソース解放を次のイベントループで実行
                if self.hotkey_worker:
                    self.hotkey_worker.deleteLater()
                self.hotkey_worker = None
                print("DEBUG: HotkeyWorkerリファレンスをクリアしました")
    
    def update_auto_text_settings(self, enabled, text, hotkey):
        """自動テキスト設定の更新"""
        self.auto_text_settings = {
            'enabled': enabled,
            'text': text,
            'hotkey': hotkey
        }
        
        # ホットキーリスナーを再起動
        if PYNPUT_AVAILABLE:
            self.start_hotkey_listener_global()
    
    def send_auto_text(self):
        """自動テキストの送信"""
        if not PYNPUT_AVAILABLE or not self.auto_text_settings['enabled']:
            return
        
        text = self.auto_text_settings['text']
        if not text:
            return
        
        try:
            # 少し待ってからテキストを送信
            time.sleep(0.1)
            
            # キーボードを使用してテキストを入力
            keyboard_controller = keyboard.Controller()
            keyboard_controller.type(text)
            
        except Exception as e:
            print(f"自動テキスト送信エラー: {e}")