from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, PreCheckoutQuery
from fastapi import FastAPI, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, UTC
import asyncio
from typing import Optional
import uvicorn
import os
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from src import models, crud, ovpn
from src.database import SessionLocal, engine

# Загружаем переменные окружения
load_dotenv()

# Получаем параметры SSH из переменных окружения
SSH_HOST = os.getenv("SSH_HOST")
SSH_USERNAME = os.getenv("SSH_USERNAME")
SSH_PASSWORD = os.getenv("SSH_PASSWORD")
SSH_PORT = int(os.getenv("SSH_PORT", "22"))
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Создаем таблицы в базе данных
models.Base.metadata.create_all(bind=engine)


app = FastAPI(title="VPN API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://t5kxd472-5173.euw.devtunnels.ms",
        "https://t5kxd472.euw.devtunnels.ms",
        "https://t5kxd472.euw.devtunnels.ms:8000",
        "http://localhost:5173",
        "http://localhost:3000",
        "*"  # Временно разрешаем все origins для отладки
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# Обработчик pre-checkout query
@dp.pre_checkout_query()
async def pre_checkout_query(query: PreCheckoutQuery):
    await query.answer(ok=True)

# Обработчик успешной оплаты
@dp.message(F.successful_payment)
async def successful_payment(message: Message):
    await bot.refund_star_payment(message.from_user.id, message.successful_payment.telegram_payment_charge_id)

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
                # Убеждаемся, что end_date имеет информацию о часовом поясе
                end_date = subscription.end_date
                if end_date.tzinfo is None:
                    # Если end_date не имеет информации о часовом поясе, считаем его UTC
                    end_date = end_date.replace(tzinfo=UTC)
                
                if end_date < current_time:
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
@app.post("/api/users")
async def create_user(
    user_id: int = Query(..., alias="user_id"),
    username: str = Query(...),
    firstname: str = Query(...),
    db: Session = Depends(get_db)
):
    db_user = crud.get_user_by_tg_id(db, user_id)
    if db_user:
        return {"message": "Пользователь уже существует", "user": db_user}
    user = crud.create_user(db, tg_id=user_id, username=username, firstname=firstname)
    subscription = crud.create_subscription(db, user_id=user.id, end_date=datetime.now(UTC) + timedelta(days=7))
    return {"message": "success", "user": user, "subscription": subscription}

@app.get("/api/users/{user_id}")
async def get_user(user_id: int, db: Session = Depends(get_db)):
    db_user = crud.get_user(db, user_id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return db_user

# Эндпоинты для работы с подписками
@app.post("/api/subscriptions")
async def create_subscription(
    user_id: int = Query(...),
    days: int = Query(...),
    db: Session = Depends(get_db)
):
    db_user = crud.get_user(db, user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    # Убеждаемся, что end_date создается с UTC
    end_date = datetime.now(UTC) + timedelta(days=days)
    return crud.create_subscription(db, user_id=user_id, end_date=end_date)

@app.delete("/api/subscriptions/user/{user_id}")
async def delete_subscription_by_user_id(user_id: int, db: Session = Depends(get_db)):
    subscription = crud.get_active_subscription(db, user_id)
    if not subscription:
        raise HTTPException(status_code=404, detail="Активная подписка не найдена")
    deactivated = crud.deactivate_subscription(db, subscription.id)
    if not deactivated:
        raise HTTPException(status_code=500, detail="Не удалось деактивировать подписку")
    return {"message": "Подписка деактивирована"}

@app.put("/api/subscriptions/extend")
async def extend_subscription(user_id: int, days: int, db: Session = Depends(get_db)):
    subscription = crud.get_active_subscription(db, user_id)
    if not subscription:
        raise HTTPException(status_code=404, detail="Активная подписка не найдена")
    
    # Убеждаемся, что end_date имеет информацию о часовом поясе
    if subscription.end_date.tzinfo is None:
        subscription.end_date = subscription.end_date.replace(tzinfo=UTC)
    
    subscription.end_date += timedelta(days=days)
    db.commit()
    db.refresh(subscription)
    return subscription

# Эндпоинты для работы с VPN
@app.post("/api/vpn")
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

@app.get("/api/vpn/{user_id}")
async def get_vpn(user_id: int, db: Session = Depends(get_db)):
    vpn_config = crud.get_active_vpn_config(db, user_id)
    if not vpn_config:
        raise HTTPException(status_code=404, detail="VPN конфигурация не найдена")
    return vpn_config

@app.delete("/api/vpn/{user_id}")
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
    

from fastapi.responses import JSONResponse

@app.get("/api/create_invoice")
async def create_invoice(title: str, description: str, payload: str, price: int):
    try:
        # Проверяем, что все параметры переданы
        if not all([title, description, payload, price]):
            return JSONResponse(status_code=400, content={"detail": "Не все параметры переданы"})

        # Временно используем валюту RUB, так как XTR не поддерживается Telegram
        invoice = await bot.create_invoice_link(
            title=title,
            description=description,
            payload=payload,
            provider_token=BOT_TOKEN,
            currency="XTR",
            prices=[
                {
                    "label": title,
                    "amount": price  
                }
            ],
        )
        return {"invoice": invoice}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": f"Ошибка при создании инвойса: {str(e)}"})

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(cleanup_inactive())
    asyncio.create_task(start_bot())

async def start_bot():
    print("🚀 Бот запущен")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    # Запускаем сервер uvicorn через asyncio
    uvicorn.run(app, host="0.0.0.0", port=8000)
    # Бот стартует как фоновая задача при запуске FastAPI (см. startup_event)
