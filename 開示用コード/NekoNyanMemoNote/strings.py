# -*- coding: utf-8 -*-

# --- Dialog Titles ---
TITLE_ERROR = "エラー"
TITLE_WARNING = "警告"
TITLE_CRITICAL = "致命的なエラー"
TITLE_PERMISSION_ERROR = "権限エラー"
TITLE_CREATION_ERROR = "作成エラー"
TITLE_OS_ERROR = "OSエラー"
TITLE_ENCODING_WARNING = "エンコーディング警告"
TITLE_READ_ERROR = "読み込みエラー"
TITLE_SAVE_ERROR = "保存エラー"
TITLE_DELETE_FOLDER = "フォルダの削除"
TITLE_DELETE_MEMO = "メモの削除"
TITLE_RENAME_FOLDER = "フォルダ名を変更"
TITLE_RENAME_MEMO = "メモ名を変更"
TITLE_NEW_FOLDER = "新しいフォルダ"
TITLE_NEW_MEMO = "新しいメモ"
TITLE_AUTO_TEXT_SETTINGS = "自動入力テキスト設定"

# --- Messages ---
MSG_INPUT_FOLDER_NAME = "フォルダ名を入力してください:"
MSG_INPUT_MEMO_NAME = "メモ名を入力してください (.txt は自動付与):"
MSG_FOLDER_NAME_EMPTY = "フォルダ名を入力してください。"
MSG_FILE_NAME_EMPTY = "ファイル名を入力してください。"
MSG_INVALID_CHARS = "名前に使用できない文字が含まれています: {}"
MSG_FOLDER_ALREADY_EXISTS = "同じ名前のフォルダが既に存在します。"
MSG_MEMO_ALREADY_EXISTS = "同じ名前のメモが既に存在します。"
MSG_SELECT_FOLDER_FOR_MEMO = "メモを作成するフォルダが選択されていません。"
MSG_CONFIRM_DELETE_FOLDER = "フォルダ '{folder_name}' を削除しますか？"
MSG_CONFIRM_DELETE_MEMO = "メモ '{file_name}' を削除しますか？"
MSG_CANNOT_UNDO = "この操作は元に戻せません。"
MSG_ALL_MEMOS_DELETED = "フォルダ内のすべてのメモも削除されます。"
MSG_PYNPUT_NOT_FOUND = "pynputライブラリが見つからないため、" + \
"システムワイドホットキー機能は利用できません。"
MSG_SETTINGS_LOAD_FAILED = "設定の読み込みに失敗しました。"
MSG_SETTINGS_SAVE_FAILED = "設定の保存中にエラーが発生しました。"
MSG_BASE_DIR_CREATE_FAILED = "ベースディレクトリを作成できませんでした。"
MSG_HOTKEY_START_FAILED = "システムワイドホットキーリスナーの開始中にエラーが発生しました。"
MSG_FILE_NOT_FOUND = "ファイルが見つかりません: {}"
MSG_CANNOT_CONNECT_INSTANCE = "既に起動している {app_name} に接続できませんでした。" + \
"({error})" + \
"\n\nプロセスが残っている可能性があります。"
MSG_SHARED_MEMORY_CREATE_FAILED = "共有メモリの作成に失敗しました。" + \
"{}"
MSG_LOCAL_SERVER_START_FAILED = "ローカルサーバーの起動に失敗しました。" + \
"{}"
MSG_WINDOWS_API_NOT_AVAILABLE = "Windows API が利用できません。フォールバック処理を使用します。"
MSG_WINDOWS_API_CALL_FAILED = "Windows API 呼び出しが失敗しました: {}"

# --- File System Error Messages ---
FS_MSG_CREATE_FOLDER_FAILED = "フォルダ '{folder_name}' を作成できませんでした。"
FS_MSG_CREATE_FOLDER_PERMISSION_ERROR = "フォルダ '{folder_name}' を作成する権限がありません。"
FS_MSG_FOLDER_OR_FILE_EXISTS = "フォルダまたは同名のファイルが既に存在します: '{folder_name}'"
FS_MSG_CREATE_FOLDER_OS_ERROR = "フォルダ '{folder_name}' を作成できませんでした。OSエラーが発生しました。"
FS_MSG_CREATE_MEMO_PERMISSION_ERROR = "メモファイル '{file_name}' を作成する権限がありません。"
FS_MSG_CREATE_MEMO_OS_ERROR = "メモファイル '{file_name}' を作成できませんでした。OSエラーが発生しました。"
FS_MSG_RENAME_FOLDER_PERMISSION_ERROR = "フォルダ名の変更に必要な権限がありません。"
FS_MSG_RENAME_FOLDER_OS_ERROR = "フォルダ名を変更できませんでした。OSエラーが発生しました。"
FS_MSG_DELETE_FOLDER_PERMISSION_ERROR = "フォルダ '{folder_name}' を削除する権限がありません。"
FS_MSG_DELETE_FOLDER_NOT_FOUND = "削除しようとしたフォルダ '{folder_name}' が見つかりません。"
FS_MSG_DELETE_FOLDER_OS_ERROR = "フォルダ '{folder_name}' を削除できませんでした。OSエラーが発生しました。" + \
"\n\nファイルが他のプログラムで使用されていないか確認してください。"
FS_MSG_RENAME_MEMO_PERMISSION_ERROR = "メモ名の変更に必要な権限がありません。"
FS_MSG_RENAME_MEMO_OS_ERROR = "メモ名を変更できませんでした。OSエラーが発生しました。"
FS_MSG_DELETE_MEMO_PERMISSION_ERROR = "メモ '{file_name}' を削除する権限がありません。"
FS_MSG_DELETE_MEMO_NOT_FOUND = "削除しようとしたメモ '{file_name}' が見つかりません。"
FS_MSG_DELETE_MEMO_OS_ERROR = "メモ '{file_name}' を削除できませんでした。OSエラーが発生しました。"
FS_MSG_LOAD_MEMO_FAILED = "メモ '{file_name}' を読み込めませんでした。"
FS_MSG_LOAD_MEMO_PERMISSION_ERROR = "メモファイル '{file_name}' を読み込む権限がありません。"
FS_MSG_LOAD_MEMO_NOT_FOUND = "メモファイルが見つかりません: {file_name}"
FS_MSG_SAVE_MEMO_PERMISSION_ERROR = "メモを保存する権限がありません。"
FS_MSG_SAVE_MEMO_OS_ERROR = "メモを保存できませんでした。OSエラーが発生しました。"
FS_MSG_ENCODING_WARNING = "ファイルを CP932 (Shift-JIS) として読み込みました。" + \
"文字化けしている可能性があります。" + \
"UTF-8 で保存し直すことを推奨します。" + \
"{file_path}"


# --- UI Labels and Tooltips ---
UI_LBL_DELETE = "削除する"
UI_LBL_CANCEL = "キャンセル"
UI_LBL_WRAP_MODE = "折り返し: {}"
UI_LBL_WRAP_WINDOW = "ウィンドウ幅"
UI_LBL_WRAP_FIXED = "{width}文字(目安)"
UI_LBL_WRAP_NONE = "折り返さない"
UI_LBL_CURSOR_POS = "カーソル: {line}行 {col}桁"
UI_LBL_CHAR_COUNT = "文字数: {count}"
UI_LBL_READ_ONLY = "文字数: - (編集不可)"
UI_LBL_STATUS_DEFAULT = "-"
UI_LBL_FONT_SIZE = "{size}pt"
UI_LBL_AUTO_TEXT_CTRL_W = "Ctrl+W+{i}:"

UI_ACT_NEW_FOLDER = "新規フォルダを作成"
UI_ACT_RENAME_FOLDER = "フォルダ名を変更"
UI_ACT_DELETE_FOLDER = "フォルダを削除"
UI_ACT_NEW_MEMO = "新規メモを作成"
UI_ACT_RENAME_MEMO = "メモ名を変更"
UI_ACT_DELETE_MEMO = "メモを削除"
UI_ACT_TOGGLE_READONLY = "メモを編集不可にする"
UI_ACT_WRAP_NONE = "折り返さない"
UI_ACT_WRAP_FIXED = "全角36文字分で折り返す"
UI_ACT_WRAP_WINDOW = "ウィンドウ幅で折り返す"

UI_BTN_WRAP_SETTINGS = "折り返し設定"
UI_BTN_AUTO_INSERT = "自動挿入"

UI_TOOLTIP_DECREASE_FONT = "文字サイズを小さくする"
UI_TOOLTIP_INCREASE_FONT = "文字サイズを大きくする"
UI_TOOLTIP_CURRENT_FONT = "現在の文字サイズ"
UI_TOOLTIP_AUTO_TEXT_SETTINGS = "自動入力テキスト設定"
UI_TOOLTIP_NEW_TAB = "新しいフォルダ（タブ）を作成します"
