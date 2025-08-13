# -*- coding: utf-8 -*-

import unittest
import tempfile
import os
import json
from unittest.mock import Mock, patch, MagicMock
import sys

# テスト用のパス設定
test_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(test_dir)
sys.path.insert(0, parent_dir)

from NekoNyanMemoNote.settings_manager import SettingsManager

class TestSettingsManager(unittest.TestCase):
    def setUp(self):
        """テスト前の準備"""
        self.mock_parent = Mock()
        
        # QSettingsのモック
        self.mock_settings = Mock()
        self.mock_parent.settings = self.mock_settings
        
        with patch('NekoNyanMemoNote.settings_manager.QSettings'):
            self.settings_manager = SettingsManager(self.mock_parent)
            self.settings_manager.settings = self.mock_settings
    
    @patch('NekoNyanMemoNote.settings_manager.ConfigValidator.validate_json_string')
    @patch('NekoNyanMemoNote.settings_manager.ConfigValidator.sanitize_file_paths')
    @patch('NekoNyanMemoNote.settings_manager.ConfigValidator.get_safe_default')
    def test_load_json_setting_valid(self, mock_get_default, mock_sanitize, mock_validate):
        """有効なJSON設定の読み込みテスト"""
        test_data = {"key1": "value1", "key2": "value2"}
        self.mock_settings.value.return_value = json.dumps(test_data)
        
        # ConfigValidatorのモック設定
        mock_get_default.return_value = {}
        mock_validate.return_value = (True, test_data, None)
        mock_sanitize.return_value = test_data
        
        result = self.settings_manager.load_json_setting("test_key", "test_schema", {})
        
        self.assertEqual(result, test_data)
        self.mock_settings.value.assert_called_once_with("test_key", "{}", type=str)
    
    def test_load_json_setting_invalid_json(self):
        """無効なJSON設定の読み込みテスト"""
        self.mock_settings.value.return_value = "invalid json"
        
        result = self.settings_manager.load_json_setting("test_key", "test_schema", {"default": True})
        
        self.assertEqual(result, {"default": True})
    
    @patch('NekoNyanMemoNote.settings_manager.ConfigValidator._validate_data')
    def test_save_json_setting_success(self, mock_validate_data):
        """JSON設定保存の正常ケース"""
        test_data = {"key": "value"}
        
        # ConfigValidatorのモック設定
        mock_validate_data.return_value = (True, None)
        
        result = self.settings_manager.save_json_setting("test_key", test_data, "test_schema")
        
        expected_json = json.dumps(test_data, ensure_ascii=False, separators=(',', ':'))
        self.mock_settings.setValue.assert_called_once_with("test_key", expected_json)
        self.assertTrue(result)

if __name__ == '__main__':
    unittest.main()