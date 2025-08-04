from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Text, Numeric
from sqlalchemy.orm import relationship
from datetime import datetime, UTC
from .database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    tgId = Column(Integer, unique=True, index=True)
    username = Column(String, unique=True, index=True)
    firstname = Column(String)
    free_trial_used = Column(Boolean, default=False)  # Использовал ли пользователь бесплатный пробный период
    free_trial_expires_at = Column(DateTime, nullable=True)  # Дата истечения бесплатного пробного периода
    
    # Связи с другими таблицами
    configs = relationship("UserConfig", back_populates="user")
    purchases = relationship("Purchase", back_populates="user")

class Server(Base):
    __tablename__ = "servers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    host = Column(String, nullable=False)
    port = Column(Integer, nullable=False)
    country = Column(String)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    
    # Связи
    configs = relationship("UserConfig", back_populates="server")

class Protocol(Base):
    __tablename__ = "protocols"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)  # openvpn, wireguard, etc.
    description = Column(String)
    is_active = Column(Boolean, default=True)
    
    # Связи
    configs = relationship("UserConfig", back_populates="protocol")

class UserConfig(Base):
    __tablename__ = "user_configs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    server_id = Column(Integer, ForeignKey("servers.id"))
    protocol_id = Column(Integer, ForeignKey("protocols.id"))
    
    config_name = Column(String)
    config_content = Column(Text)  # Содержимое конфигурационного файла
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    expires_at = Column(DateTime, nullable=True)  # Дата истечения конфига
    is_active = Column(Boolean, default=True)
    
    # Связи
    user = relationship("User", back_populates="configs")
    server = relationship("Server", back_populates="configs")
    protocol = relationship("Protocol", back_populates="configs")
    purchases = relationship("Purchase", back_populates="config")

class Purchase(Base):
    __tablename__ = "purchases"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    config_id = Column(Integer, ForeignKey("user_configs.id"))
    
    amount = Column(Numeric(10, 2), nullable=False)  # Сумма покупки
    duration_days = Column(Integer, nullable=False)  # Продолжительность в днях
    purchase_type = Column(String)  # "new", "renewal"
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    
    # Связи
    user = relationship("User", back_populates="purchases")
    config = relationship("UserConfig", back_populates="purchases")

class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id = Column(Integer, primary_key=True, index=True)
    config_id = Column(Integer, ForeignKey("user_configs.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    notification_type = Column(String)  # "expiration_warning"
    sent_at = Column(DateTime, default=lambda: datetime.now(UTC))
    expires_at = Column(DateTime)  # Дата истечения конфига на момент отправки уведомления
    
    # Связи
    config = relationship("UserConfig")
    user = relationship("User")