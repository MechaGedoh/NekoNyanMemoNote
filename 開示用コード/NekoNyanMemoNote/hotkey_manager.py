# -*- coding: utf-8 -*-

import threading
import time
from PyQt6.QtCore import QObject, pyqtSignal
from .interfaces import IHotkeyManager

try:
    from pynput import keyboard
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False

class HotkeyManager(QObject):
    """ホットキー管理を担当するクラス"""
    
    toggle_visibility_signal = pyqtSignal()
    auto_text_signal = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.hotkey_listener = None
        self.hotkey_thread = None
        self.auto_text_settings = {
            'enabled': False,
            'text': '',
            'hotkey': 'ctrl+shift+v'
        }
    
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
                        'f1': keyboard.Key.f1,
                        'f2': keyboard.Key.f2,
                        'f3': keyboard.Key.f3,
                        'f4': keyboard.Key.f4,
                        'f5': keyboard.Key.f5,
                        'f6': keyboard.Key.f6,
                        'f7': keyboard.Key.f7,
                        'f8': keyboard.Key.f8,
                        'f9': keyboard.Key.f9,
                        'f10': keyboard.Key.f10,
                        'f11': keyboard.Key.f11,
                        'f12': keyboard.Key.f12,
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
    
    def start_hotkey_listener_global(self):
        """グローバルホットキーリスナーの開始"""
        if not PYNPUT_AVAILABLE:
            print("pynputが利用できません。ホットキー機能は無効です。")
            return
        
        def hotkey_thread():
            try:
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
                
                def for_canonical(f):
                    return lambda k: f(self.hotkey_listener.canonical(k))
                
                def on_press(key):
                    # Insertキー単体の処理
                    if key == keyboard.Key.insert:
                        print("DEBUG: Insertキーが押されました")
                        self.toggle_visibility_signal.emit()
                        return
                    
                    main_hotkey.press(for_canonical(lambda k: k)(key))
                    if auto_text_hotkey:
                        auto_text_hotkey.press(for_canonical(lambda k: k)(key))
                
                def on_release(key):
                    main_hotkey.release(for_canonical(lambda k: k)(key))
                    if auto_text_hotkey:
                        auto_text_hotkey.release(for_canonical(lambda k: k)(key))
                
                # リスナー開始
                self.hotkey_listener = keyboard.Listener(
                    on_press=on_press,
                    on_release=on_release
                )
                self.hotkey_listener.start()
                self.hotkey_listener.join()
                
            except Exception as e:
                print(f"ホットキーリスナーエラー: {e}")
        
        if self.hotkey_thread and self.hotkey_thread.is_alive():
            self.stop_hotkey_listener()
        
        self.hotkey_thread = threading.Thread(target=hotkey_thread, daemon=True)
        self.hotkey_thread.start()
        print("グローバルホットキーが有効になりました (Ctrl+Shift+M)")
    
    def stop_hotkey_listener(self):
        """ホットキーリスナーの停止"""
        if self.hotkey_listener:
            try:
                self.hotkey_listener.stop()
                time.sleep(0.1)
            except Exception as e:
                print(f"ホットキーリスナー停止エラー: {e}")
            finally:
                self.hotkey_listener = None
        
        if self.hotkey_thread and self.hotkey_thread.is_alive():
            try:
                self.hotkey_thread.join(timeout=1.0)
            except Exception as e:
                print(f"ホットキースレッド停止エラー: {e}")
            finally:
                self.hotkey_thread = None
    
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