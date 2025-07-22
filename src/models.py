from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime, UTC
from .database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    tgId = Column(Integer, unique=True, index=True)
    username = Column(String, unique=True, index=True)
    firstname = Column(String)
    
    # Связи с другими таблицами
    subscriptions = relationship("Subscription", back_populates="user")
    vpn_configs = relationship("VPNConfig", back_populates="user")

class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    start_date = Column(DateTime, default=lambda: datetime.now(UTC))
    end_date = Column(DateTime)
    is_active = Column(Boolean, default=True)
    
    # Связь с пользователем
    user = relationship("User", back_populates="subscriptions")

class VPNConfig(Base):
    __tablename__ = "vpn_configs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    config_name = Column(String)
    config_content = Column(String)  # Содержимое .ovpn файла
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    is_active = Column(Boolean, default=True)
    
    # Связь с пользователем
    user = relationship("User", back_populates="vpn_configs")