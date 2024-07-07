from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Float, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    
    id = Column(String, primary_key=True)
    username = Column(String, nullable=True)
    balance = Column(Float, default=0.0)
    referrer_count = Column(Integer, default=0)
    referral_link = Column(String, nullable=True)
    referrer_id = Column(Integer, ForeignKey('users.id'))
    chat_link = Column(String, nullable=True)
    referrer = relationship('User', remote_side=[id], backref='referrals')

class Transaction(Base):
    __tablename__ = 'transactions'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    amount = Column(Float)
    description = Column(String)
    user = relationship('User', backref='transactions')

engine = create_engine('sqlite:///referral_system.db')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
session = Session()
