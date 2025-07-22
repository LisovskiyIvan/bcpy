from sqlalchemy.orm import Session
from datetime import datetime
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

# Subscription CRUD operations
def create_subscription(db: Session, user_id: int, end_date: datetime):
    db_subscription = models.Subscription(
        user_id=user_id,
        end_date=end_date,
        is_active=True
    )
    db.add(db_subscription)
    db.commit()
    db.refresh(db_subscription)
    return db_subscription

def get_user_subscriptions(db: Session, user_id: int):
    return db.query(models.Subscription).filter(models.Subscription.user_id == user_id).all()

def get_active_subscription(db: Session, user_id: int):
    return db.query(models.Subscription).filter(
        models.Subscription.user_id == user_id,
        models.Subscription.is_active == True
    ).first()

def deactivate_subscription(db: Session, subscription_id: int):
    subscription = db.query(models.Subscription).filter(models.Subscription.id == subscription_id).first()
    if subscription:
        subscription.is_active = False
        db.commit()
        db.refresh(subscription)
    return subscription

# VPNConfig CRUD operations
def create_vpn_config(db: Session, user_id: int, config_name: str, config_content: str):
    db_config = models.VPNConfig(
        user_id=user_id,
        config_name=config_name,
        config_content=config_content,
        is_active=True
    )
    db.add(db_config)
    db.commit()
    db.refresh(db_config)
    return db_config

def get_user_vpn_configs(db: Session, user_id: int):
    return db.query(models.VPNConfig).filter(models.VPNConfig.user_id == user_id).all()

def get_active_vpn_config(db: Session, user_id: int):
    return db.query(models.VPNConfig).filter(
        models.VPNConfig.user_id == user_id,
        models.VPNConfig.is_active == True
    ).first()

def deactivate_vpn_config(db: Session, config_id: int):
    config = db.query(models.VPNConfig).filter(models.VPNConfig.id == config_id).first()
    if config:
        config.is_active = False
        db.commit()
        db.refresh(config)
    return config 