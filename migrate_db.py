import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from src.database import engine
from src import models
from src.database import DATABASE_URL

# Загружаем переменные окружения
load_dotenv()

def migrate_database():
    """Миграция базы данных для новой структуры VPN конфигураций"""
    
    # Создаем новые таблицы
    models.Base.metadata.create_all(bind=engine)
    
    with engine.connect() as connection:
        print("Начинаем миграцию базы данных...")
        
        # Проверяем существующие таблицы
        tables_result = connection.execute(text("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """))
        existing_tables = [row[0] for row in tables_result]
        print(f"Существующие таблицы: {existing_tables}")
        
        # Проверяем структуру таблицы users
        if 'users' in existing_tables:
            columns_result = connection.execute(text("""
                SELECT column_name, data_type FROM information_schema.columns 
                WHERE table_name = 'users'
                ORDER BY column_name;
            """))
            user_columns = {row[0]: row[1] for row in columns_result}
            print(f"Колонки таблицы users: {user_columns}")
        
        # Проверяем, существует ли старая таблица subscriptions
        result = connection.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'subscriptions'
            );
        """))
        
        if result.scalar():
            print("Обнаружена старая структура с таблицей subscriptions")
            print("Выполняем миграцию данных...")
            
            # Создаем базовые протоколы
            connection.execute(text("""
                INSERT INTO protocols (name, description) VALUES 
                ('openvpn', 'OpenVPN протокол'),
                ('wireguard', 'WireGuard протокол')
                ON CONFLICT (name) DO NOTHING;
            """))
            
            # Создаем базовый сервер (если нужно)
            connection.execute(text("""
                INSERT INTO servers (name, host, port, country) VALUES 
                ('default_server', 'vpn.example.com', 1194, 'Unknown')
                ON CONFLICT (name) DO NOTHING;
            """))
            
            # Получаем ID базового сервера и протокола
            server_result = connection.execute(text("SELECT id FROM servers WHERE name = 'default_server' LIMIT 1;"))
            server_id = server_result.scalar()
            
            protocol_result = connection.execute(text("SELECT id FROM protocols WHERE name = 'openvpn' LIMIT 1;"))
            protocol_id = protocol_result.scalar()
            
            if server_id and protocol_id:
                # Проверяем, есть ли таблица vpn_configs
                vpn_configs_exists = connection.execute(text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'vpn_configs'
                    );
                """)).scalar()
                
                if vpn_configs_exists:
                    # Проверяем колонки таблицы vpn_configs
                    vpn_columns_result = connection.execute(text("""
                        SELECT column_name FROM information_schema.columns 
                        WHERE table_name = 'vpn_configs'
                        ORDER BY column_name;
                    """))
                    vpn_columns = [row[0] for row in vpn_columns_result]
                    print(f"Колонки таблицы vpn_configs: {vpn_columns}")
                    
                    # Мигрируем VPN конфигурации в новую структуру
                    if 'user_id' in vpn_columns:
                        connection.execute(text("""
                            INSERT INTO user_configs (user_id, server_id, protocol_id, config_name, config_content, created_at, is_active)
                            SELECT 
                                u.id as user_id,
                                %s as server_id,
                                %s as protocol_id,
                                COALESCE(vc.config_name, 'Migrated Config') as config_name,
                                vc.config_content,
                                COALESCE(vc.created_at, NOW()) as created_at,
                                vc.is_active
                            FROM vpn_configs vc
                            JOIN users u ON vc.user_id = u.id
                            WHERE vc.is_active = TRUE
                            ON CONFLICT DO NOTHING;
                        """), (server_id, protocol_id))
                        
                        # Создаем записи о покупках для существующих конфигов
                        connection.execute(text("""
                            INSERT INTO purchases (user_id, config_id, amount, duration_days, purchase_type, created_at)
                            SELECT 
                                uc.user_id,
                                uc.id as config_id,
                                0.00 as amount,
                                30 as duration_days,
                                'migration' as purchase_type,
                                uc.created_at
                            FROM user_configs uc
                            WHERE uc.created_at IS NOT NULL
                            ON CONFLICT DO NOTHING;
                        """))
                        
                        print("Данные успешно мигрированы!")
                    else:
                        print("Таблица vpn_configs не содержит колонку user_id, пропускаем миграцию данных")
                else:
                    print("Таблица vpn_configs не существует, пропускаем миграцию данных")
            else:
                print("Ошибка: не удалось найти базовый сервер или протокол")
        
        else:
            print("Старая структура не обнаружена, создаем новую базу данных")
            
            # Создаем базовые протоколы
            connection.execute(text("""
                INSERT INTO protocols (name, description) VALUES 
                ('openvpn', 'OpenVPN протокол'),
                ('wireguard', 'WireGuard протокол')
                ON CONFLICT (name) DO NOTHING;
            """))
            
            # Создаем базовый сервер
            connection.execute(text("""
                INSERT INTO servers (name, host, port, country) VALUES 
                ('default_server', 'vpn.example.com', 1194, 'Unknown')
                ON CONFLICT (name) DO NOTHING;
            """))
            
            # Добавляем колонки для бесплатного пробного периода (если их нет)
            try:
                connection.execute(text("""
                    ALTER TABLE users 
                    ADD COLUMN IF NOT EXISTS free_trial_used BOOLEAN DEFAULT FALSE,
                    ADD COLUMN IF NOT EXISTS free_trial_expires_at TIMESTAMP WITH TIME ZONE;
                """))
                print("Колонки для бесплатного пробного периода добавлены")
            except Exception as e:
                print(f"Ошибка при добавлении колонок для бесплатного пробного периода: {e}")
            
            print("Базовая структура создана!")
        
        # Удаляем старые таблицы (если они существуют)
        try:
            connection.execute(text("DROP TABLE IF EXISTS vpn_configs CASCADE;"))
            connection.execute(text("DROP TABLE IF EXISTS subscriptions CASCADE;"))
            print("Старые таблицы удалены")
        except Exception as e:
            print(f"Ошибка при удалении старых таблиц: {e}")
        
        connection.commit()
        print("Миграция завершена успешно!")

def migrate_notification_logs():
    """Добавляет таблицу notification_logs в базу данных"""
    engine = create_engine(DATABASE_URL)
    
    with engine.connect() as conn:
        # Проверяем, существует ли таблица
        result = conn.execute(text("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='notification_logs'
        """))
        
        if not result.fetchone():
            # Создаем таблицу notification_logs
            conn.execute(text("""
                CREATE TABLE notification_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    config_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    notification_type VARCHAR NOT NULL,
                    sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    expires_at DATETIME NOT NULL,
                    FOREIGN KEY (config_id) REFERENCES user_configs (id),
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """))
            
            # Создаем индексы для оптимизации запросов
            conn.execute(text("""
                CREATE INDEX idx_notification_logs_config_id 
                ON notification_logs (config_id)
            """))
            
            conn.execute(text("""
                CREATE INDEX idx_notification_logs_user_id 
                ON notification_logs (user_id)
            """))
            
            conn.execute(text("""
                CREATE INDEX idx_notification_logs_type 
                ON notification_logs (notification_type)
            """))
            
            conn.commit()
            print("✅ Таблица notification_logs успешно создана")
        else:
            print("ℹ️ Таблица notification_logs уже существует")

if __name__ == "__main__":
    migrate_database()
    migrate_notification_logs() 