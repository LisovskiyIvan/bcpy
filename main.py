from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, UTC
import asyncio
from typing import Optional
import uvicorn
import os
from dotenv import load_dotenv

from src import models, crud, ovpn
from src.database import SessionLocal, engine

# Загружаем переменные окружения
load_dotenv()

# Получаем параметры SSH из переменных окружения
SSH_HOST = os.getenv("SSH_HOST")
SSH_USERNAME = os.getenv("SSH_USERNAME")
SSH_PASSWORD = os.getenv("SSH_PASSWORD")
SSH_PORT = int(os.getenv("SSH_PORT", "22"))

# Создаем таблицы в базе данных
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="VPN API")

# Dependency для получения сессии базы данных
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Фоновые задачи
async def cleanup_inactive():
    while True:
        db = SessionLocal()
        try:
            # Получаем все активные подписки
            subscriptions = db.query(models.Subscription).filter(
                models.Subscription.is_active == True
            ).all()
            
            current_time = datetime.now(UTC)
            for subscription in subscriptions:
                if subscription.end_date < current_time:
                    # Деактивируем подписку
                    crud.deactivate_subscription(db, subscription.id)
                    # Деактивируем связанные VPN конфигурации
                    vpn_configs = crud.get_user_vpn_configs(db, subscription.user_id)
                    for config in vpn_configs:
                        if config.is_active:
                            crud.deactivate_vpn_config(db, config.id)
        finally:
            db.close()
        await asyncio.sleep(3600)  # Проверка каждый час

# Эндпоинты для работы с пользователями
@app.post("/users/")
async def create_user(tg_id: int, username: str, firstname: str, db: Session = Depends(get_db)):
    db_user = crud.get_user_by_tg_id(db, tg_id)
    if db_user:
        raise HTTPException(status_code=400, detail="Пользователь уже существует")
    return crud.create_user(db, tg_id=tg_id, username=username, firstname=firstname)

@app.get("/users/{user_id}")
async def get_user(user_id: int, db: Session = Depends(get_db)):
    db_user = crud.get_user(db, user_id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return db_user

# Эндпоинты для работы с подписками
@app.post("/subscriptions/")
async def create_subscription(user_id: int, days: int, db: Session = Depends(get_db)):
    db_user = crud.get_user(db, user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    end_date = datetime.now(UTC) + timedelta(days=days)
    return crud.create_subscription(db, user_id=user_id, end_date=end_date)

@app.delete("/subscriptions/user/{user_id}")
async def delete_subscription_by_user_id(user_id: int, db: Session = Depends(get_db)):
    subscription = crud.get_active_subscription(db, user_id)
    if not subscription:
        raise HTTPException(status_code=404, detail="Активная подписка не найдена")
    deactivated = crud.deactivate_subscription(db, subscription.id)
    if not deactivated:
        raise HTTPException(status_code=500, detail="Не удалось деактивировать подписку")
    return {"message": "Подписка деактивирована"}

@app.put("/subscriptions/extend")
async def extend_subscription(user_id: int, days: int, db: Session = Depends(get_db)):
    subscription = crud.get_active_subscription(db, user_id)
    if not subscription:
        raise HTTPException(status_code=404, detail="Активная подписка не найдена")
    
    subscription.end_date += timedelta(days=days)
    db.commit()
    db.refresh(subscription)
    return subscription

# Эндпоинты для работы с VPN
@app.post("/vpn/")
async def create_vpn(
    user_id: int,
    db: Session = Depends(get_db)
):
    # Проверяем наличие активной подписки
    active_subscription = crud.get_active_subscription(db, user_id)
    if not active_subscription:
        raise HTTPException(status_code=400, detail="Нет активной подписки")
    
    # Генерируем уникальное имя для конфига
    config_name = f"user_{user_id}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
    
    try:
        # Создаем VPN конфигурацию на сервере
        config_content = ovpn.create_openvpn_user(
            client_name=config_name,
            hostname=SSH_HOST,
            username=SSH_USERNAME,
            password=SSH_PASSWORD,
            port=SSH_PORT
        )
        
        # Сохраняем конфигурацию в базе данных
        return crud.create_vpn_config(
            db,
            user_id=user_id,
            config_name=config_name,
            config_content=config_content
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/vpn/{user_id}")
async def get_vpn(user_id: int, db: Session = Depends(get_db)):
    vpn_config = crud.get_active_vpn_config(db, user_id)
    if not vpn_config:
        raise HTTPException(status_code=404, detail="VPN конфигурация не найдена")
    return vpn_config

@app.delete("/vpn/{user_id}")
async def delete_vpn(
    user_id: int,
    db: Session = Depends(get_db)
):
    vpn_config = crud.get_active_vpn_config(db, user_id)
    if not vpn_config:
        raise HTTPException(status_code=404, detail="VPN конфигурация не найдена")
    
    try:
        # Удаляем VPN конфигурацию на сервере
        success = ovpn.revoke_openvpn_user(
            client_name=vpn_config.config_name,
            hostname=SSH_HOST,
            username=SSH_USERNAME,
            password=SSH_PASSWORD,
            port=SSH_PORT
        )
        
        if success:
            # Деактивируем конфигурацию в базе данных
            crud.deactivate_vpn_config(db, vpn_config.id)
            return {"message": "VPN конфигурация удалена"}
        else:
            raise HTTPException(status_code=500, detail="Ошибка при удалении VPN конфигурации на сервере")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(cleanup_inactive())

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
