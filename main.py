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
async def cleanup_expired_configs():
    while True:
        db = SessionLocal()
        try:
            # Получаем все активные конфиги с истекшим сроком
            current_time = datetime.now(UTC)
            expired_configs = db.query(models.UserConfig).filter(
                models.UserConfig.is_active == True,
                models.UserConfig.expires_at < current_time
            ).all()
            
            for config in expired_configs:
                # Деактивируем конфиг
                crud.deactivate_user_config(db, config.id)
                print(f"Конфиг {config.id} деактивирован (истек срок)")
        finally:
            db.close()
        await asyncio.sleep(3600)  # Проверка каждый час

# Эндпоинты для работы с пользователями
@app.post("/api/users")
async def create_user(
    user_id: int = Query(..., alias="user_id"),
    username: str = Query(...),
    firstname: str = Query(...),
    activate_trial: bool = Query(True, alias="activate_trial"),
    trial_days: int = Query(7, alias="trial_days"),
    db: Session = Depends(get_db)
):
    db_user = crud.get_user_by_tg_id(db, user_id)
    if db_user:
        return {"message": "Пользователь уже существует", "user": db_user}
    
    user = crud.create_user(db, tg_id=user_id, username=username, firstname=firstname)
    
    # Активируем бесплатный пробный период, если запрошено
    if activate_trial:
        trial_user = crud.activate_free_trial(db, user.id, trial_days)
        if trial_user:
            return {
                "message": "success", 
                "user": user, 
                "free_trial": {
                    "activated": True,
                    "expires_at": trial_user.free_trial_expires_at,
                    "days": trial_days
                }
            }
    
    return {"message": "success", "user": user}

@app.get("/api/users/{user_id}")
async def get_user(user_id: int, db: Session = Depends(get_db)):
    # Сначала пробуем найти по Telegram ID
    db_user = crud.get_user_by_tg_id(db, user_id)
    if db_user is None:
        # Если не найден по Telegram ID, пробуем по внутреннему ID
        db_user = crud.get_user(db, user_id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return db_user

@app.get("/api/users/{user_id}/free-trial")
async def get_user_free_trial_status(user_id: int, db: Session = Depends(get_db)):
    """Получить статус бесплатного пробного периода пользователя"""
    trial_status = crud.get_user_free_trial_status(db, user_id)
    if trial_status is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return trial_status

@app.post("/api/users/{user_id}/activate-trial")
async def activate_user_free_trial(
    user_id: int,
    trial_days: int = Query(7, alias="trial_days"),
    db: Session = Depends(get_db)
):
    """Активировать бесплатный пробный период для пользователя"""
    # Проверяем существование пользователя
    user = crud.get_user_by_tg_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    trial_user = crud.activate_free_trial(db, user.id, trial_days)
    if not trial_user:
        raise HTTPException(status_code=400, detail="Бесплатный пробный период уже использован или недоступен")
    
    return {
        "message": "Бесплатный пробный период активирован",
        "user": trial_user,
        "free_trial": {
            "activated": True,
            "expires_at": trial_user.free_trial_expires_at,
            "days": trial_days
        }
    }

# Эндпоинты для работы с серверами
@app.get("/api/servers")
async def get_servers(db: Session = Depends(get_db)):
    """Получить все активные серверы"""
    servers = crud.get_active_servers(db)
    return {"servers": servers}

@app.post("/api/servers")
async def create_server(
    name: str = Query(...),
    host: str = Query(...),
    port: int = Query(...),
    country: str = Query(None),
    db: Session = Depends(get_db)
):
    """Создать новый сервер"""
    try:
        server = crud.create_server(db, name=name, host=host, port=port, country=country)
        return server
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# Эндпоинты для работы с протоколами
@app.get("/api/protocols")
async def get_protocols(db: Session = Depends(get_db)):
    """Получить все активные протоколы"""
    protocols = crud.get_active_protocols(db)
    return {"protocols": protocols}

@app.post("/api/protocols")
async def create_protocol(
    name: str = Query(...),
    description: str = Query(None),
    db: Session = Depends(get_db)
):
    """Создать новый протокол"""
    try:
        protocol = crud.create_protocol(db, name=name, description=description)
        return protocol
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# Эндпоинты для работы с конфигурациями пользователей
@app.post("/api/configs")
async def create_user_config(
    user_id: int = Query(..., alias="user_id"),
    server_id: int = Query(..., alias="server_id"),
    protocol_id: int = Query(..., alias="protocol_id"),
    config_name: str = Query(...),
    duration_days: int = Query(30),
    db: Session = Depends(get_db)
):
    """Создать новую конфигурацию для пользователя"""
    # Проверяем существование пользователя
    user = crud.get_user_by_tg_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    # Проверяем существование сервера
    server = crud.get_server(db, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Сервер не найден")
    
    # Проверяем существование протокола
    protocol = crud.get_protocol(db, protocol_id)
    if not protocol:
        raise HTTPException(status_code=404, detail="Протокол не найден")
    
    try:
        # Создаем VPN конфигурацию на сервере через ovpn.py
        config_content = ovpn.create_openvpn_user(
            client_name=config_name,
            hostname=SSH_HOST,
            username=SSH_USERNAME,
            password=SSH_PASSWORD,
            port=SSH_PORT
        )
        
        # Сохраняем конфигурацию в базе данных
        config = crud.create_user_config(
            db, 
            user_id=user.id, 
            server_id=server_id, 
            protocol_id=protocol_id,
            config_name=config_name,
            config_content=config_content,
            duration_days=duration_days
        )
        
        return config
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при создании VPN конфигурации: {str(e)}")

@app.get("/api/configs/user/{user_id}")
async def get_user_configs(user_id: int, db: Session = Depends(get_db)):
    """Получить все конфигурации пользователя"""
    user = crud.get_user_by_tg_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    configs = crud.get_user_all_configs(db, user.id)
    return {"configs": configs}

@app.get("/api/configs/user/{user_id}/active")
async def get_user_active_configs(user_id: int, db: Session = Depends(get_db)):
    """Получить активные конфигурации пользователя"""
    user = crud.get_user_by_tg_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    configs = crud.get_user_active_configs(db, user.id)
    return {"configs": configs}

@app.delete("/api/configs/{config_id}")
async def deactivate_config(config_id: int, db: Session = Depends(get_db)):
    """Деактивировать конфигурацию и удалить VPN пользователя на сервере"""
    config = crud.get_user_config(db, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Конфигурация не найдена")
    
    try:
        # Удаляем VPN конфигурацию на сервере
        success = ovpn.revoke_openvpn_user(
            client_name=config.config_name,
            hostname=SSH_HOST,
            username=SSH_USERNAME,
            password=SSH_PASSWORD,
            port=SSH_PORT
        )
        
        if success:
            # Деактивируем конфигурацию в базе данных
            crud.deactivate_user_config(db, config_id)
            return {"message": "Конфигурация деактивирована и удалена с сервера"}
        else:
            raise HTTPException(status_code=500, detail="Ошибка при удалении VPN конфигурации на сервере")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при деактивации конфигурации: {str(e)}")

@app.put("/api/configs/{config_id}/extend")
async def extend_config(
    config_id: int,
    additional_days: int = Query(...),
    db: Session = Depends(get_db)
):
    """Продлить конфигурацию"""
    config = crud.extend_user_config(db, config_id, additional_days)
    if not config:
        raise HTTPException(status_code=404, detail="Конфигурация не найдена")
    return config

@app.post("/api/configs/{config_id}/send-to-telegram")
async def send_config_to_telegram(
    config_id: int,
    chat_id: int = Query(...),
    db: Session = Depends(get_db)
):
    """Отправить файл конфигурации в Telegram чат"""
    config = crud.get_user_config(db, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Конфигурация не найдена")
    
    if not config.is_active:
        raise HTTPException(status_code=400, detail="Конфигурация неактивна")
    
    try:
        # Создаем содержимое файла
        config_content = config.config_content.encode('utf-8')
        
        # Отправляем файл в Telegram
        from aiogram.types import BufferedInputFile
        await bot.send_document(
            chat_id=chat_id,
            document=BufferedInputFile(
                file=config_content,
                filename=f"vpn_config_{config.config_name}.ovpn"
            ),
            caption=f"🔐 Ваш VPN конфигурационный файл\n"
                   f"📅 Действует до: {config.expires_at.strftime('%Y-%m-%d') if config.expires_at else 'Бессрочно'}\n"
                   f"🖥️ Сервер: {config.server.name}\n"
                   f"📡 Протокол: {config.protocol.name}"
        )
        
        return {"message": "Файл конфигурации отправлен в Telegram"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при отправке файла: {str(e)}")

# Эндпоинты для работы с покупками
@app.post("/api/purchases")
async def create_purchase(
    user_id: int = Query(..., alias="user_id"),
    config_id: int = Query(..., alias="config_id"),
    amount: float = Query(...),
    duration_days: int = Query(...),
    purchase_type: str = Query("new"),
    db: Session = Depends(get_db)
):
    """Создать запись о покупке"""
    # Проверяем существование пользователя
    user = crud.get_user_by_tg_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    # Проверяем существование конфигурации
    config = crud.get_user_config(db, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Конфигурация не найдена")
    
    purchase = crud.create_purchase(
        db, 
        user_id=user.id, 
        config_id=config_id,
        amount=amount,
        duration_days=duration_days,
        purchase_type=purchase_type
    )
    return purchase

@app.get("/api/purchases/user/{user_id}")
async def get_user_purchases(user_id: int, db: Session = Depends(get_db)):
    """Получить все покупки пользователя"""
    user = crud.get_user_by_tg_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    purchases = crud.get_user_purchases(db, user.id)
    return {"purchases": purchases}

# Комбинированные эндпоинты для покупки конфигураций
@app.post("/api/buy-config")
async def buy_new_config(
    user_id: int = Query(..., alias="user_id"),
    server_id: int = Query(..., alias="server_id"),
    protocol_id: int = Query(..., alias="protocol_id"),
    config_name: str = Query(...),
    config_content: str = Query(...),
    amount: float = Query(0.0),  # По умолчанию 0 для бесплатного пробного периода
    duration_days: int = Query(30),
    use_free_trial: bool = Query(False, alias="use_free_trial"),
    db: Session = Depends(get_db)
):
    """Покупка новой конфигурации с поддержкой бесплатного пробного периода"""
    # Проверяем существование пользователя
    user = crud.get_user_by_tg_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    # Проверяем статус бесплатного пробного периода
    trial_status = crud.get_user_free_trial_status(db, user_id)
    if not trial_status:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    # Если запрошен бесплатный пробный период
    if use_free_trial:
        if not trial_status["available"]:
            raise HTTPException(status_code=400, detail="Бесплатный пробный период недоступен")
        
        # Активируем бесплатный пробный период
        trial_user = crud.activate_free_trial(db, user.id, 7)  # 7 дней пробного периода
        if not trial_user:
            raise HTTPException(status_code=400, detail="Не удалось активировать бесплатный пробный период")
        
        # Создаем конфигурацию с нулевой стоимостью
        try:
            config, purchase = crud.buy_new_config(
                db, 
                user_id=user.id,
                server_id=server_id,
                protocol_id=protocol_id,
                config_name=config_name,
                config_content=config_content,
                amount=0.0,  # Бесплатно
                duration_days=7  # 7 дней пробного периода
            )
            return {
                "config": config, 
                "purchase": purchase,
                "free_trial": {
                    "used": True,
                    "expires_at": trial_user.free_trial_expires_at
                }
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    else:
        # Обычная покупка
        if amount <= 0:
            raise HTTPException(status_code=400, detail="Сумма покупки должна быть больше 0")
        
        try:
            config, purchase = crud.buy_new_config(
                db, 
                user_id=user.id,
                server_id=server_id,
                protocol_id=protocol_id,
                config_name=config_name,
                config_content=config_content,
                amount=amount,
                duration_days=duration_days
            )
            return {"config": config, "purchase": purchase}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/renew-config")
async def renew_config(
    config_id: int = Query(..., alias="config_id"),
    user_id: int = Query(..., alias="user_id"),
    amount: float = Query(...),
    duration_days: int = Query(...),
    db: Session = Depends(get_db)
):
    """Продление существующей конфигурации"""
    # Проверяем существование пользователя
    user = crud.get_user_by_tg_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    try:
        config, purchase = crud.renew_config(
            db,
            config_id=config_id,
            user_id=user.id,
            amount=amount,
            duration_days=duration_days
        )
        return {"config": config, "purchase": purchase}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



# Эндпоинт для создания инвойса (оставляем без изменений)
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
    asyncio.create_task(cleanup_expired_configs())
    asyncio.create_task(start_bot())

async def start_bot():
    print("🚀 Бот запущен")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    # Запускаем сервер uvicorn через asyncio
    uvicorn.run(app, host="0.0.0.0", port=8000)
    # Бот стартует как фоновая задача при запуске FastAPI (см. startup_event)
