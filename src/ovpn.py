from src.ssh import SSHClient
import re
import time

def wait_for_prompt(channel, prompt, timeout=30):
    """Ждёт появления строки prompt в выводе канала."""
    buffer = ""
    start = time.time()
    while True:
        if channel.recv_ready():
            buffer += channel.recv(4096).decode('utf-8')
            print(buffer)  # Для отладки
            if prompt in buffer:
                return buffer
        if time.time() - start > timeout:
            raise TimeoutError(f"Не дождался приглашения: {prompt}")
        time.sleep(0.5)

def create_openvpn_user(client_name, hostname, username, password, port=22):
    """
    Создаёт нового OpenVPN пользователя на сервере через adduser.sh и возвращает содержимое .ovpn файла.
    :param client_name: Имя нового клиента (строка)
    :param hostname: IP или домен сервера
    :param username: SSH-пользователь (обычно root)
    :param password: SSH-пароль
    :param port: SSH-порт (по умолчанию 22)
    :return: Строка с содержимым .ovpn файла
    """
    ssh = SSHClient(hostname=hostname, username=username, password=password, port=port)
    try:
        ssh.connect()
        
        # Запускаем adduser.sh с именем клиента
        exit_code, stdout, stderr = ssh.execute_command(f'./adduser.sh {client_name}')
        output = stdout + stderr
        print(output)

        # Ищем путь к .ovpn файлу
        match = re.search(r'Конфигурационный файл создан: (.+\.ovpn)', output)
        if match:
            remote_path = match.group(1).strip()
        else:
            remote_path = f'/root/{client_name}.ovpn'
        
        # Считываем содержимое файла на сервере и возвращаем как строку
        exit_code, file_content, file_err = ssh.execute_command(f'cat "{remote_path}"')
        if exit_code != 0:
            raise Exception(f"Ошибка при чтении .ovpn файла: {file_err}")
        return file_content
    finally:
        ssh.close()

def revoke_openvpn_user(client_name, hostname, username, password, port=22):
    """
    Удаляет OpenVPN пользователя на сервере через removeuser.sh.
    :param client_name: Имя клиента для удаления (строка)
    :param hostname: IP или домен сервера
    :param username: SSH-пользователь (обычно root)
    :param password: SSH-пароль
    :param port: SSH-порт (по умолчанию 22)
    :return: True, если успешно, иначе False
    """
    ssh = SSHClient(hostname=hostname, username=username, password=password, port=port)
    try:
        ssh.connect()
        
        # Запускаем removeuser.sh с именем клиента
        exit_code, stdout, stderr = ssh.execute_command(f'./removeuser.sh {client_name}')
        output = stdout + stderr
        print(output)

        # Проверяем успешность удаления
        return f'Пользователь {client_name} успешно удален' in output
    finally:
        ssh.close()

# Пример использования:
# file_path = create_openvpn_user(
#     client_name='suka4',
#     hostname='77.239.112.108',
#     username='root',
#     password='fi4CBXe0fVDb'
# )
# print(f'Файл сохранён: {file_path}')

# revoke_openvpn_user(
#     client_name='suka4',
#     hostname='77.239.112.108',
#     username='root',
#     password='fi4CBXe0fVDb')
