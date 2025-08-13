# -*- coding: utf-8 -*-

import unittest
import os
from unittest.mock import Mock, patch, MagicMock
import sys

# テスト用のパス設定
test_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(test_dir)
sys.path.insert(0, parent_dir)

from NekoNyanMemoNote.tab_manager import TabManager

class TestTabManager(unittest.TestCase):
    def setUp(self):
        """テスト前の準備"""
        self.mock_parent = Mock()
        
        with patch('NekoNyanMemoNote.tab_manager.QTabWidget') as mock_tab_widget_class:
            self.mock_tab_widget = Mock()
            mock_tab_widget_class.return_value = self.mock_tab_widget
            
            self.tab_manager = TabManager(self.mock_parent)
    
    @patch('NekoNyanMemoNote.tab_manager.QWidget')
    @patch('NekoNyanMemoNote.tab_manager.CustomTabBar')
    @patch('NekoNyanMemoNote.tab_manager.QTabWidget')
    def test_create_tab_widget(self, mock_tab_widget_class, mock_custom_tab_bar, mock_qwidget):
        """タブウィジェット作成のテスト"""
        # モックのセットアップ
        mock_tab_widget = Mock()
        mock_tab_widget_class.return_value = mock_tab_widget
        mock_tab_bar = Mock()
        mock_custom_tab_bar.return_value = mock_tab_bar
        mock_plus_widget = Mock()
        mock_qwidget.return_value = mock_plus_widget
        
        # count()の返り値を設定（プラスタブ追加時のインデックス計算用）
        mock_tab_widget.count.return_value = 1
        
        # テスト実行
        result = self.tab_manager.create_tab_widget()
        
        # アサーション
        self.assertEqual(result, mock_tab_widget)
        mock_tab_widget.setTabBar.assert_called_once_with(mock_tab_bar)
        mock_tab_widget.currentChanged.connect.assert_called_once()
        mock_tab_widget.addTab.assert_called_once_with(mock_plus_widget, "+")

if __name__ == '__main__':
    unittest.main()