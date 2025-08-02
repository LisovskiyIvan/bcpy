import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from src.database import engine
from src import models

# Загружаем переменные окружения
load_dotenv()

def migrate_database():
    """Миграция базы данных для новой структуры VPN конфигураций"""
    
    # Создаем новые таблицы
    models.Base.metadata.create_all(bind=engine)
    
    with engine.connect() as connection:
        # Проверяем, существует ли старая таблица vpn_configs
        result = connection.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'vpn_configs'
            );
        """))
        
        if result.scalar():
            # Проверяем, есть ли колонка user_id в старой таблице
            result = connection.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns 
                    WHERE table_name = 'vpn_configs' AND column_name = 'user_id'
                );
            """))
            
            if result.scalar():
                print("Обнаружена старая структура таблицы vpn_configs")
                print("Выполняем миграцию...")
                
                # Создаем временную таблицу с новой структурой
                connection.execute(text("""
                    CREATE TABLE IF NOT EXISTS vpn_configs_new (
                        id SERIAL PRIMARY KEY,
                        subscription_id INTEGER REFERENCES subscriptions(id),
                        config_name VARCHAR,
                        config_content TEXT,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        is_active BOOLEAN DEFAULT TRUE
                    );
                """))
                
                # Копируем данные из старой таблицы в новую
                # Для каждой VPN конфигурации находим активную подписку пользователя
                connection.execute(text("""
                    INSERT INTO vpn_configs_new (subscription_id, config_name, config_content, created_at, is_active)
                    SELECT 
                        s.id as subscription_id,
                        vc.config_name,
                        vc.config_content,
                        vc.created_at,
                        vc.is_active
                    FROM vpn_configs vc
                    JOIN users u ON vc.user_id = u.id
                    JOIN subscriptions s ON u.id = s.user_id
                    WHERE s.is_active = TRUE
                    AND vc.is_active = TRUE;
                """))
                
                # Удаляем старую таблицу
                connection.execute(text("DROP TABLE vpn_configs;"))
                
                # Переименовываем новую таблицу
                connection.execute(text("ALTER TABLE vpn_configs_new RENAME TO vpn_configs;"))
                
                print("Миграция завершена успешно!")
            else:
                print("Таблица vpn_configs уже имеет новую структуру")
        else:
            print("Таблица vpn_configs не существует, создаем новую структуру")
        
        connection.commit()

if __name__ == "__main__":
    migrate_database() 