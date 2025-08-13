# -*- coding: utf-8 -*-

import unittest
import tempfile
import os
import shutil
from unittest.mock import Mock, patch, MagicMock
import sys

# テスト用のパス設定
test_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(test_dir)
sys.path.insert(0, parent_dir)

from NekoNyanMemoNote.file_system import FileSystemManager

class TestFileSystemManager(unittest.TestCase):
    def setUp(self):
        """テスト前の準備"""
        self.mock_parent = Mock()
        self.temp_dir = tempfile.mkdtemp()
        
        # BASE_MEMO_DIRをテスト用ディレクトリに変更
        self.original_base_dir = FileSystemManager.__module__ + '.BASE_MEMO_DIR'
        self.patcher = patch('NekoNyanMemoNote.file_system.BASE_MEMO_DIR', self.temp_dir)
        self.patcher.start()
        
        self.fs_manager = FileSystemManager(self.mock_parent)
    
    def tearDown(self):
        """テスト後のクリーンアップ"""
        self.patcher.stop()
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    @patch('NekoNyanMemoNote.file_system.QInputDialog.getText')
    def test_create_new_folder_success(self, mock_input):
        """フォルダ作成の正常ケース"""
        mock_input.return_value = ("テストフォルダ", True)
        
        folder_name, folder_path = self.fs_manager.create_new_folder()
        
        self.assertEqual(folder_name, "テストフォルダ")
        self.assertTrue(os.path.exists(folder_path))
        self.assertTrue(os.path.isdir(folder_path))
    
    @patch('NekoNyanMemoNote.file_system.QInputDialog.getText')
    def test_create_new_folder_duplicate_name(self, mock_input):
        """重複名フォルダ作成のテスト"""
        # 最初のフォルダを作成
        mock_input.return_value = ("テストフォルダ", True)
        folder_name1, folder_path1 = self.fs_manager.create_new_folder()
        
        # 同名フォルダを作成（自動的に番号が付与される）
        mock_input.return_value = ("テストフォルダ", True)
        folder_name2, folder_path2 = self.fs_manager.create_new_folder()
        
        self.assertEqual(folder_name1, "テストフォルダ")
        self.assertEqual(folder_name2, "テストフォルダ_1")
        self.assertTrue(os.path.exists(folder_path1))
        self.assertTrue(os.path.exists(folder_path2))
    
    @patch('NekoNyanMemoNote.file_system.QInputDialog.getText')
    def test_create_new_folder_with_dialog(self, mock_input):
        """ダイアログ入力でのフォルダ作成"""
        mock_input.return_value = ("ダイアログテスト", True)
        
        folder_name, folder_path = self.fs_manager.create_new_folder()
        
        self.assertEqual(folder_name, "ダイアログテスト")
        self.assertTrue(os.path.exists(folder_path))
    
    def test_create_new_memo_success(self):
        """メモ作成の正常ケース"""
        # テスト用フォルダを作成
        test_folder = os.path.join(self.temp_dir, "テストフォルダ")
        os.makedirs(test_folder)
        
        with patch('NekoNyanMemoNote.file_system.QInputDialog.getText') as mock_input:
            mock_input.return_value = ("テストメモ", True)
            
            memo_path = self.fs_manager.create_new_memo(test_folder)
            
            self.assertIsNotNone(memo_path)
            self.assertTrue(memo_path.endswith("テストメモ.txt"))
            self.assertTrue(os.path.exists(memo_path))
    
    def test_load_memo_content_success(self):
        """メモ読み込みの正常ケース"""
        # テストファイルを作成
        test_file = os.path.join(self.temp_dir, "test.txt")
        test_content = "テストコンテンツ\n日本語テスト"
        
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write(test_content)
        
        content = self.fs_manager.load_memo_content(test_file)
        self.assertEqual(content, test_content)
    
    def test_save_memo_content_success(self):
        """メモ保存の正常ケース"""
        test_file = os.path.join(self.temp_dir, "save_test.txt")
        test_content = "保存テストコンテンツ\n日本語保存テスト"
        
        result = self.fs_manager.save_memo_content(test_file, test_content)
        
        self.assertTrue(result)
        with open(test_file, 'r', encoding='utf-8') as f:
            saved_content = f.read()
        self.assertEqual(saved_content, test_content)

if __name__ == '__main__':
    unittest.main()