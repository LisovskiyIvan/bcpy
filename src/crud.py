from sqlalchemy.orm import Session
from datetime import UTC, datetime, timedelta
from . import models

# User CRUD operations
def create_user(db: Session, tg_id: int, username: str, firstname: str):
    db_user = models.User(tgId=tg_id, username=username, firstname=firstname)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def get_user_by_tg_id(db: Session, tg_id: int):
    return db.query(models.User).filter(models.User.tgId == tg_id).first()

def get_user_by_username(db: Session, username: str):
    return db.query(models.User).filter(models.User.username == username).first()

def get_user(db: Session, user_id: int):
    return db.query(models.User).filter(models.User.id == user_id).first()

def get_users(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.User).offset(skip).limit(limit).all()

def activate_free_trial(db: Session, user_id: int, trial_days: int = 7):
    """Активирует бесплатный пробный период для пользователя"""
    user = get_user(db, user_id)
    if user and not user.free_trial_used:
        user.free_trial_used = True
        user.free_trial_expires_at = datetime.now(UTC) + timedelta(days=trial_days)
        db.commit()
        db.refresh(user)
        return user
    return None

def get_user_free_trial_status(db: Session, user_id: int):
    """Получает статус бесплатного пробного периода пользователя"""
    user = get_user_by_tg_id(db, user_id)
    if not user:
        return None
    
    if not user.free_trial_used:
        return {"available": True, "used": False, "expires_at": None}
    
    if user.free_trial_expires_at and user.free_trial_expires_at > datetime.now(UTC):
        return {
            "available": False, 
            "used": True, 
            "active": True,
            "expires_at": user.free_trial_expires_at
        }
    else:
        return {
            "available": False, 
            "used": True, 
            "active": False,
            "expires_at": user.free_trial_expires_at
        }

# Server CRUD operations
def create_server(db: Session, name: str, host: str, port: int, country: str = None):
    # Проверяем, существует ли сервер с таким именем
    existing_server = get_server_by_name(db, name)
    if existing_server:
        raise ValueError(f"Сервер с именем '{name}' уже существует")
    
    db_server = models.Server(name=name, host=host, port=port, country=country)
    db.add(db_server)
    db.commit()
    db.refresh(db_server)
    return db_server

def get_server(db: Session, server_id: int):
    return db.query(models.Server).filter(models.Server.id == server_id).first()

def get_active_servers(db: Session):
    return db.query(models.Server).filter(models.Server.is_active == True).all()

def get_server_by_name(db: Session, name: str):
    return db.query(models.Server).filter(models.Server.name == name).first()

# Protocol CRUD operations
def create_protocol(db: Session, name: str, description: str = None):
    # Проверяем, существует ли протокол с таким именем
    existing_protocol = get_protocol_by_name(db, name)
    if existing_protocol:
        raise ValueError(f"Протокол с именем '{name}' уже существует")
    
    db_protocol = models.Protocol(name=name, description=description)
    db.add(db_protocol)
    db.commit()
    db.refresh(db_protocol)
    return db_protocol

def get_protocol(db: Session, protocol_id: int):
    return db.query(models.Protocol).filter(models.Protocol.id == protocol_id).first()

def get_active_protocols(db: Session):
    return db.query(models.Protocol).filter(models.Protocol.is_active == True).all()

def get_protocol_by_name(db: Session, name: str):
    return db.query(models.Protocol).filter(models.Protocol.name == name).first()

# UserConfig CRUD operations
def create_user_config(db: Session, user_id: int, server_id: int, protocol_id: int, 
                      config_name: str, config_content: str, duration_days: int = 30):
    expires_at = datetime.now(UTC) + timedelta(days=duration_days)
    db_config = models.UserConfig(
        user_id=user_id,
        server_id=server_id,
        protocol_id=protocol_id,
        config_name=config_name,
        config_content=config_content,
        expires_at=expires_at,
        is_active=True
    )
    db.add(db_config)
    db.commit()
    db.refresh(db_config)
    return db_config

def get_user_config(db: Session, config_id: int):
    return db.query(models.UserConfig).filter(models.UserConfig.id == config_id).first()

def get_user_active_configs(db: Session, user_id: int):
    """Получает все активные конфиги пользователя"""
    configs = db.query(models.UserConfig).filter(
        models.UserConfig.user_id == user_id,
        models.UserConfig.is_active == True,
        (models.UserConfig.expires_at == None) | (models.UserConfig.expires_at > datetime.now(UTC))
    ).all()
    
    # Преобразуем объекты конфигурации в словари с нужными полями
    result = []
    for config in configs:
        config_dict = {
            "id": config.id,
            "config_name": config.config_name,
            "created_at": config.created_at,
            "expires_at": config.expires_at,
            "is_active": config.is_active,
            "protocol": config.protocol.name,  # Имя протокола вместо ID
            "server_country": config.server.country,  # Страна сервера вместо ID
            "server_name": config.server.name,  # Добавим также имя сервера для полноты
            "config_content": config.config_content
        }
        result.append(config_dict)
    
    return result

def get_user_all_configs(db: Session, user_id: int):
    """Получает все конфиги пользователя"""
    configs = db.query(models.UserConfig).filter(models.UserConfig.user_id == user_id).all()
    
    # Преобразуем объекты конфигурации в словари с нужными полями
    result = []
    for config in configs:
        config_dict = {
            "id": config.id,
            "config_name": config.config_name,
            "created_at": config.created_at,
            "expires_at": config.expires_at,
            "is_active": config.is_active,
            "protocol": config.protocol.name,  # Имя протокола вместо ID
            "server_country": config.server.country,  # Страна сервера вместо ID
            "server_name": config.server.name  # Добавим также имя сервера для полноты
        }
        result.append(config_dict)
    
    return result

def deactivate_user_config(db: Session, config_id: int):
    config = get_user_config(db, config_id)
    if config:
        config.is_active = False
        db.commit()
        db.refresh(config)
    return config

def extend_user_config(db: Session, config_id: int, additional_days: int):
    """Продлевает конфиг на указанное количество дней"""
    config = get_user_config(db, config_id)
    if config:
        if config.expires_at:
            config.expires_at += timedelta(days=additional_days)
        else:
            config.expires_at = datetime.now(UTC) + timedelta(days=additional_days)
        db.commit()
        db.refresh(config)
    return config

# Purchase CRUD operations
def create_purchase(db: Session, user_id: int, config_id: int, amount: float, 
                   duration_days: int, purchase_type: str = "new"):
    db_purchase = models.Purchase(
        user_id=user_id,
        config_id=config_id,
        amount=amount,
        duration_days=duration_days,
        purchase_type=purchase_type
    )
    db.add(db_purchase)
    db.commit()
    db.refresh(db_purchase)
    return db_purchase

def get_user_purchases(db: Session, user_id: int):
    return db.query(models.Purchase).filter(models.Purchase.user_id == user_id).all()

def get_config_purchases(db: Session, config_id: int):
    return db.query(models.Purchase).filter(models.Purchase.config_id == config_id).all()

def get_purchase(db: Session, purchase_id: int):
    return db.query(models.Purchase).filter(models.Purchase.id == purchase_id).first()

# Комбинированные операции
def buy_new_config(db: Session, user_id: int, server_id: int, protocol_id: int, 
                  config_name: str, config_content: str, amount: float, duration_days: int):
    """Покупка нового конфига"""
    # Создаем конфиг
    config = create_user_config(db, user_id, server_id, protocol_id, 
                               config_name, config_content, duration_days)
    
    # Создаем запись о покупке
    purchase = create_purchase(db, user_id, config.id, amount, duration_days, "new")
    
    return config, purchase

def renew_config(db: Session, config_id: int, user_id: int, amount: float, duration_days: int):
    """Продление существующего конфига"""
    # Продлеваем конфиг
    config = extend_user_config(db, config_id, duration_days)
    
    # Создаем запись о покупке
    purchase = create_purchase(db, user_id, config_id, amount, duration_days, "renewal")
    
    return config, purchase 

# Notification CRUD operations
def create_notification_log(db: Session, config_id: int, user_id: int, notification_type: str, expires_at: datetime):
    """Создает запись об отправленном уведомлении"""
    notification = models.NotificationLog(
        config_id=config_id,
        user_id=user_id,
        notification_type=notification_type,
        expires_at=expires_at
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification

def get_notification_log(db: Session, config_id: int, notification_type: str):
    """Получает запись об уведомлении для конкретного конфига и типа"""
    return db.query(models.NotificationLog).filter(
        models.NotificationLog.config_id == config_id,
        models.NotificationLog.notification_type == notification_type
    ).first()

def get_configs_expiring_soon(db: Session, hours_before: int = 24):
    """Получает конфиги, которые истекают через указанное количество часов"""
    from datetime import timedelta
    
    current_time = datetime.now(UTC)
    target_time = current_time + timedelta(hours=hours_before)
    
    # Получаем конфиги, которые истекают в указанном временном окне
    configs = db.query(models.UserConfig).filter(
        models.UserConfig.is_active == True,
        models.UserConfig.expires_at >= current_time,
        models.UserConfig.expires_at <= target_time
    ).all()
    
    return configs

def has_expiration_notification_sent(db: Session, config_id: int):
    """Проверяет, было ли уже отправлено уведомление об истечении для данного конфига"""
    notification = get_notification_log(db, config_id, "expiration_warning")
    return notification is not None 