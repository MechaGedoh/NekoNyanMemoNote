# -*- coding: utf-8 -*-

import json
import os
from typing import Dict, List, Any, Union, Optional

class ConfigValidator:
    """設定データのスキーマ検証を行うクラス"""
    
    # スキーマ定義
    LAST_OPENED_FILES_SCHEMA = {
        "type": "object",
        "description": "最後に開いていたファイルのマップ",
        "additionalProperties": {
            "type": "string",
            "description": "ファイルパス（文字列）"
        }
    }
    
    TAB_ORDER_SCHEMA = {
        "type": "array",
        "description": "タブの順序配列",
        "items": {
            "type": "string",
            "description": "ファイルパス（文字列）"
        }
    }
    
    @staticmethod
    def validate_json_string(json_str: str, schema_name: str) -> tuple[bool, Optional[Any], Optional[str]]:
        """
        JSON文字列をパースし、スキーマ検証を行う
        
        Args:
            json_str: 検証するJSON文字列
            schema_name: スキーマ名 ('lastOpenedFiles' または 'tabOrder')
            
        Returns:
            tuple[bool, Optional[Any], Optional[str]]: (成功フラグ, パース結果, エラーメッセージ)
        """
        try:
            # JSON パース
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            return False, None, f"JSON解析エラー: {e}"
        
        # スキーマ検証
        is_valid, error_msg = ConfigValidator._validate_data(data, schema_name)
        if not is_valid:
            return False, None, f"スキーマ検証エラー: {error_msg}"
        
        return True, data, None
    
    @staticmethod
    def _validate_data(data: Any, schema_name: str) -> tuple[bool, Optional[str]]:
        """データのスキーマ検証を行う"""
        if schema_name == "lastOpenedFiles":
            return ConfigValidator._validate_last_opened_files(data)
        elif schema_name == "tabOrder":
            return ConfigValidator._validate_tab_order(data)
        else:
            return False, f"未知のスキーマ名: {schema_name}"
    
    @staticmethod
    def _validate_last_opened_files(data: Any) -> tuple[bool, Optional[str]]:
        """lastOpenedFilesのスキーマ検証"""
        if not isinstance(data, dict):
            return False, "lastOpenedFilesは辞書である必要があります"
        
        for key, value in data.items():
            if not isinstance(key, str):
                return False, f"キー '{key}' は文字列である必要があります"
            if not isinstance(value, str):
                return False, f"値 '{value}' は文字列である必要があります"
            
            # ファイルパスの基本検証（危険な文字の確認）
            if ConfigValidator._has_dangerous_path_chars(key):
                return False, f"キー '{key}' に危険な文字が含まれています"
            if ConfigValidator._has_dangerous_path_chars(value):
                return False, f"値 '{value}' に危険な文字が含まれています"
        
        return True, None
    
    @staticmethod
    def _validate_tab_order(data: Any) -> tuple[bool, Optional[str]]:
        """tabOrderのスキーマ検証"""
        if not isinstance(data, list):
            return False, "tabOrderは配列である必要があります"
        
        for i, item in enumerate(data):
            if not isinstance(item, str):
                return False, f"インデックス {i} の項目は文字列である必要があります"
            
            # ファイルパスの基本検証
            if ConfigValidator._has_dangerous_path_chars(item):
                return False, f"インデックス {i} の項目 '{item}' に危険な文字が含まれています"
        
        return True, None
    
    @staticmethod
    def _has_dangerous_path_chars(path: str) -> bool:
        """ファイルパスに危険な文字が含まれているかチェック"""
        if not path:
            return False
        
        # 絶対に許可しない文字
        dangerous_chars = ['\x00', '\r', '\n']  # ヌル文字、改行文字
        
        for char in dangerous_chars:
            if char in path:
                return True
        
        # 過度に長いパスのチェック（Windows限界の260文字を基準）
        if len(path) > 500:
            return True
        
        return False
    
    @staticmethod
    def sanitize_file_paths(data: Union[Dict[str, str], List[str]]) -> Union[Dict[str, str], List[str]]:
        """ファイルパスを正規化・サニタイズする"""
        if isinstance(data, dict):
            # lastOpenedFiles形式
            sanitized = {}
            for key, value in data.items():
                try:
                    safe_key = os.path.normcase(os.path.abspath(key))
                    safe_value = os.path.normcase(os.path.abspath(value))
                    sanitized[safe_key] = safe_value
                except (ValueError, OSError) as e:
                    print(f"警告: パス正規化に失敗しました ({key} -> {value}): {e}")
                    continue
            return sanitized
        
        elif isinstance(data, list):
            # tabOrder形式
            sanitized = []
            for item in data:
                try:
                    safe_path = os.path.normcase(os.path.abspath(item))
                    sanitized.append(safe_path)
                except (ValueError, OSError) as e:
                    print(f"警告: パス正規化に失敗しました ({item}): {e}")
                    continue
            return sanitized
        
        return data
    
    @staticmethod
    def get_safe_default(schema_name: str) -> Any:
        """スキーマに応じた安全なデフォルト値を返す"""
        if schema_name == "lastOpenedFiles":
            return {}
        elif schema_name == "tabOrder":
            return []
        else:
            return None