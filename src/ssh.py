import paramiko
import os
from typing import Optional, Tuple, List

class SSHClient:
    def __init__(self, hostname: str, username: str, password: Optional[str] = None, 
                 key_filename: Optional[str] = None, port: int = 22):
        """
        Инициализация SSH клиента
        
        Args:
            hostname: Имя хоста или IP адрес
            username: Имя пользователя
            password: Пароль (опционально)
            key_filename: Путь к приватному ключу (опционально)
            port: Порт SSH (по умолчанию 22)
        """
        self.hostname = hostname
        self.username = username
        self.password = password
        self.key_filename = key_filename
        self.port = port
        self.client = None

    def connect(self) -> None:
        """Установка SSH соединения"""
        try:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.client.connect(
                hostname=self.hostname,
                username=self.username,
                password=self.password,
                key_filename=self.key_filename,
                port=self.port
            )
        except Exception as e:
            raise ConnectionError(f"Ошибка подключения к SSH: {str(e)}")

    def execute_command(self, command: str) -> Tuple[int, str, str]:
        """
        Выполнение команды на удаленном сервере
        
        Args:
            command: Команда для выполнения
            
        Returns:
            Tuple[int, str, str]: (код возврата, stdout, stderr)
        """
        if not self.client:
            raise ConnectionError("Нет активного SSH соединения")
        
        stdin, stdout, stderr = self.client.exec_command(command)
        return (
            stdout.channel.recv_exit_status(),
            stdout.read().decode('utf-8'),
            stderr.read().decode('utf-8')
        )

    def upload_file(self, local_path: str, remote_path: str) -> None:
        """
        Загрузка файла на удаленный сервер
        
        Args:
            local_path: Локальный путь к файлу
            remote_path: Удаленный путь для сохранения
        """
        if not self.client:
            raise ConnectionError("Нет активного SSH соединения")
        
        sftp = self.client.open_sftp()
        sftp.put(local_path, remote_path)
        sftp.close()

    def download_file(self, remote_path: str, local_path: str) -> None:
        """
        Скачивание файла с удаленного сервера
        
        Args:
            remote_path: Удаленный путь к файлу
            local_path: Локальный путь для сохранения
        """
        if not self.client:
            raise ConnectionError("Нет активного SSH соединения")
        
        sftp = self.client.open_sftp()
        sftp.get(remote_path, local_path)
        sftp.close()

    def close(self) -> None:
        """Закрытие SSH соединения"""
        if self.client:
            self.client.close()
            self.client = None
