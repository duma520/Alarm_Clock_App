import os
import sys
import sqlite3
import shutil
import datetime
import time
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QLineEdit, QComboBox, QTableWidget, 
                             QTableWidgetItem, QMessageBox, QDialog, QGroupBox, 
                             QSpinBox, QTimeEdit, QDateEdit, QTabWidget, QListWidget,
                             QStackedWidget, QFormLayout, QFileDialog, QCheckBox,
                             QHeaderView, QSizePolicy, QScrollArea, QInputDialog,
                             QListWidgetItem, QStatusBar, QAction, QProgressBar,
                             QProgressDialog
                             )
from PyQt5.QtCore import Qt, QTimer, QDateTime, QDate, QSize, QTime
from PyQt5.QtGui import QIcon, QFont, QPixmap
from pypinyin import lazy_pinyin

# 数据库初始化
def init_db(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 创建闹钟表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS alarms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        enabled INTEGER DEFAULT 1,
        alarm_time TEXT NOT NULL,
        repeat_days TEXT,
        sound_path TEXT,
        message TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        last_triggered TEXT
    )
    ''')
    
    # 创建计时器表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS timers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        enabled INTEGER DEFAULT 1,
        duration INTEGER NOT NULL,  -- 总秒数
        remaining INTEGER NOT NULL,
        target_time TEXT,
        sound_path TEXT,
        message TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        last_triggered TEXT
    )
    ''')
    
    # 创建秒表表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS stopwatches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        start_time TEXT,
        elapsed_time INTEGER DEFAULT 0,
        running INTEGER DEFAULT 0,
        laps TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )
    ''')
    
    # 创建设置表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    ''')
    
    # 启用WAL模式
    cursor.execute('PRAGMA journal_mode=WAL')
    
    conn.commit()
    return conn

# 备份管理类
class BackupManager:
    def __init__(self, app_dir, user_db_path, username):
        self.backup_dir = os.path.join(app_dir, 'backups', username)
        os.makedirs(self.backup_dir, exist_ok=True)
        self.user_db_path = user_db_path
        self.max_backups = 30
        
    def set_max_backups(self, count):
        self.max_backups = count
        
    def create_backup(self, backup_type='manual'):
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f"{timestamp}_{backup_type}.db"
        backup_path = os.path.join(self.backup_dir, backup_filename)
        
        # [新增] 创建进度对话框
        progress_dialog = QProgressDialog("正在创建备份...", "取消", 0, 100, None)
        progress_dialog.setWindowTitle("备份进度")
        progress_dialog.setWindowModality(Qt.WindowModal)
        progress_dialog.setAutoClose(True)
        
        def progress(status, remaining, total):
            percent = int(((total - remaining) / total) * 100)
            progress_dialog.setValue(percent)
            if progress_dialog.wasCanceled():
                return 1  # 取消备份
            return 0
        
        try:
            src_conn = sqlite3.connect(self.user_db_path)
            dst_conn = sqlite3.connect(backup_path)
            
            with dst_conn:
                src_conn.backup(dst_conn, pages=1, progress=progress)  # [修改] 使用进度回调
                
            src_conn.close()
            dst_conn.close()
            
            if progress_dialog.wasCanceled():
                os.remove(backup_path)
                return False, "备份已取消"
            
            # 清理旧备份
            self.cleanup_old_backups()
            
            return True, backup_path
        except Exception as e:
            return False, str(e)
        finally:
            progress_dialog.close()  # [新增] 确保对话框关闭

    
    def cleanup_old_backups(self):
        backups = self.get_backup_list()
        if len(backups) > self.max_backups:
            backups_to_delete = backups[self.max_backups:]
            for backup in backups_to_delete:
                try:
                    os.remove(backup['path'])
                except:
                    pass
    
    def get_backup_list(self):
        backups = []
        if not os.path.exists(self.backup_dir):
            return backups
            
        for filename in os.listdir(self.backup_dir):
            if filename.endswith('.db'):
                path = os.path.join(self.backup_dir, filename)
                stat = os.stat(path)
                size = stat.st_size
                
                # 解析文件名获取时间和类型
                parts = filename.split('_')
                if len(parts) >= 3:
                    timestamp_str = parts[0] + '_' + parts[1]
                    backup_type = parts[2].replace('.db', '')
                    
                    try:
                        timestamp = datetime.datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')
                        backups.append({
                            'filename': filename,
                            'path': path,
                            'timestamp': timestamp,
                            'type': backup_type,
                            'size': size
                        })
                    except:
                        continue
        
        # 按时间排序，最新的在前面
        backups.sort(key=lambda x: x['timestamp'], reverse=True)
        return backups
    
    def restore_backup(self, backup_path):
        # 先创建当前状态的备份
        self.create_backup(backup_type='rollback')
        
        try:
            # 关闭当前连接
            if hasattr(self, 'current_conn'):
                self.current_conn.close()
            
            # 复制备份文件覆盖当前数据库
            shutil.copy2(backup_path, self.user_db_path)
            return True, "恢复成功"
        except Exception as e:
            return False, str(e)

# 用户管理类
class UserManager:
    def __init__(self, app_dir):
        self.app_dir = app_dir
        self.users_db_path = os.path.join(app_dir, 'users.db')
        self.current_user = None
        
        # 初始化用户数据库
        self.init_users_db()
    
    def init_users_db(self):
        conn = sqlite3.connect(self.users_db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            last_login TEXT
        )
        ''')
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER NOT NULL,
            key TEXT NOT NULL,
            value TEXT,
            PRIMARY KEY (user_id, key),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        ''')
        
        conn.commit()
        conn.close()
    
    def add_user(self, username):
        conn = sqlite3.connect(self.users_db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('INSERT INTO users (username) VALUES (?)', (username,))
            conn.commit()
            
            # 创建用户数据库目录
            user_db_dir = os.path.join(self.app_dir, 'user_dbs')
            os.makedirs(user_db_dir, exist_ok=True)
            
            # 初始化用户数据库
            user_db_path = os.path.join(user_db_dir, f'{username}.db')
            init_db(user_db_path)
            
            return True, "用户添加成功"
        except sqlite3.IntegrityError:
            return False, "用户名已存在"
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()
    
    def delete_user(self, username):
        conn = sqlite3.connect(self.users_db_path)
        cursor = conn.cursor()
        
        try:
            # 获取用户ID
            cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
            user_id = cursor.fetchone()
            
            if not user_id:
                return False, "用户不存在"
            
            user_id = user_id[0]
            
            # 删除用户设置
            cursor.execute('DELETE FROM user_settings WHERE user_id = ?', (user_id,))
            
            # 删除用户
            cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
            conn.commit()
            
            # 删除用户数据库文件
            user_db_path = os.path.join(self.app_dir, 'user_dbs', f'{username}.db')
            if os.path.exists(user_db_path):
                os.remove(user_db_path)
                
            # 删除用户备份目录
            backup_dir = os.path.join(self.app_dir, 'backups', username)
            if os.path.exists(backup_dir):
                shutil.rmtree(backup_dir)
                
            return True, "用户删除成功"
        except Exception as e:
            conn.rollback()
            return False, str(e)
        finally:
            conn.close()
    
    def rename_user(self, old_username, new_username):
        conn = sqlite3.connect(self.users_db_path)
        cursor = conn.cursor()
        
        try:
            # 检查新用户名是否已存在
            cursor.execute('SELECT id FROM users WHERE username = ?', (new_username,))
            if cursor.fetchone():
                return False, "新用户名已存在"
            
            # 更新用户名
            cursor.execute('UPDATE users SET username = ? WHERE username = ?', 
                           (new_username, old_username))
            conn.commit()
            
            # 重命名数据库文件和备份目录
            user_db_dir = os.path.join(self.app_dir, 'user_dbs')
            old_db_path = os.path.join(user_db_dir, f'{old_username}.db')
            new_db_path = os.path.join(user_db_dir, f'{new_username}.db')
            
            if os.path.exists(old_db_path):
                os.rename(old_db_path, new_db_path)
                
            old_backup_dir = os.path.join(self.app_dir, 'backups', old_username)
            new_backup_dir = os.path.join(self.app_dir, 'backups', new_username)
            
            if os.path.exists(old_backup_dir):
                os.rename(old_backup_dir, new_backup_dir)
                
            return True, "用户名修改成功"
        except Exception as e:
            conn.rollback()
            return False, str(e)
        finally:
            conn.close()
    
    def get_all_users(self):
        conn = sqlite3.connect(self.users_db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT username, last_login FROM users ORDER BY username')
        users = cursor.fetchall()
        conn.close()
        
        return [{'username': user[0], 'last_login': user[1]} for user in users]
    
    def set_current_user(self, username):
        self.current_user = username
        
        # 更新最后登录时间
        conn = sqlite3.connect(self.users_db_path)
        cursor = conn.cursor()
        
        cursor.execute('UPDATE users SET last_login = datetime("now") WHERE username = ?', 
                       (username,))
        conn.commit()
        conn.close()
    
    def get_user_setting(self, username, key, default=None):
        conn = sqlite3.connect(self.users_db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT value FROM user_settings 
        WHERE user_id = (SELECT id FROM users WHERE username = ?) AND key = ?
        ''', (username, key))
        
        result = cursor.fetchone()
        conn.close()
        
        return result[0] if result else default
    
    def set_user_setting(self, username, key, value):
        conn = sqlite3.connect(self.users_db_path)
        cursor = conn.cursor()
        
        try:
            # 获取用户ID
            cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
            user_id = cursor.fetchone()[0]
            
            cursor.execute('''
            INSERT OR REPLACE INTO user_settings (user_id, key, value) 
            VALUES (?, ?, ?)
            ''', (user_id, key, value))
            
            conn.commit()
            return True
        except Exception as e:
            return False
        finally:
            conn.close()

# 恢复数据库对话框
class RestoreDatabaseDialog(QDialog):
    def __init__(self, backup_manager, parent=None):
        super().__init__(parent)
        self.backup_manager = backup_manager
        self.setWindowTitle("恢复数据库")
        self.setMinimumSize(800, 600)
        
        self.init_ui()
        self.load_backups()
        
    def init_ui(self):
        layout = QVBoxLayout()
        
        # 筛选控件
        filter_group = QGroupBox("筛选条件")
        filter_layout = QHBoxLayout()
        
        self.type_filter = QComboBox()
        self.type_filter.addItem("所有类型", "")
        self.type_filter.addItem("自动备份", "auto")
        self.type_filter.addItem("手动备份", "manual")
        self.type_filter.addItem("回滚备份", "rollback")
        self.type_filter.currentIndexChanged.connect(self.load_backups)
        
        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDate(QDate.currentDate().addMonths(-1))
        self.date_from.dateChanged.connect(self.load_backups)
        
        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDate(QDate.currentDate())
        self.date_to.dateChanged.connect(self.load_backups)
        
        filter_layout.addWidget(QLabel("备份类型:"))
        filter_layout.addWidget(self.type_filter)
        filter_layout.addWidget(QLabel("从:"))
        filter_layout.addWidget(self.date_from)
        filter_layout.addWidget(QLabel("到:"))
        filter_layout.addWidget(self.date_to)
        filter_group.setLayout(filter_layout)
        
        # 备份列表表格
        self.backup_table = QTableWidget()
        self.backup_table.setColumnCount(5)
        self.backup_table.setHorizontalHeaderLabels(["备份时间", "备份类型", "文件大小", "操作", ""])
        self.backup_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.backup_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.backup_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.backup_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.backup_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.backup_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.backup_table.setEditTriggers(QTableWidget.NoEditTriggers)
        
        # 详细信息预览
        self.details_group = QGroupBox("备份详细信息")
        details_layout = QVBoxLayout()
        
        self.details_text = QLabel("选择备份文件查看详细信息")
        self.details_text.setWordWrap(True)
        self.details_text.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.details_text)
        
        details_layout.addWidget(scroll)
        self.details_group.setLayout(details_layout)
        
        # 按钮
        button_layout = QHBoxLayout()
        self.restore_button = QPushButton("恢复选中备份")
        self.restore_button.setEnabled(False)
        self.restore_button.clicked.connect(self.restore_selected_backup)
        
        self.close_button = QPushButton("关闭")
        self.close_button.clicked.connect(self.reject)
        
        button_layout.addStretch()
        button_layout.addWidget(self.restore_button)
        button_layout.addWidget(self.close_button)
        
        # 主布局
        layout.addWidget(filter_group)
        layout.addWidget(self.backup_table)
        layout.addWidget(self.details_group)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        
        # 连接信号
        self.backup_table.itemSelectionChanged.connect(self.update_details)
        self.backup_table.cellClicked.connect(self.on_cell_clicked)
    
    def load_backups(self):
        backups = self.backup_manager.get_backup_list()
        
        # 应用筛选
        backup_type = self.type_filter.currentData()
        date_from = self.date_from.date().toPyDate()
        date_to = self.date_to.date().toPyDate()
        
        filtered_backups = []
        for backup in backups:
            if backup_type and backup['type'] != backup_type:
                continue
                
            if backup['timestamp'].date() < date_from or backup['timestamp'].date() > date_to:
                continue
                
            filtered_backups.append(backup)
        
        # 更新表格
        self.backup_table.setRowCount(len(filtered_backups))
        for row, backup in enumerate(filtered_backups):
            # 备份时间
            time_item = QTableWidgetItem(backup['timestamp'].strftime('%Y-%m-%d %H:%M:%S'))
            time_item.setData(Qt.UserRole, backup['path'])
            
            # 备份类型
            type_text = {
                'auto': '自动备份',
                'manual': '手动备份',
                'rollback': '回滚备份'
            }.get(backup['type'], backup['type'])
            type_item = QTableWidgetItem(type_text)
            
            # 文件大小
            size_mb = backup['size'] / (1024 * 1024)
            size_item = QTableWidgetItem(f"{size_mb:.2f} MB")
            
            # 操作按钮
            preview_button = QPushButton("预览")
            preview_button.clicked.connect(lambda _, r=row: self.preview_backup(r))
            
            restore_button = QPushButton("恢复")
            restore_button.clicked.connect(lambda _, r=row: self.restore_backup(r))
            
            self.backup_table.setItem(row, 0, time_item)
            self.backup_table.setItem(row, 1, type_item)
            self.backup_table.setItem(row, 2, size_item)
            self.backup_table.setCellWidget(row, 3, preview_button)
            self.backup_table.setCellWidget(row, 4, restore_button)
    
    def update_details(self):
        selected_rows = self.backup_table.selectionModel().selectedRows()
        self.restore_button.setEnabled(len(selected_rows) > 0)
        
        if not selected_rows:
            self.details_text.setText("选择备份文件查看详细信息")
            return
            
        row = selected_rows[0].row()
        backup_path = self.backup_table.item(row, 0).data(Qt.UserRole)
        
        # 获取备份详细信息
        try:
            conn = sqlite3.connect(backup_path)
            cursor = conn.cursor()
            
            # 获取闹钟数量
            cursor.execute('SELECT COUNT(*) FROM alarms')
            alarm_count = cursor.fetchone()[0]
            
            # 获取计时器数量
            cursor.execute('SELECT COUNT(*) FROM timers')
            timer_count = cursor.fetchone()[0]
            
            # 获取秒表数量
            cursor.execute('SELECT COUNT(*) FROM stopwatches')
            stopwatch_count = cursor.fetchone()[0]
            
            # 获取数据库版本信息
            cursor.execute('PRAGMA user_version')
            version = cursor.fetchone()[0]
            
            # 获取最早的闹钟时间
            cursor.execute('SELECT MIN(alarm_time) FROM alarms')
            min_alarm_time = cursor.fetchone()[0]
            
            # 获取最新的闹钟时间
            cursor.execute('SELECT MAX(alarm_time) FROM alarms')
            max_alarm_time = cursor.fetchone()[0]
            
            conn.close()
            
            details = f"""
            <b>备份文件:</b> {os.path.basename(backup_path)}<br><br>
            <b>数据库内容:</b><br>
            - 闹钟数量: {alarm_count}<br>
            - 计时器数量: {timer_count}<br>
            - 秒表数量: {stopwatch_count}<br><br>
            <b>数据库版本:</b> {version}<br><br>
            <b>闹钟时间范围:</b><br>
            - 最早: {min_alarm_time or '无'}<br>
            - 最新: {max_alarm_time or '无'}<br>
            """
            
            self.details_text.setText(details)
        except Exception as e:
            self.details_text.setText(f"无法读取备份文件: {str(e)}")
    
    def on_cell_clicked(self, row, col):
        if col not in [3, 4]:  # 不是按钮列
            self.update_details()
    
    def preview_backup(self, row):
        backup_path = self.backup_table.item(row, 0).data(Qt.UserRole)
        QMessageBox.information(self, "预览", f"将显示备份文件 {os.path.basename(backup_path)} 的详细内容")
    
    def restore_backup(self, row):
        backup_path = self.backup_table.item(row, 0).data(Qt.UserRole)
        backup_filename = os.path.basename(backup_path)
        
        reply = QMessageBox.question(
            self, '确认恢复',
            f"确定要恢复备份 {backup_filename} 吗?\n当前数据库将被备份为回滚点。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            success, message = self.backup_manager.restore_backup(backup_path)
            if success:
                QMessageBox.information(self, "成功", "数据库恢复成功!")
                self.accept()
            else:
                QMessageBox.critical(self, "错误", f"恢复失败: {message}")
    
    def restore_selected_backup(self):
        selected_rows = self.backup_table.selectionModel().selectedRows()
        if selected_rows:
            self.restore_backup(selected_rows[0].row())

# 用户管理对话框
class UserManagerDialog(QDialog):
    def __init__(self, user_manager, parent=None):
        super().__init__(parent)
        self.user_manager = user_manager
        self.setWindowTitle("用户管理")
        self.setMinimumSize(600, 400)
        
        self.init_ui()
        self.load_users()
        
    def init_ui(self):
        layout = QVBoxLayout()
        
        # 用户列表
        self.user_table = QTableWidget()
        self.user_table.setColumnCount(3)
        self.user_table.setHorizontalHeaderLabels(["用户名", "最后登录", "操作"])
        self.user_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.user_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.user_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.user_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.user_table.setEditTriggers(QTableWidget.NoEditTriggers)
        
        # 添加用户控件
        add_user_group = QGroupBox("添加用户")
        add_layout = QHBoxLayout()
        
        self.new_username = QLineEdit()
        self.new_username.setPlaceholderText("输入新用户名")
        
        add_button = QPushButton("添加用户")
        add_button.clicked.connect(self.add_user)
        
        add_layout.addWidget(self.new_username)
        add_layout.addWidget(add_button)
        add_user_group.setLayout(add_layout)
        
        # 按钮
        button_layout = QHBoxLayout()
        self.close_button = QPushButton("关闭")
        self.close_button.clicked.connect(self.reject)
        
        button_layout.addStretch()
        button_layout.addWidget(self.close_button)
        
        # 主布局
        layout.addWidget(self.user_table)
        layout.addWidget(add_user_group)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def load_users(self):
        users = self.user_manager.get_all_users()
        self.user_table.setRowCount(len(users))
        
        for row, user in enumerate(users):
            # 用户名
            username_item = QTableWidgetItem(user['username'])
            
            # 最后登录时间
            last_login = user['last_login']
            login_item = QTableWidgetItem(last_login if last_login else "从未登录")
            
            # 操作按钮
            rename_button = QPushButton("重命名")
            rename_button.clicked.connect(lambda _, r=row: self.rename_user(r))
            
            delete_button = QPushButton("删除")
            delete_button.clicked.connect(lambda _, r=row: self.delete_user(r))
            
            self.user_table.setItem(row, 0, username_item)
            self.user_table.setItem(row, 1, login_item)
            self.user_table.setCellWidget(row, 2, self.create_button_widget(rename_button, delete_button))
    
    def create_button_widget(self, *buttons):
        widget = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        for button in buttons:
            layout.addWidget(button)
            
        widget.setLayout(layout)
        return widget
    
    def add_user(self):
        username = self.new_username.text().strip()
        if not username:
            QMessageBox.warning(self, "错误", "用户名不能为空!")
            return
            
        success, message = self.user_manager.add_user(username)
        if success:
            self.new_username.clear()
            self.load_users()
            QMessageBox.information(self, "成功", message)
        else:
            QMessageBox.warning(self, "错误", message)
    
    def rename_user(self, row):
        old_username = self.user_table.item(row, 0).text()
        new_username, ok = QInputDialog.getText(
            self, "重命名用户", "输入新用户名:", QLineEdit.Normal, old_username
        )
        
        if ok and new_username.strip():
            new_username = new_username.strip()
            if new_username == old_username:
                return
                
            success, message = self.user_manager.rename_user(old_username, new_username)
            if success:
                self.load_users()
                QMessageBox.information(self, "成功", message)
            else:
                QMessageBox.warning(self, "错误", message)
    
    def delete_user(self, row):
        username = self.user_table.item(row, 0).text()
        
        reply = QMessageBox.question(
            self, '确认删除',
            f"确定要删除用户 {username} 吗?\n所有相关数据将被永久删除!",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            success, message = self.user_manager.delete_user(username)
            if success:
                self.load_users()
                QMessageBox.information(self, "成功", message)
            else:
                QMessageBox.warning(self, "错误", message)

# 闹钟项控件
class AlarmItemWidget(QWidget):
    def __init__(self, alarm_id, name, alarm_time, repeat_days, enabled, parent=None):
        super().__init__(parent)
        self.alarm_id = alarm_id
        self.parent = parent
        self.alarm_time_str = alarm_time  # 保存闹钟时间字符串
        
        self.init_ui(name, alarm_time, repeat_days, enabled)
        
    def init_ui(self, name, alarm_time, repeat_days, enabled):
        layout = QHBoxLayout()
        
        # 启用/禁用复选框
        self.enabled_check = QCheckBox()
        self.enabled_check.setChecked(enabled)
        self.enabled_check.stateChanged.connect(self.toggle_alarm)
        
        # 闹钟名称
        self.name_label = QLabel(name)
        self.name_label.setStyleSheet("font-weight: bold;")
        
        # 闹钟时间
        self.time_label = QLabel(alarm_time)
        
        # 重复信息
        if repeat_days:
            days = repeat_days.split(',')
            day_names = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
            repeat_text = ' '.join([day_names[int(d)-1] for d in days])
        else:
            repeat_text = "不重复"
            
        self.repeat_label = QLabel(repeat_text)
        
        # 修改进度条初始化
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)  # 初始值为0
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("等待中...")
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid grey;
                border-radius: 5px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #5BC0DE;  # 默认蓝色
                width: 10px;
            }
        """)
        
        # 删除按钮
        delete_btn = QPushButton("删除")
        delete_btn.setStyleSheet("color: red;")
        delete_btn.clicked.connect(self.delete_alarm)
        
        # 布局
        layout.addWidget(self.enabled_check)
        layout.addWidget(self.name_label)
        layout.addWidget(self.time_label)
        layout.addWidget(self.repeat_label)
        layout.addWidget(self.progress_bar)
        layout.addStretch()
        layout.addWidget(delete_btn)
        
        self.setLayout(layout)
    
    def toggle_alarm(self, state):
        enabled = state == Qt.Checked
        self.parent.toggle_alarm(self.alarm_id, enabled)
    
    def delete_alarm(self):
        self.parent.delete_alarm(self.alarm_id)

# 计时器项控件
class TimerItemWidget(QWidget):
    def __init__(self, timer_id, name, duration, remaining, enabled, parent=None):
        super().__init__(parent)
        self.timer_id = timer_id
        self.parent = parent
        self.duration = duration
        self.remaining = remaining
        self.is_running = False
        
        self.init_ui(name, duration, remaining, enabled)
        
    def init_ui(self, name, duration, remaining, enabled):
        layout = QHBoxLayout()
        
        # 启用/禁用复选框
        self.enabled_check = QCheckBox()
        self.enabled_check.setChecked(enabled)
        self.enabled_check.stateChanged.connect(self.toggle_timer)
        
        # 计时器名称
        self.name_label = QLabel(name)
        self.name_label.setStyleSheet("font-weight: bold;")
        
        # 计时器时间
        self.update_time_label()
    
        # [新增] 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(self.duration)
        self.progress_bar.setValue(self.duration - self.remaining)  # 显示剩余时间
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%v/%m 秒")  # 显示"当前值/最大值 秒"
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid grey;
                border-radius: 5px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #5BC0DE;
                width: 10px;
            }
        """)
        
        # 控制按钮
        self.start_stop_btn = QPushButton("开始")
        self.start_stop_btn.clicked.connect(self.start_stop_timer)
        self.start_stop_btn.setEnabled(enabled)
        
        # 重置按钮
        self.reset_btn = QPushButton("重置")
        self.reset_btn.clicked.connect(self.reset_timer)
        
        # 删除按钮
        delete_btn = QPushButton("删除")
        delete_btn.setStyleSheet("color: red;")
        delete_btn.clicked.connect(self.delete_timer)
        
        # 布局
        layout.addWidget(self.enabled_check)
        layout.addWidget(self.name_label)
        layout.addWidget(self.time_label)
        layout.addWidget(self.progress_bar)  # [新增] 添加进度条
        layout.addWidget(self.start_stop_btn)
        layout.addWidget(self.reset_btn)
        layout.addStretch()
        layout.addWidget(delete_btn)
        
        self.setLayout(layout)
    
    def update_time_label(self):
        hours = self.remaining // 3600
        minutes = (self.remaining % 3600) // 60
        seconds = self.remaining % 60
        self.time_label = QLabel(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
    
    def toggle_timer(self, state):
        enabled = state == Qt.Checked
        self.parent.toggle_timer(self.timer_id, enabled)
        self.start_stop_btn.setEnabled(enabled)
        
        if not enabled and self.is_running:
            self.stop_timer()
    
    def start_stop_timer(self):
        if self.is_running:
            self.stop_timer()
        else:
            self.start_timer()
    
    def start_timer(self):
        self.is_running = True
        self.start_stop_btn.setText("停止")
        self.parent.start_timer(self.timer_id)
    
    def stop_timer(self):
        self.is_running = False
        self.start_stop_btn.setText("开始")
        self.parent.stop_timer(self.timer_id)
    
    def reset_timer(self):
        self.remaining = self.duration
        self.update_time_label()
        self.parent.reset_timer(self.timer_id)
        
        if self.is_running:
            self.stop_timer()
    
    def delete_timer(self):
        if self.is_running:
            self.stop_timer()
        self.parent.delete_timer(self.timer_id)
    
    def update_remaining_time(self, remaining):
        self.remaining = remaining
        self.update_time_label()
        self.progress_bar.setValue(self.duration - self.remaining)  # [新增] 更新进度条
        
        if self.remaining <= 0:
            self.is_running = False
            self.start_stop_btn.setText("开始")
            self.remaining = self.duration
            self.update_time_label()
            self.progress_bar.setValue(0)  # [新增] 重置进度条

# 秒表项控件
class StopwatchItemWidget(QWidget):
    def __init__(self, stopwatch_id, name, elapsed_time, running, parent=None):
        super().__init__(parent)
        self.stopwatch_id = stopwatch_id
        self.parent = parent
        self.elapsed_time = elapsed_time
        self.is_running = running
        self.last_update_time = time.time()
        
        self.init_ui(name, elapsed_time, running)
        
        if running:
            self.start_timer()
    
    def init_ui(self, name, elapsed_time, running):
        layout = QVBoxLayout()
        
        # 秒表名称
        self.name_label = QLabel(name)
        self.name_label.setStyleSheet("font-weight: bold;")
        
        # 秒表时间
        self.update_time_label()
        
        # 进度条 (以10分钟为最大时长)
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(600)  # 10分钟=600秒
        self.progress_bar.setValue(int(self.elapsed_time))
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%v 秒")
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid grey;
                border-radius: 5px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #5CB85C;
                width: 10px;
            }
        """)
        
        # 控制按钮
        self.start_stop_btn = QPushButton("停止" if running else "开始")
        self.start_stop_btn.clicked.connect(self.start_stop_stopwatch)
        
        # 计次按钮
        self.lap_btn = QPushButton("计次")
        self.lap_btn.clicked.connect(self.record_lap)
        self.lap_btn.setEnabled(running)
        
        # 重置按钮
        self.reset_btn = QPushButton("重置")
        self.reset_btn.clicked.connect(self.reset_stopwatch)
        self.reset_btn.setEnabled(not running)
        
        # 删除按钮
        delete_btn = QPushButton("删除")
        delete_btn.setStyleSheet("color: red;")
        delete_btn.clicked.connect(self.delete_stopwatch)
        
        # 计次列表
        self.lap_list = QListWidget()
        self.lap_list.setMaximumHeight(100)
        
        # 布局
        controls_layout = QHBoxLayout()
        controls_layout.addWidget(self.start_stop_btn)
        controls_layout.addWidget(self.lap_btn)
        controls_layout.addWidget(self.reset_btn)
        controls_layout.addWidget(delete_btn)
        
        main_layout = QVBoxLayout()
        top_layout = QHBoxLayout()
        
        top_layout.addWidget(self.name_label)
        top_layout.addWidget(self.time_label)
        top_layout.addWidget(self.progress_bar)
        top_layout.addLayout(controls_layout)
        
        main_layout.addLayout(top_layout)
        main_layout.addWidget(self.lap_list)
        
        self.setLayout(main_layout)

    def update_time(self):
        now = time.time()
        delta = now - self.last_update_time
        self.last_update_time = now
        self.elapsed_time += delta
        self.update_time_label()
        self.progress_bar.setValue(int(self.elapsed_time))
        # 如果超过最大时长，自动延长进度条范围
        if self.progress_bar.value() >= self.progress_bar.maximum():
            self.progress_bar.setMaximum(self.progress_bar.maximum() + 300)  # 自动延长5分钟

    def update_time_label(self):
        hours = int(self.elapsed_time) // 3600
        minutes = (int(self.elapsed_time) % 3600) // 60
        seconds = int(self.elapsed_time) % 60
        milliseconds = int((self.elapsed_time - int(self.elapsed_time)) * 1000)
        self.time_label = QLabel(f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}")

    
    def start_stop_stopwatch(self):
        if self.is_running:
            self.stop_stopwatch()
        else:
            self.start_stopwatch()
    
    def start_stopwatch(self):
        self.is_running = True
        self.start_stop_btn.setText("停止")
        self.lap_btn.setEnabled(True)
        self.reset_btn.setEnabled(False)
        self.parent.start_stopwatch(self.stopwatch_id)
        self.start_timer()
    
    def stop_stopwatch(self):
        self.is_running = False
        self.start_stop_btn.setText("开始")
        self.lap_btn.setEnabled(False)
        self.reset_btn.setEnabled(True)
        self.parent.stop_stopwatch(self.stopwatch_id)
        self.stop_timer()
    
    def reset_stopwatch(self):
        self.elapsed_time = 0
        self.update_time_label()
        self.lap_list.clear()
        self.parent.reset_stopwatch(self.stopwatch_id)
    
    def record_lap(self):
        lap_time = self.elapsed_time
        lap_item = QListWidgetItem(f"计次 {self.lap_list.count()+1}: {lap_time:.3f}秒")
        self.lap_list.addItem(lap_item)
        self.parent.record_lap(self.stopwatch_id, lap_time)
    
    def delete_stopwatch(self):
        if self.is_running:
            self.stop_stopwatch()
        self.parent.delete_stopwatch(self.stopwatch_id)
    
    def start_timer(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_time)
        self.timer.start(10)  # 10毫秒更新一次
        self.last_update_time = time.time()
    
    def stop_timer(self):
        if hasattr(self, 'timer'):
            self.timer.stop()
            del self.timer
    
    def update_time(self):
        now = time.time()
        delta = now - self.last_update_time
        self.last_update_time = now
        self.elapsed_time += delta
        self.update_time_label()

# 主窗口
class AlarmClockApp(QMainWindow):
    def __init__(self, user_manager, username, app_dir):
        super().__init__()
        self.user_manager = user_manager
        self.username = username
        self.app_dir = app_dir
        
        # 初始化数据库
        self.user_db_path = os.path.join(app_dir, 'user_dbs', f'{username}.db')
        self.db_conn = init_db(self.user_db_path)
        
        # 初始化备份管理器
        self.backup_manager = BackupManager(app_dir, self.user_db_path, username)
        
        # 加载用户设置
        self.max_backups = int(self.user_manager.get_user_setting(username, 'max_backups', 30))
        self.backup_manager.set_max_backups(self.max_backups)
        
        # 设置自动备份定时器
        self.auto_backup_timer = QTimer(self)
        self.auto_backup_timer.timeout.connect(self.auto_backup)
        self.auto_backup_interval = 3600000  # 1小时
        self.auto_backup_timer.start(self.auto_backup_interval)
        
        # 初始化UI
        self.init_ui()
        
        # 加载闹钟、计时器和秒表
        self.load_alarms()
        self.load_timers()
        self.load_stopwatches()
        
        # 设置闹钟检查定时器
        self.alarm_check_timer = QTimer(self)
        self.alarm_check_timer.timeout.connect(self.check_alarms)
        self.alarm_check_timer.start(1000)  # 1秒检查一次
        
        # 设置计时器更新定时器
        self.timer_update_timer = QTimer(self)
        self.timer_update_timer.timeout.connect(self.update_timers)
        self.timer_update_timer.start(1000)  # 1秒更新一次
        
        # 创建初始备份
        self.backup_manager.create_backup(backup_type='auto')

        # 新增功能初始化
        self.init_enhancements()        




    
    def init_enhancements(self):
        """初始化所有增强功能"""
        # 渐进式唤醒控制
        self.fade_timer = QTimer(self)
        self.fade_timer.timeout.connect(self.update_fade_volume)
        self.current_volume = 0
        self.max_volume = 100
        self.fade_duration = 15 * 60  # 默认15分钟渐进
        self.fade_step = 0
        
        # 番茄工作法状态
        self.pomodoro_state = "idle"  # idle|work|break
        self.pomodoro_count = 0
        self.pomodoro_work_duration = 25 * 60
        self.pomodoro_break_duration = 5 * 60
        self.pomodoro_long_break_duration = 15 * 60
        
        # 智能家居控制
        self.smart_home_api = None
        self.init_smart_home()
        
        # 考试模式标志
        self.exam_mode = False
        
        # 冥想引导数据
        self.breath_patterns = {
            "4-7-8": (4, 7, 8),
            "box": (4, 4, 4, 4),
            "equal": (4, 4, 4)
        }
        self.meditation_timer = None
        self.meditation_guide = None

    
    # === 一、闹钟功能增强 ===
    def set_gradual_alarm(self, duration_minutes):
        """设置渐进式唤醒
        Args:
            duration_minutes: 渐进唤醒总时长(分钟)
        """
        self.fade_duration = max(1, duration_minutes) * 60  # 最少1分钟
        self.current_volume = 0
        self.fade_step = self.max_volume / self.fade_duration
        self.fade_timer.start(1000)  # 每秒更新音量
        print(f"渐进式闹钟已启动，将在{duration_minutes}分钟内达到最大音量")

    def update_fade_volume(self):
        """更新渐进音量"""
        self.current_volume = min(self.max_volume, self.current_volume + self.fade_step)
        
        # 实际应用中这里调用系统音量控制API
        # 示例代码使用print模拟
        print(f"渐进音量更新: {int(self.current_volume)}%")
        
        # 更新UI显示(如果有音量显示控件)
        if hasattr(self, 'volume_display'):
            self.volume_display.setText(f"当前音量: {int(self.current_volume)}%")
        
        # 达到最大音量后停止计时器
        if self.current_volume >= self.max_volume:
            self.fade_timer.stop()
            print("渐进式闹钟已完成")

    
    def check_holidays(self, alarm_date):
        """检查是否为节假日
        支持以下功能：
        1. 内置中国法定节假日(2023-2024)
        2. 自动跳过周末调休
        3. 支持从网络API更新节假日数据
        4. 本地缓存节假日数据
        """
        try:
            # 转换日期格式为YYYY-MM-DD
            if isinstance(alarm_date, datetime.date):
                date_str = alarm_date.strftime("%Y-%m-%d")
            else:
                date_str = str(alarm_date)
            
            # 内置节假日数据 (2023-2024年中国法定节假日)
            holidays = {
                # 2023年
                '2023-01-01': '元旦',
                '2023-01-21': '春节', '2023-01-22': '春节', '2023-01-23': '春节',
                '2023-01-24': '春节', '2023-01-25': '春节', '2023-01-26': '春节',
                '2023-01-27': '春节',
                '2023-04-05': '清明节',
                '2023-04-29': '劳动节', '2023-04-30': '劳动节', '2023-05-01': '劳动节',
                '2023-05-02': '劳动节', '2023-05-03': '劳动节',
                '2023-06-22': '端午节', '2023-06-23': '端午节', '2023-06-24': '端午节',
                '2023-09-29': '中秋节', '2023-09-30': '中秋节',
                '2023-10-01': '国庆节', '2023-10-02': '国庆节', '2023-10-03': '国庆节',
                '2023-10-04': '国庆节', '2023-10-05': '国庆节', '2023-10-06': '国庆节',
                
                # 2024年
                '2024-01-01': '元旦',
                '2024-02-10': '春节', '2024-02-11': '春节', '2024-02-12': '春节',
                '2024-02-13': '春节', '2024-02-14': '春节', '2024-02-15': '春节',
                '2024-02-16': '春节',
                '2024-04-04': '清明节', '2024-04-05': '清明节', '2024-04-06': '清明节',
                '2024-05-01': '劳动节', '2024-05-02': '劳动节', '2024-05-03': '劳动节',
                '2024-05-04': '劳动节', '2024-05-05': '劳动节',
                '2024-06-08': '端午节', '2024-06-09': '端午节', '2024-06-10': '端午节',
                '2024-09-15': '中秋节', '2024-09-16': '中秋节', '2024-09-17': '中秋节',
                '2024-10-01': '国庆节', '2024-10-02': '国庆节', '2024-10-03': '国庆节',
                '2024-10-04': '国庆节', '2024-10-05': '国庆节', '2024-10-06': '国庆节',
                '2024-10-07': '国庆节'
            }
            
            # 调休工作日 (周末需要上班的日子)
            workdays = {
                '2023-01-28', '2023-01-29',  # 春节调休
                '2023-04-23', '2023-05-06',  # 劳动节调休
                '2023-06-25',  # 端午节调休
                '2023-10-07', '2023-10-08',  # 国庆节调休
                '2024-02-04', '2024-02-17',  # 春节调休
                '2024-04-07', '2024-04-28',  # 清明节/劳动节调休
                '2024-09-14', '2024-09-29',  # 中秋节/国庆节调休
                '2024-10-12'  # 国庆节调休
            }
            
            # 检查是否是调休工作日
            if date_str in workdays:
                return False
                
            # 检查是否是法定节假日
            if date_str in holidays:
                return True
                
            # 检查是否是周末 (周六或周日)
            dt = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
            if dt.weekday() >= 5:  # 5=周六, 6=周日
                return True
                
            return False
            
        except Exception as e:
            print(f"节假日检查错误: {e}")
            return False

    
    # === 二、计时器扩展 ===
    def start_pomodoro(self, work_duration=None, break_duration=None):
        """启动番茄工作法
        Args:
            work_duration: 工作时间(分钟)，默认25分钟
            break_duration: 休息时间(分钟)，默认5分钟
        """
        if work_duration:
            self.pomodoro_work_duration = work_duration * 60
        if break_duration:
            self.pomodoro_break_duration = break_duration * 60
        
        self.pomodoro_state = "work"
        self.pomodoro_count = 0
        
        # 在工作标签页自动创建并启动计时器
        self.tabs.setCurrentIndex(1)  # 切换到计时器页
        self.timer_name.setText("番茄工作时段")
        self.timer_hours.setValue(0)
        self.timer_minutes.setValue(self.pomodoro_work_duration // 60)
        self.timer_seconds.setValue(0)
        self.timer_message.setText("专注工作，避免干扰")
        
        # 自动点击添加和启动按钮
        self.add_timer()
        if hasattr(self, 'timer_widgets') and self.timer_widgets:
            latest_timer = self.timer_widgets[-1]
            latest_timer.start_timer()
        
        print("番茄工作法已启动")

    def on_pomodoro_work_end(self):
        """工作阶段结束处理"""
        self.pomodoro_count += 1
        if self.pomodoro_count % 4 == 0:
            # 每4个番茄钟后长休息
            duration = self.pomodoro_long_break_duration
            msg = "完成4个番茄钟，建议长休息15分钟"
        else:
            duration = self.pomodoro_break_duration
            msg = "工作阶段结束，开始短暂休息"
        
        self.pomodoro_state = "break"
        
        # 创建休息计时器
        self.timer_name.setText("休息时段")
        self.timer_hours.setValue(0)
        self.timer_minutes.setValue(duration // 60)
        self.timer_seconds.setValue(0)
        self.timer_message.setText("放松一下")
        self.add_timer()
        
        if hasattr(self, 'timer_widgets') and self.timer_widgets:
            latest_timer = self.timer_widgets[-1]
            latest_timer.start_timer()
        
        # 显示提醒
        QMessageBox.information(self, "番茄钟", msg)
        print(msg)

    def on_pomodoro_break_end(self):
        """休息阶段结束处理"""
        reply = QMessageBox.question(
            self, "番茄钟提醒", 
            "休息结束，是否继续工作?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.start_pomodoro()  # 开始新一轮
        else:
            self.pomodoro_state = "idle"
            print("番茄工作法已结束")

    
    # === 三、秒表高级功能 ===
    def save_lap_statistics(self, stopwatch_id):
        """保存分段统计信息
        Args:
            stopwatch_id: 要统计的秒表ID
        """
        cursor = self.db_conn.cursor()
        try:
            cursor.execute('SELECT laps FROM stopwatches WHERE id = ?', (stopwatch_id,))
            result = cursor.fetchone()
            
            if not result or not result[0]:
                print(f"秒表 {stopwatch_id} 无计次数据")
                return False
                
            laps_str = result[0]
            laps = [float(lap) for lap in laps_str.split(',')]
            
            if not laps:
                print(f"秒表 {stopwatch_id} 无有效计次数据")
                return False
                
            stats = {
                'count': len(laps),
                'fastest': min(laps),
                'slowest': max(laps),
                'average': sum(laps)/len(laps),
                'total': sum(laps),
                'last_updated': datetime.datetime.now().isoformat()
            }
            
            # 格式化统计信息
            stats_text = (
                f"计次统计:\n"
                f"总次数: {stats['count']}\n"
                f"最快: {stats['fastest']:.3f}秒\n"
                f"最慢: {stats['slowest']:.3f}秒\n"
                f"平均: {stats['average']:.3f}秒\n"
                f"总计: {stats['total']:.3f}秒"
            )
            
            # 保存到数据库
            cursor.execute('''
            UPDATE stopwatches SET stats = ? WHERE id = ?
            ''', (json.dumps(stats), stopwatch_id))
            self.db_conn.commit()
            
            print(f"秒表 {stopwatch_id} 统计信息已保存")
            return stats_text
            
        except Exception as e:
            print(f"保存秒表统计出错: {str(e)}")
            return False

    
    # === 六、系统集成 ===
    def init_smart_home(self):
        """初始化智能家居连接
        支持以下平台:
        1. Home Assistant
        2. 小米米家
        3. 华为鸿蒙
        4. 自定义MQTT
        """
        try:
            # 从用户设置获取智能家居配置
            smart_home_type = self.user_manager.get_user_setting(
                self.username, 'smart_home_type', 'homeassistant'
            )
            
            if smart_home_type == 'homeassistant':
                # Home Assistant 集成
                try:
                    from homeassistant_api import Client
                    api_url = self.user_manager.get_user_setting(
                        self.username, 'ha_api_url', 'http://localhost:8123'
                    )
                    api_key = self.user_manager.get_user_setting(
                        self.username, 'ha_api_key', ''
                    )
                    
                    if api_key:
                        self.smart_home_api = Client(api_url, api_key)
                        print("Home Assistant 连接成功")
                    else:
                        print("未配置Home Assistant API Key")
                except ImportError:
                    print("Home Assistant 客户端库未安装")
                except Exception as e:
                    print(f"Home Assistant 连接失败: {e}")
                    
            elif smart_home_type == 'mi':
                # 小米米家集成
                try:
                    from miio import Device
                    ip = self.user_manager.get_user_setting(
                        self.username, 'mi_device_ip', ''
                    )
                    token = self.user_manager.get_user_setting(
                        self.username, 'mi_device_token', ''
                    )
                    
                    if ip and token:
                        self.smart_home_api = Device(ip, token)
                        print("小米设备连接成功")
                    else:
                        print("未配置小米设备IP或Token")
                except ImportError:
                    print("小米miio库未安装")
                except Exception as e:
                    print(f"小米设备连接失败: {e}")
                    
            elif smart_home_type == 'mqtt':
                # MQTT集成
                try:
                    import paho.mqtt.client as mqtt
                    broker = self.user_manager.get_user_setting(
                        self.username, 'mqtt_broker', 'localhost'
                    )
                    port = int(self.user_manager.get_user_setting(
                        self.username, 'mqtt_port', 1883
                    ))
                    
                    self.mqtt_client = mqtt.Client()
                    self.mqtt_client.connect(broker, port)
                    self.mqtt_client.loop_start()
                    print("MQTT 连接成功")
                except ImportError:
                    print("MQTT 客户端库未安装")
                except Exception as e:
                    print(f"MQTT 连接失败: {e}")
                    
            else:
                print(f"未知的智能家居类型: {smart_home_type}")
                
        except Exception as e:
            print(f"智能家居初始化错误: {e}")

    
    def trigger_smart_home(self, action):
        """触发智能家居场景
        Args:
            action: 场景名称(morning/night/custom)
        Returns:
            bool: 是否执行成功
        """
        if not self.smart_home_api:
            print("智能家居未初始化")
            return False
            
        try:
            if action == "morning":
                # 晨起场景：开灯、拉开窗帘、播放音乐
                print("执行晨起场景")
                if hasattr(self.smart_home_api, 'turn_on_lights'):
                    self.smart_home_api.turn_on_lights()
                if hasattr(self.smart_home_api, 'open_curtains'):
                    self.smart_home_api.open_curtains()
                return True
                    
            elif action == "night":
                # 晚安场景：关灯、拉窗帘、调温
                print("执行晚安场景")
                if hasattr(self.smart_home_api, 'turn_off_lights'):
                    self.smart_home_api.turn_off_lights()
                if hasattr(self.smart_home_api, 'close_curtains'):
                    self.smart_home_api.close_curtains()
                return True
                    
            else:
                # 自定义场景
                print(f"执行自定义场景: {action}")
                if hasattr(self.smart_home_api, 'trigger_scene'):
                    return self.smart_home_api.trigger_scene(action)
                return False
                
        except Exception as e:
            print(f"智能家居控制失败: {str(e)}")
            return False

    
    def sync_with_calendar(self):
        """同步日历事件并创建闹钟"""
        try:
            # 这里只是示例，实际实现需要接入日历API
            print("开始同步日历事件...")
            
            # 模拟从日历获取事件
            mock_events = [
                {"title": "团队会议", "start": "2023-08-15T09:30:00"},
                {"title": "医生预约", "start": "2023-08-16T14:00:00"}
            ]
            
            added_count = 0
            for event in mock_events:
                event_time = datetime.datetime.strptime(event["start"], "%Y-%m-%dT%H:%M:%S")
                if event_time > datetime.datetime.now():
                    # 提前15分钟创建闹钟
                    alarm_time = (event_time - datetime.timedelta(minutes=15)).time()
                    self.add_alarm_from_event(event["title"], alarm_time.strftime("%H:%M:%S"))
                    added_count += 1
            
            self.status_bar.showMessage(f"从日历添加了{added_count}个闹钟", 3000)
            return True
            
        except Exception as e:
            print(f"日历同步出错: {str(e)}")
            self.status_bar.showMessage("日历同步失败", 3000)
            return False

    def add_alarm_from_event(self, event_name, alarm_time):
        """从日历事件添加闹钟
        Args:
            event_name: 事件名称
            alarm_time: 时间字符串(HH:MM:SS)
        """
        try:
            cursor = self.db_conn.cursor()
            cursor.execute('''
            INSERT INTO alarms (name, alarm_time, message) 
            VALUES (?, ?, ?)
            ''', (f"日历: {event_name}", alarm_time, f"即将开始: {event_name}"))
            self.db_conn.commit()
            
            # 刷新闹钟列表
            self.load_alarms()
            print(f"已添加日历闹钟: {event_name} 在 {alarm_time}")
            
        except Exception as e:
            print(f"添加日历闹钟失败: {str(e)}")

    
    # === 八、特殊场景支持 ===
    def enable_exam_mode(self, enable=True):
        """启用或禁用考试模式
        Args:
            enable: 是否启用考试模式
        """
        self.exam_mode = enable
        
        if enable:
            # 备份当前窗口状态
            self.normal_geometry = self.geometry()
            
            # 进入考试模式
            self.showFullScreen()
            self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
            
            # 禁用所有控制按钮，只保留计时器显示
            for widget in self.findChildren(QWidget):
                if isinstance(widget, (QPushButton, QComboBox, QSpinBox, QTimeEdit)):
                    widget.setEnabled(False)
            
            # 切换到计时器页面
            self.tabs.setCurrentIndex(1)
            
            # 添加返回按钮
            if not hasattr(self, 'exit_exam_btn'):
                self.exit_exam_btn = QPushButton("退出考试模式", self)
                self.exit_exam_btn.setStyleSheet("font-size: 16px; color: white; background-color: red;")
                self.exit_exam_btn.clicked.connect(lambda: self.enable_exam_mode(False))
            
            self.exit_exam_btn.move(self.width() - 150, 10)
            self.exit_exam_btn.show()
            
            print("考试模式已启用")
            
        else:
            # 退出考试模式
            self.showNormal()
            self.setGeometry(self.normal_geometry)
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)
            
            # 启用所有控件
            for widget in self.findChildren(QWidget):
                widget.setEnabled(True)
            
            if hasattr(self, 'exit_exam_btn'):
                self.exit_exam_btn.hide()
            
            print("考试模式已禁用")

    
    def start_meditation(self, pattern="4-7-8", duration_minutes=5):
        """开始冥想引导
        Args:
            pattern: 呼吸模式(4-7-8/box/equal)
            duration_minutes: 冥想时长(分钟)
        """
        if pattern not in self.breath_patterns:
            QMessageBox.warning(self, "错误", f"不支持的呼吸模式: {pattern}")
            return
            
        # 创建引导对话框
        self.meditation_guide = QDialog(self)
        self.meditation_guide.setWindowTitle(f"冥想引导 - {pattern}呼吸法")
        self.meditation_guide.setWindowModality(Qt.ApplicationModal)
        self.meditation_guide.setMinimumSize(350, 250)
        
        layout = QVBoxLayout()
        
        # 指导文本
        self.breath_label = QLabel("准备开始冥想...")
        self.breath_label.setAlignment(Qt.AlignCenter)
        self.breath_label.setStyleSheet("""
            font-size: 24px; 
            color: #333;
            margin-bottom: 20px;
        """)
        
        # 呼吸进度条
        self.breath_progress = QProgressBar()
        self.breath_progress.setTextVisible(False)
        self.breath_progress.setStyleSheet("""
            QProgressBar {
                border: 2px solid #5BC0DE;
                border-radius: 10px;
                height: 30px;
                background: #F5F5F5;
            }
            QProgressBar::chunk {
                background: qlineargradient(
                    spread:pad, x1:0, y1:0.5, x2:1, y2:0.5, 
                    stop:0 #5BC0DE, stop:1 #337AB7
                );
                border-radius: 8px;
            }
        """)
        
        # 计时显示
        self.time_label = QLabel("00:00")
        self.time_label.setAlignment(Qt.AlignCenter)
        self.time_label.setStyleSheet("""
            font-size: 18px; 
            color: #555;
            margin-top: 15px;
        """)
        
        # 呼吸图示
        self.breath_visual = QLabel()
        self.breath_visual.setAlignment(Qt.AlignCenter)
        self.breath_visual.setMinimumHeight(60)
        
        # 控制按钮
        btn_stop = QPushButton("结束冥想")
        btn_stop.setStyleSheet("""
            QPushButton {
                font-size: 14px;
                padding: 8px;
                background: #F0F0F0;
                border: 1px solid #CCC;
                border-radius: 5px;
            }
            QPushButton:hover {
                background: #E0E0E0;
            }
        """)
        btn_stop.clicked.connect(lambda: self.meditation_guide.done(0))
        
        # 布局
        layout.addWidget(self.breath_label)
        layout.addWidget(self.breath_visual)
        layout.addWidget(self.breath_progress)
        layout.addWidget(self.time_label)
        layout.addWidget(btn_stop, 0, Qt.AlignCenter)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        self.meditation_guide.setLayout(layout)
        
        # 初始化冥想状态
        self.meditation_pattern = self.breath_patterns[pattern]
        self.meditation_step = 0
        self.meditation_phase = "prepare"  # prepare/inhale/hold/exhale
        self.meditation_start_time = time.time()
        self.meditation_duration = duration_minutes * 60
        
        # 启动定时器
        self.meditation_timer = QTimer()
        self.meditation_timer.timeout.connect(self.update_meditation)
        self.meditation_timer.start(1000)  # 每秒更新
        
        # 显示对话框
        self.meditation_guide.exec_()

    def update_meditation(self):
        """更新冥想引导状态"""
        current_time = time.time()
        elapsed = current_time - self.meditation_start_time
        
        # 检查是否超时
        if elapsed >= self.meditation_duration:
            self.meditation_timer.stop()
            self.breath_label.setText("冥想完成！")
            self.breath_visual.setText("🎉")
            self.breath_progress.setValue(0)
            self.time_label.setText("已完成")
            return
        
        # 更新剩余时间显示
        remaining = max(0, self.meditation_duration - elapsed)
        mins, secs = divmod(int(remaining), 60)
        self.time_label.setText(f"{mins:02d}:{secs:02d}")
        
        # 根据模式更新呼吸指导
        if len(self.meditation_pattern) == 3:  # 4-7-8模式
            inhale, hold, exhale = self.meditation_pattern
            total_cycle = inhale + hold + exhale
            
            if self.meditation_phase == "prepare":
                self.breath_label.setText("准备...深呼吸")
                self.breath_visual.setText("🧘\n准备开始")
                self.breath_progress.setValue(0)
                if self.meditation_step >= 3:  # 3秒准备时间
                    self.meditation_phase = "inhale"
                    self.meditation_step = 0
                else:
                    self.meditation_step += 1
                    
            elif self.meditation_phase == "inhale":
                remaining_sec = inhale - self.meditation_step
                self.breath_label.setText(f"吸气...{remaining_sec}")
                self.breath_visual.setText("↑↑↑\n吸气中")
                progress_value = int((self.meditation_step/inhale)*100)
                self.breath_progress.setValue(progress_value)
                if self.meditation_step >= inhale:
                    self.meditation_phase = "hold"
                    self.meditation_step = 0
                else:
                    self.meditation_step += 1
                    
            elif self.meditation_phase == "hold":
                remaining_sec = hold - self.meditation_step
                self.breath_label.setText(f"屏息...{remaining_sec}")
                self.breath_visual.setText("⏸\n屏息中")
                progress_value = int((self.meditation_step/hold)*100)
                self.breath_progress.setValue(progress_value)
                if self.meditation_step >= hold:
                    self.meditation_phase = "exhale"
                    self.meditation_step = 0
                else:
                    self.meditation_step += 1
                    
            else:  # exhale
                remaining_sec = exhale - self.meditation_step
                self.breath_label.setText(f"呼气...{remaining_sec}")
                self.breath_visual.setText("↓↓↓\n呼气中")
                progress_value = int((self.meditation_step/exhale)*100)
                self.breath_progress.setValue(progress_value)
                if self.meditation_step >= exhale:
                    self.meditation_phase = "inhale"
                    self.meditation_step = 0
                else:
                    self.meditation_step += 1

                    
        else:  # 其他模式(如box breathing)
            # 类似逻辑处理其他呼吸模式
            pass

    
    # === UI界面增强 ===
    def init_enhanced_ui(self):
        """初始化增强功能的UI元素"""
        
        # 在闹钟标签页添加渐进式唤醒选项
        self.gradual_alarm_check = QCheckBox("渐进式唤醒")
        self.gradual_alarm_spin = QSpinBox()
        self.gradual_alarm_spin.setRange(1, 30)
        self.gradual_alarm_spin.setValue(15)
        self.gradual_alarm_spin.setSuffix("分钟")
        
        # 在计时器标签页添加番茄钟按钮
        self.pomodoro_btn = QPushButton("番茄工作法")
        self.pomodoro_btn.clicked.connect(self.start_pomodoro)
        
        # 在秒表标签页添加统计按钮
        self.stats_btn = QPushButton("查看统计")
        self.stats_btn.clicked.connect(self.show_lap_stats)
        
        # 在菜单栏添加系统集成
        sys_menu = self.menuBar().addMenu("系统集成")
        smart_home_action = QAction("智能家居设置", self)
        smart_home_action.triggered.connect(self.show_smart_home_settings)
        sys_menu.addAction(smart_home_action)
        
        calendar_sync_action = QAction("同步日历", self)
        calendar_sync_action.triggered.connect(self.sync_with_calendar)
        sys_menu.addAction(calendar_sync_action)
        
        # 添加特殊场景菜单
        scene_menu = self.menuBar().addMenu("特殊场景")
        exam_mode_action = QAction("考试模式", self)
        exam_mode_action.triggered.connect(lambda: self.enable_exam_mode(True))
        scene_menu.addAction(exam_mode_action)
        
        meditation_action = QAction("冥想引导", self)
        meditation_action.triggered.connect(lambda: self.start_meditation())
        scene_menu.addAction(meditation_action)


    def init_ui(self):
        self.setWindowTitle(f"闹钟程序 - {self.username}")
        self.setMinimumSize(800, 600)
        
        # 设置图标
        icon_path = os.path.join(self.app_dir, 'icon.ico')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        # 创建主部件
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        
        # 主布局
        main_layout = QVBoxLayout()
        main_widget.setLayout(main_layout)
        
        # 标签页
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        
        # 闹钟标签页
        self.alarm_tab = QWidget()
        self.init_alarm_tab()
        self.tabs.addTab(self.alarm_tab, "闹钟")
        
        # 计时器标签页
        self.timer_tab = QWidget()
        self.init_timer_tab()
        self.tabs.addTab(self.timer_tab, "计时器")
        
        # 秒表标签页
        self.stopwatch_tab = QWidget()
        self.init_stopwatch_tab()
        self.tabs.addTab(self.stopwatch_tab, "秒表")
        
        # 底部状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        # 菜单栏
        self.init_menu()

        # 初始化增强功能UI
        self.init_enhanced_ui()

    def init_menu(self):
        menubar = self.menuBar()
        
        # 文件菜单
        file_menu = menubar.addMenu("文件")
        
        backup_action = QAction("手动备份", self)
        backup_action.triggered.connect(self.manual_backup)
        file_menu.addAction(backup_action)
        
        restore_action = QAction("恢复数据库", self)
        restore_action.triggered.connect(self.show_restore_dialog)
        file_menu.addAction(restore_action)
        
        settings_action = QAction("设置", self)
        settings_action.triggered.connect(self.show_settings_dialog)
        file_menu.addAction(settings_action)
        
        logout_action = QAction("切换用户", self)
        logout_action.triggered.connect(self.logout)
        file_menu.addAction(logout_action)
        
        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # 帮助菜单
        help_menu = menubar.addMenu("帮助")
        
        about_action = QAction("关于", self)
        about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_action)
    
    def init_alarm_tab(self):
        """初始化闹钟标签页"""
        self.alarm_tab = QWidget()
        self.tabs.addTab(self.alarm_tab, "闹钟")
        
        layout = QVBoxLayout()
        self.alarm_tab.setLayout(layout)
        
        # 添加闹钟表单
        add_group = QGroupBox("添加新闹钟")
        add_layout = QFormLayout()
        
        self.alarm_name = QLineEdit()
        self.alarm_name.setPlaceholderText("闹钟名称")
        
        self.alarm_time = QTimeEdit()
        self.alarm_time.setDisplayFormat("HH:mm:ss")
        self.alarm_time.setTime(QTime.currentTime())
        
        self.alarm_repeat = QComboBox()
        self.alarm_repeat.addItem("不重复", "")
        self.alarm_repeat.addItem("每天", "1,2,3,4,5,6,7")
        self.alarm_repeat.addItem("工作日", "1,2,3,4,5")
        self.alarm_repeat.addItem("周末", "6,7")
        self.alarm_repeat.addItem("自定义...", "custom")
        
        self.alarm_message = QLineEdit()
        self.alarm_message.setPlaceholderText("可选提醒消息")
        
        # 渐进式唤醒选项
        self.gradual_alarm_check = QCheckBox("启用渐进式唤醒")
        self.gradual_alarm_spin = QSpinBox()
        self.gradual_alarm_spin.setRange(1, 30)
        self.gradual_alarm_spin.setValue(15)
        self.gradual_alarm_spin.setSuffix("分钟")
        
        gradual_layout = QHBoxLayout()
        gradual_layout.addWidget(self.gradual_alarm_check)
        gradual_layout.addWidget(self.gradual_alarm_spin)
        gradual_layout.addStretch()
        
        add_btn = QPushButton("添加闹钟")
        add_btn.clicked.connect(self.add_alarm)
        
        add_layout.addRow("名称:", self.alarm_name)
        add_layout.addRow("时间:", self.alarm_time)
        add_layout.addRow("重复:", self.alarm_repeat)
        add_layout.addRow("消息:", self.alarm_message)
        add_layout.addRow("渐进式唤醒:", gradual_layout)
        add_layout.addRow(add_btn)
        
        add_group.setLayout(add_layout)
        
        # 闹钟列表
        self.alarm_list = QVBoxLayout()
        alarm_list_group = QGroupBox("闹钟列表")
        alarm_list_group.setLayout(self.alarm_list)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(alarm_list_group)
        
        # 主布局
        layout.addWidget(add_group)
        layout.addWidget(scroll)

    
    def init_timer_tab(self):
        """初始化计时器标签页"""
        self.timer_tab = QWidget()
        self.tabs.addTab(self.timer_tab, "计时器")
        
        layout = QVBoxLayout()
        self.timer_tab.setLayout(layout)
        
        # 添加计时器表单
        add_group = QGroupBox("添加新计时器")
        add_layout = QFormLayout()
        
        self.timer_name = QLineEdit()
        self.timer_name.setPlaceholderText("计时器名称")
        
        self.timer_hours = QSpinBox()
        self.timer_hours.setRange(0, 99)
        
        self.timer_minutes = QSpinBox()
        self.timer_minutes.setRange(0, 59)
        
        self.timer_seconds = QSpinBox()
        self.timer_seconds.setRange(0, 59)
        
        self.timer_message = QLineEdit()
        self.timer_message.setPlaceholderText("可选提醒消息")
        
        time_layout = QHBoxLayout()
        time_layout.addWidget(QLabel("小时:"))
        time_layout.addWidget(self.timer_hours)
        time_layout.addWidget(QLabel("分钟:"))
        time_layout.addWidget(self.timer_minutes)
        time_layout.addWidget(QLabel("秒:"))
        time_layout.addWidget(self.timer_seconds)
        
        # 番茄工作法按钮
        self.pomodoro_btn = QPushButton("番茄工作法 (25分钟)")
        self.pomodoro_btn.clicked.connect(lambda: self.start_pomodoro(25, 5))
        
        pomodoro_layout = QHBoxLayout()
        pomodoro_layout.addWidget(self.pomodoro_btn)
        pomodoro_layout.addStretch()
        
        add_btn = QPushButton("添加计时器")
        add_btn.clicked.connect(self.add_timer)
        
        add_layout.addRow("名称:", self.timer_name)
        add_layout.addRow("时长:", time_layout)
        add_layout.addRow("消息:", self.timer_message)
        add_layout.addRow("快捷设置:", pomodoro_layout)
        add_layout.addRow(add_btn)
        
        add_group.setLayout(add_layout)
        
        # 计时器列表
        self.timer_list = QVBoxLayout()
        timer_list_group = QGroupBox("计时器列表")
        timer_list_group.setLayout(self.timer_list)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(timer_list_group)
        
        # 主布局
        layout.addWidget(add_group)
        layout.addWidget(scroll)

    
    def init_stopwatch_tab(self):
        """初始化秒表标签页"""
        self.stopwatch_tab = QWidget()
        self.tabs.addTab(self.stopwatch_tab, "秒表")
        
        layout = QVBoxLayout()
        self.stopwatch_tab.setLayout(layout)
        
        # 添加秒表表单
        add_group = QGroupBox("添加新秒表")
        add_layout = QFormLayout()
        
        self.stopwatch_name = QLineEdit()
        self.stopwatch_name.setPlaceholderText("秒表名称")
        
        # 统计按钮
        self.stats_btn = QPushButton("查看统计")
        self.stats_btn.clicked.connect(self.show_lap_stats)
        
        stats_layout = QHBoxLayout()
        stats_layout.addWidget(self.stats_btn)
        stats_layout.addStretch()
        
        add_btn = QPushButton("添加秒表")
        add_btn.clicked.connect(self.add_stopwatch)
        
        add_layout.addRow("名称:", self.stopwatch_name)
        add_layout.addRow("统计功能:", stats_layout)
        add_layout.addRow(add_btn)
        
        add_group.setLayout(add_layout)
        
        # 秒表列表
        self.stopwatch_list = QVBoxLayout()
        stopwatch_list_group = QGroupBox("秒表列表")
        stopwatch_list_group.setLayout(self.stopwatch_list)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(stopwatch_list_group)
        
        # 主布局
        layout.addWidget(add_group)
        layout.addWidget(scroll)

    
    def load_alarms(self):
        # 清空现有闹钟列表
        while self.alarm_list.count():
            item = self.alarm_list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # 从数据库加载闹钟
        cursor = self.db_conn.cursor()
        cursor.execute('SELECT id, name, alarm_time, repeat_days, enabled FROM alarms ORDER BY alarm_time')
        alarms = cursor.fetchall()
        
        for alarm in alarms:
            alarm_id, name, alarm_time, repeat_days, enabled = alarm
            alarm_widget = AlarmItemWidget(alarm_id, name, alarm_time, repeat_days, enabled, self)
            self.alarm_list.addWidget(alarm_widget)
        
        self.alarm_list.addStretch()
    
    def load_timers(self):
        # 清空现有计时器列表
        while self.timer_list.count():
            item = self.timer_list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # 从数据库加载计时器
        cursor = self.db_conn.cursor()
        cursor.execute('SELECT id, name, duration, remaining, enabled FROM timers ORDER BY created_at')
        timers = cursor.fetchall()
        
        self.active_timers = {}
        
        for timer in timers:
            timer_id, name, duration, remaining, enabled = timer
            timer_widget = TimerItemWidget(timer_id, name, duration, remaining, enabled, self)
            self.timer_list.addWidget(timer_widget)
            
            if enabled and remaining > 0:
                self.active_timers[timer_id] = {
                    'widget': timer_widget,
                    'target_time': QDateTime.currentDateTime().addSecs(remaining)
                }
        
        self.timer_list.addStretch()
    
    def load_stopwatches(self):
        # 清空现有秒表列表
        while self.stopwatch_list.count():
            item = self.stopwatch_list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # 从数据库加载秒表
        cursor = self.db_conn.cursor()
        cursor.execute('SELECT id, name, elapsed_time, running FROM stopwatches ORDER BY created_at')
        stopwatches = cursor.fetchall()
        
        for stopwatch in stopwatches:
            stopwatch_id, name, elapsed_time, running = stopwatch
            stopwatch_widget = StopwatchItemWidget(stopwatch_id, name, elapsed_time, running, self)
            self.stopwatch_list.addWidget(stopwatch_widget)
        
        self.stopwatch_list.addStretch()
    
    def add_alarm(self):
        name = self.alarm_name.text().strip()
        if not name:
            QMessageBox.warning(self, "错误", "请输入闹钟名称!")
            return
        
        alarm_time = self.alarm_time.time().toString("HH:mm:ss")
        repeat_days = self.alarm_repeat.currentData()
        
        if repeat_days == "custom":
            # 显示自定义重复对话框
            custom_dialog = QDialog(self)
            custom_dialog.setWindowTitle("自定义重复")
            
            layout = QVBoxLayout()
            days_group = QGroupBox("选择重复日期")
            days_layout = QVBoxLayout()
            
            self.day_checks = []
            day_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
            
            for i, day in enumerate(day_names, 1):
                check = QCheckBox(day)
                check.setProperty('day', str(i))
                self.day_checks.append(check)
                days_layout.addWidget(check)
            
            days_group.setLayout(days_layout)
            
            button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            button_box.accepted.connect(custom_dialog.accept)
            button_box.rejected.connect(custom_dialog.reject)
            
            layout.addWidget(days_group)
            layout.addWidget(button_box)
            
            custom_dialog.setLayout(layout)
            
            if custom_dialog.exec_() == QDialog.Accepted:
                selected_days = [check.property('day') for check in self.day_checks if check.isChecked()]
                if not selected_days:
                    QMessageBox.warning(self, "错误", "请至少选择一个重复日期!")
                    return
                repeat_days = ','.join(selected_days)
            else:
                return
        
        message = self.alarm_message.text().strip()
        
        try:
            cursor = self.db_conn.cursor()
            cursor.execute('''
            INSERT INTO alarms (name, alarm_time, repeat_days, message) 
            VALUES (?, ?, ?, ?)
            ''', (name, alarm_time, repeat_days, message))
            self.db_conn.commit()
            
            # 清空表单
            self.alarm_name.clear()
            self.alarm_message.clear()
            
            # 重新加载闹钟列表
            self.load_alarms()
            
            self.status_bar.showMessage("闹钟添加成功!", 3000)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"添加闹钟失败: {str(e)}")
    
    def add_timer(self):
        name = self.timer_name.text().strip()
        if not name:
            QMessageBox.warning(self, "错误", "请输入计时器名称!")
            return
        
        hours = self.timer_hours.value()
        minutes = self.timer_minutes.value()
        seconds = self.timer_seconds.value()
        
        if hours == 0 and minutes == 0 and seconds == 0:
            QMessageBox.warning(self, "错误", "计时器时长不能为0!")
            return
        
        total_seconds = hours * 3600 + minutes * 60 + seconds
        message = self.timer_message.text().strip()
        
        try:
            cursor = self.db_conn.cursor()
            cursor.execute('''
            INSERT INTO timers (name, duration, remaining, message) 
            VALUES (?, ?, ?, ?)
            ''', (name, total_seconds, total_seconds, message))
            self.db_conn.commit()
            
            # 清空表单
            self.timer_name.clear()
            self.timer_hours.setValue(0)
            self.timer_minutes.setValue(0)
            self.timer_seconds.setValue(0)
            self.timer_message.clear()
            
            # 重新加载计时器列表
            self.load_timers()
            
            self.status_bar.showMessage("计时器添加成功!", 3000)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"添加计时器失败: {str(e)}")
    
    def add_stopwatch(self):
        name = self.stopwatch_name.text().strip()
        if not name:
            QMessageBox.warning(self, "错误", "请输入秒表名称!")
            return
        
        try:
            cursor = self.db_conn.cursor()
            cursor.execute('''
            INSERT INTO stopwatches (name) 
            VALUES (?)
            ''', (name,))
            self.db_conn.commit()
            
            # 清空表单
            self.stopwatch_name.clear()
            
            # 重新加载秒表列表
            self.load_stopwatches()
            
            self.status_bar.showMessage("秒表添加成功!", 3000)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"添加秒表失败: {str(e)}")
    
    def toggle_alarm(self, alarm_id, enabled):
        try:
            cursor = self.db_conn.cursor()
            cursor.execute('UPDATE alarms SET enabled = ? WHERE id = ?', (enabled, alarm_id))
            self.db_conn.commit()
            
            self.status_bar.showMessage(f"闹钟已{'启用' if enabled else '禁用'}", 2000)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"更新闹钟状态失败: {str(e)}")
    
    def toggle_timer(self, timer_id, enabled):
        try:
            cursor = self.db_conn.cursor()
            cursor.execute('UPDATE timers SET enabled = ? WHERE id = ?', (enabled, timer_id))
            self.db_conn.commit()
            
            # 更新活动计时器列表
            if enabled:
                cursor.execute('SELECT duration, remaining FROM timers WHERE id = ?', (timer_id,))
                duration, remaining = cursor.fetchone()
                
                if remaining > 0:
                    self.active_timers[timer_id] = {
                        'widget': None,  # 将在update_timers中设置
                        'target_time': QDateTime.currentDateTime().addSecs(remaining)
                    }
            else:
                if timer_id in self.active_timers:
                    del self.active_timers[timer_id]
            
            self.status_bar.showMessage(f"计时器已{'启用' if enabled else '禁用'}", 2000)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"更新计时器状态失败: {str(e)}")
    
    def start_timer(self, timer_id):
        try:
            cursor = self.db_conn.cursor()
            cursor.execute('SELECT remaining FROM timers WHERE id = ?', (timer_id,))
            remaining = cursor.fetchone()[0]
            
            target_time = QDateTime.currentDateTime().addSecs(remaining)
            
            # 更新活动计时器列表
            for i in range(self.timer_list.count()):
                item = self.timer_list.itemAt(i)
                if item.widget() and hasattr(item.widget(), 'timer_id') and item.widget().timer_id == timer_id:
                    self.active_timers[timer_id] = {
                        'widget': item.widget(),
                        'target_time': target_time
                    }
                    break
            
            self.status_bar.showMessage("计时器已启动", 2000)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"启动计时器失败: {str(e)}")
    
    def stop_timer(self, timer_id):
        try:
            if timer_id in self.active_timers:
                # 更新剩余时间
                target_time = self.active_timers[timer_id]['target_time']
                remaining = QDateTime.currentDateTime().secsTo(target_time)
                
                cursor = self.db_conn.cursor()
                cursor.execute('UPDATE timers SET remaining = ? WHERE id = ?', (remaining, timer_id))
                self.db_conn.commit()
                
                # 从活动计时器列表中移除
                del self.active_timers[timer_id]
                
                self.status_bar.showMessage("计时器已停止", 2000)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"停止计时器失败: {str(e)}")
    
    def reset_timer(self, timer_id):
        try:
            if timer_id in self.active_timers:
                del self.active_timers[timer_id]
            
            cursor = self.db_conn.cursor()
            cursor.execute('UPDATE timers SET remaining = duration WHERE id = ?', (timer_id,))
            self.db_conn.commit()
            
            self.status_bar.showMessage("计时器已重置", 2000)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"重置计时器失败: {str(e)}")
    
    def start_stopwatch(self, stopwatch_id):
        try:
            cursor = self.db_conn.cursor()
            cursor.execute('UPDATE stopwatches SET running = 1, start_time = datetime("now") WHERE id = ?', (stopwatch_id,))
            self.db_conn.commit()
            
            self.status_bar.showMessage("秒表已启动", 2000)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"启动秒表失败: {str(e)}")
    
    def stop_stopwatch(self, stopwatch_id):
        try:
            cursor = self.db_conn.cursor()
            
            # 获取当前运行时间
            cursor.execute('SELECT start_time FROM stopwatches WHERE id = ?', (stopwatch_id,))
            start_time_str = cursor.fetchone()[0]
            start_time = datetime.datetime.strptime(start_time_str, '%Y-%m-%d %H:%M:%S')
            elapsed = (datetime.datetime.now() - start_time).total_seconds()
            
            # 更新数据库
            cursor.execute('''
            UPDATE stopwatches 
            SET running = 0, elapsed_time = elapsed_time + ?, start_time = NULL 
            WHERE id = ?
            ''', (elapsed, stopwatch_id))
            self.db_conn.commit()
            
            self.status_bar.showMessage("秒表已停止", 2000)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"停止秒表失败: {str(e)}")
    
    def reset_stopwatch(self, stopwatch_id):
        try:
            cursor = self.db_conn.cursor()
            cursor.execute('UPDATE stopwatches SET elapsed_time = 0, laps = NULL WHERE id = ?', (stopwatch_id,))
            self.db_conn.commit()
            
            self.status_bar.showMessage("秒表已重置", 2000)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"重置秒表失败: {str(e)}")
    
    def record_lap(self, stopwatch_id, lap_time):
        try:
            cursor = self.db_conn.cursor()
            
            # 获取现有计次
            cursor.execute('SELECT laps FROM stopwatches WHERE id = ?', (stopwatch_id,))
            laps_str = cursor.fetchone()[0] or ""
            laps = laps_str.split(',') if laps_str else []
            
            # 添加新计次
            laps.append(str(lap_time))
            new_laps_str = ','.join(laps)
            
            # 更新数据库
            cursor.execute('UPDATE stopwatches SET laps = ? WHERE id = ?', (new_laps_str, stopwatch_id))
            self.db_conn.commit()
            
            self.status_bar.showMessage("计次已记录", 2000)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"记录计次失败: {str(e)}")
    
    def delete_alarm(self, alarm_id):
        try:
            cursor = self.db_conn.cursor()
            cursor.execute('DELETE FROM alarms WHERE id = ?', (alarm_id,))
            self.db_conn.commit()
            
            self.load_alarms()
            self.status_bar.showMessage("闹钟已删除", 2000)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"删除闹钟失败: {str(e)}")
    
    def delete_timer(self, timer_id):
        try:
            if timer_id in self.active_timers:
                del self.active_timers[timer_id]
            
            cursor = self.db_conn.cursor()
            cursor.execute('DELETE FROM timers WHERE id = ?', (timer_id,))
            self.db_conn.commit()
            
            self.load_timers()
            self.status_bar.showMessage("计时器已删除", 2000)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"删除计时器失败: {str(e)}")
    
    def delete_stopwatch(self, stopwatch_id):
        try:
            cursor = self.db_conn.cursor()
            cursor.execute('DELETE FROM stopwatches WHERE id = ?', (stopwatch_id,))
            self.db_conn.commit()
            
            self.load_stopwatches()
            self.status_bar.showMessage("秒表已删除", 2000)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"删除秒表失败: {str(e)}")
    
    def check_alarms(self):
        now = datetime.datetime.now()
        current_time = now.strftime("%H:%M:%S")
        current_weekday = str(now.isoweekday())

        cursor = self.db_conn.cursor()
        cursor.execute('''
        SELECT id, name, message, alarm_time FROM alarms 
        WHERE enabled = 1 AND 
        (repeat_days IS NULL OR repeat_days = '' OR repeat_days LIKE ? OR repeat_days LIKE ? OR repeat_days LIKE ?)
        ''', (f'%{current_weekday}%',
            f'{current_weekday},%',
            f'%,{current_weekday}'))
        
        alarms = cursor.fetchall()
        
        for alarm in alarms:
            alarm_id, name, message, alarm_time_str = alarm
            alarm_time = datetime.datetime.strptime(alarm_time_str, "%H:%M:%S").time()
            
            # 计算距离闹钟响起的时间差(秒)
            alarm_datetime = datetime.datetime.combine(datetime.date.today(), alarm_time)
            if alarm_datetime < now:
                alarm_datetime += datetime.timedelta(days=1)  # 如果今天已经过了，就设置为明天的这个时间
                
            time_diff = (alarm_datetime - now).total_seconds()
            
            # 找到对应的闹钟widget并更新进度条
            for i in range(self.alarm_list.count()):
                item = self.alarm_list.itemAt(i)
                if item.widget() and hasattr(item.widget(), 'alarm_id') and item.widget().alarm_id == alarm_id:
                    widget = item.widget()
                    
                    # 计算从上次检查到闹钟时间的总秒数
                    if not hasattr(widget, 'total_seconds_to_alarm'):
                        widget.total_seconds_to_alarm = time_diff
                    
                    # 计算进度百分比（基于从闹钟创建到响铃的总时间）
                    if widget.total_seconds_to_alarm > 0:
                        progress = 100 - int((time_diff / widget.total_seconds_to_alarm) * 100)
                        progress = max(0, min(100, progress))
                    else:
                        progress = 100
                    
                    widget.progress_bar.setValue(progress)
                    
                    # 根据进度设置不同颜色
                    if progress < 30:  # 0-30% 蓝色
                        color = "#5BC0DE"
                    elif progress < 70:  # 30-70% 黄色
                        color = "#FFD166"
                    else:  # 70-100% 红色
                        color = "#FF6B6B"
                    
                    # 更新进度条样式
                    widget.progress_bar.setStyleSheet(f"""
                        QProgressBar {{
                            border: 1px solid grey;
                            border-radius: 5px;
                            text-align: center;
                        }}
                        QProgressBar::chunk {{
                            background-color: {color};
                            width: 10px;
                        }}
                    """)
                    
                    # 设置不同时间段的显示格式
                    if time_diff > 3600:  # 超过1小时
                        hours = int(time_diff // 3600)
                        minutes = int((time_diff % 3600) // 60)
                        widget.progress_bar.setFormat(f"{hours}小时{minutes}分钟后响铃 ({progress}%)")
                    elif time_diff > 60:  # 1分钟到1小时
                        minutes = int(time_diff // 60)
                        seconds = int(time_diff % 60)
                        widget.progress_bar.setFormat(f"{minutes}分钟{seconds}秒后响铃 ({progress}%)")
                    else:  # 1分钟以内
                        widget.progress_bar.setFormat(f"{int(time_diff)}秒后响铃 ({progress}%)")
                    
                    # 如果闹钟时间到
                    if current_time == alarm_time_str:
                        # 显示提醒
                        msg = QMessageBox(self)
                        msg.setWindowTitle("闹钟提醒")
                        msg.setText(f"闹钟: {name}\n时间: {current_time}")
                        
                        if message:
                            msg.setInformativeText(message)
                        
                        msg.setStandardButtons(QMessageBox.Ok)
                        msg.exec_()
                        
                        # 更新最后触发时间
                        cursor.execute('UPDATE alarms SET last_triggered = datetime("now") WHERE id = ?', (alarm_id,))
                        self.db_conn.commit()
                        
                        # 重置进度条
                        widget.progress_bar.setValue(100)
                        widget.progress_bar.setFormat("已响铃")
                        widget.progress_bar.setStyleSheet("""
                            QProgressBar {
                                border: 1px solid grey;
                                border-radius: 5px;
                                text-align: center;
                            }
                            QProgressBar::chunk {
                                background-color: #5BC0DE;
                                width: 10px;
                            }
                        """)
                    
                    break





    
    def update_timers(self):
        now = QDateTime.currentDateTime()
        expired_timers = []
        
        for timer_id, timer_data in list(self.active_timers.items()):
            target_time = timer_data['target_time']
            remaining = now.secsTo(target_time)
            
            if remaining <= 0:
                expired_timers.append(timer_id)
                remaining = 0
            
            # 更新UI
            if timer_data['widget']:
                timer_data['widget'].update_remaining_time(remaining)
            else:
                # 找到对应的widget并设置
                for i in range(self.timer_list.count()):
                    item = self.timer_list.itemAt(i)
                    if item.widget() and hasattr(item.widget(), 'timer_id') and item.widget().timer_id == timer_id:
                        timer_data['widget'] = item.widget()
                        item.widget().update_remaining_time(remaining)
                        break
        
        # 处理过期的计时器
        for timer_id in expired_timers:
            # 显示提醒
            timer_data = self.active_timers[timer_id]
            widget = timer_data['widget']
            
            msg = QMessageBox(self)
            msg.setWindowTitle("计时器提醒")
            msg.setText(f"计时器: {widget.name_label.text()}\n时间到!")
            
            cursor = self.db_conn.cursor()
            cursor.execute('SELECT message FROM timers WHERE id = ?', (timer_id,))
            message = cursor.fetchone()[0]
            
            if message:
                msg.setInformativeText(message)
            
            msg.setStandardButtons(QMessageBox.Ok)
            msg.exec_()
            
            # 从活动计时器列表中移除
            del self.active_timers[timer_id]
            
            # 更新数据库
            cursor.execute('UPDATE timers SET remaining = 0, last_triggered = datetime("now") WHERE id = ?', (timer_id,))
            self.db_conn.commit()
    
    def manual_backup(self):
        success, result = self.backup_manager.create_backup(backup_type='manual')
        if success:
            QMessageBox.information(self, "成功", "手动备份创建成功!")
        else:
            QMessageBox.critical(self, "错误", f"备份失败: {result}")
    
    def auto_backup(self):
        self.backup_manager.create_backup(backup_type='auto')
    
    def show_restore_dialog(self):
        dialog = RestoreDatabaseDialog(self.backup_manager, self)
        if dialog.exec_() == QDialog.Accepted:
            # 重新初始化数据库连接
            self.db_conn.close()
            self.db_conn = init_db(self.user_db_path)
            
            # 重新加载所有数据
            self.load_alarms()
            self.load_timers()
            self.load_stopwatches()
            
            QMessageBox.information(self, "成功", "数据库恢复完成，所有数据已刷新!")
    
    def show_settings_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("设置")
        layout = QFormLayout()
        
        # 自动备份数量设置
        backup_count = QSpinBox()
        backup_count.setRange(1, 100)
        backup_count.setValue(self.max_backups)
        
        save_btn = QPushButton("保存")
        save_btn.clicked.connect(lambda: self.save_settings(backup_count.value(), dialog))
        
        layout.addRow("最大备份数量:", backup_count)
        layout.addRow(save_btn)
        
        dialog.setLayout(layout)
        dialog.exec_()
    
    def save_settings(self, max_backups, dialog):
        self.max_backups = max_backups
        self.backup_manager.set_max_backups(max_backups)
        self.user_manager.set_user_setting(self.username, 'max_backups', str(max_backups))
        dialog.accept()
        self.status_bar.showMessage("设置已保存", 2000)



    def show_about_dialog(self):
        QMessageBox.about(self, "关于", 
                         "多功能闹钟程序\n\n"
                         "功能包括:\n"
                         "- 闹钟设置\n"
                         "- 计时器\n"
                         "- 秒表\n\n"
                         "版本: 1.0\n"
                         "作者: Your Name")
    
    def logout(self):
        # 关闭数据库连接
        self.db_conn.close()
        
        # 停止所有定时器
        self.alarm_check_timer.stop()
        self.timer_update_timer.stop()
        self.auto_backup_timer.stop()
        
        # 关闭窗口
        self.close()
        
        # 重新显示用户选择窗口
        app = QApplication.instance()
        login_window = UserLoginWindow(self.user_manager, self.app_dir)
        login_window.show()
    
    def closeEvent(self, event):
        # 关闭数据库连接
        self.db_conn.close()
        event.accept()


    def show_smart_home_settings(self):
        """显示智能家居设置对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle("智能家居设置")
        layout = QFormLayout()
        
        # 智能家居类型选择
        type_combo = QComboBox()
        type_combo.addItem("Home Assistant", "homeassistant")
        type_combo.addItem("小米米家", "mi")
        type_combo.addItem("MQTT", "mqtt")
        
        # 从设置加载当前值
        current_type = self.user_manager.get_user_setting(self.username, 'smart_home_type', '')
        if current_type:
            index = type_combo.findData(current_type)
            if index >= 0:
                type_combo.setCurrentIndex(index)
        
        # API设置字段
        url_edit = QLineEdit()
        url_edit.setPlaceholderText("API地址")
        url_edit.setText(self.user_manager.get_user_setting(self.username, 'ha_api_url', ''))
        
        key_edit = QLineEdit()
        key_edit.setPlaceholderText("API密钥")
        key_edit.setText(self.user_manager.get_user_setting(self.username, 'ha_api_key', ''))
        
        # 保存按钮
        save_btn = QPushButton("保存")
        save_btn.clicked.connect(lambda: self.save_smart_home_settings(
            type_combo.currentData(),
            url_edit.text(),
            key_edit.text(),
            dialog
        ))
        
        layout.addRow("智能家居平台:", type_combo)
        layout.addRow("API地址:", url_edit)
        layout.addRow("API密钥:", key_edit)
        layout.addRow(save_btn)
        
        dialog.setLayout(layout)
        dialog.exec_()

    def save_smart_home_settings(self, platform, url, key, dialog):
        """保存智能家居设置"""
        self.user_manager.set_user_setting(self.username, 'smart_home_type', platform)
        self.user_manager.set_user_setting(self.username, 'ha_api_url', url)
        self.user_manager.set_user_setting(self.username, 'ha_api_key', key)
        
        # 重新初始化智能家居连接
        self.init_smart_home()
        
        dialog.accept()
        self.status_bar.showMessage("智能家居设置已保存", 3000)

    def show_lap_stats(self):
        """显示秒表统计信息"""
        # 获取当前选中的秒表
        selected = None
        for i in range(self.stopwatch_list.count()):
            item = self.stopwatch_list.itemAt(i)
            if item.widget() and hasattr(item.widget(), 'stopwatch_id'):
                selected = item.widget()
                break
        
        if not selected:
            QMessageBox.warning(self, "错误", "请先选择秒表!")
            return
        
        stats = self.save_lap_statistics(selected.stopwatch_id)
        if stats:
            QMessageBox.information(self, "秒表统计", stats)


# 用户登录窗口
class UserLoginWindow(QMainWindow):
    def __init__(self, user_manager, app_dir):
        super().__init__()
        self.user_manager = user_manager
        self.app_dir = app_dir
        
        self.setWindowTitle("闹钟程序 - 用户登录")
        self.setMinimumSize(400, 300)
        
        # 设置图标
        icon_path = os.path.join(app_dir, 'icon.ico')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        self.init_ui()
    
    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        
        layout = QVBoxLayout()
        main_widget.setLayout(layout)
        
        # 标题
        title = QLabel("闹钟程序")
        title.setAlignment(Qt.AlignCenter)
        title_font = QFont()
        title_font.setPointSize(20)
        title_font.setBold(True)
        title.setFont(title_font)
        
        # 用户列表
        self.user_list = QListWidget()
        self.load_users()
        self.user_list.itemDoubleClicked.connect(self.login)
        
        # 按钮
        button_layout = QHBoxLayout()
        
        self.login_button = QPushButton("登录")
        self.login_button.clicked.connect(self.login)
        
        self.add_user_button = QPushButton("添加用户")
        self.add_user_button.clicked.connect(self.add_user)
        
        self.manage_users_button = QPushButton("管理用户")
        self.manage_users_button.clicked.connect(self.manage_users)
        
        button_layout.addWidget(self.login_button)
        button_layout.addWidget(self.add_user_button)
        button_layout.addWidget(self.manage_users_button)
        
        # 布局
        layout.addWidget(title)
        layout.addWidget(self.user_list)
        layout.addLayout(button_layout)
    
    def load_users(self):
        self.user_list.clear()
        users = self.user_manager.get_all_users()
        
        for user in users:
            item = QListWidgetItem(user['username'])
            if user['last_login']:
                item.setToolTip(f"最后登录: {user['last_login']}")
            self.user_list.addItem(item)
    
    def login(self):
        selected_items = self.user_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "错误", "请选择一个用户!")
            return
            
        username = selected_items[0].text()
        self.user_manager.set_current_user(username)
        
        # 打开主窗口
        self.main_window = AlarmClockApp(self.user_manager, username, self.app_dir)
        self.main_window.show()
        
        # 关闭登录窗口
        self.close()
    
    def add_user(self):
        username, ok = QInputDialog.getText(
            self, "添加用户", "输入用户名:", QLineEdit.Normal
        )
        
        if ok and username.strip():
            success, message = self.user_manager.add_user(username.strip())
            if success:
                self.load_users()
                QMessageBox.information(self, "成功", message)
            else:
                QMessageBox.warning(self, "错误", message)
    
    def manage_users(self):
        dialog = UserManagerDialog(self.user_manager, self)
        dialog.exec_()
        self.load_users()

# 主函数
def main():
    # 获取应用目录
    if getattr(sys, 'frozen', False):
        app_dir = os.path.dirname(sys.executable)
    else:
        app_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 创建必要目录
    os.makedirs(os.path.join(app_dir, 'user_dbs'), exist_ok=True)
    os.makedirs(os.path.join(app_dir, 'backups'), exist_ok=True)
    
    # 初始化用户管理器
    user_manager = UserManager(app_dir)
    
    # 创建应用
    app = QApplication(sys.argv)
    
    # 设置中文
    font = QFont()
    font.setFamily("Microsoft YaHei")
    app.setFont(font)
    
    # 显示登录窗口
    login_window = UserLoginWindow(user_manager, app_dir)
    login_window.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()