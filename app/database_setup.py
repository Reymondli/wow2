from sqlalchemy import Column, Date, Integer, String, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, backref
from sqlalchemy import create_engine
import hashlib

Base = declarative_base()


def salted(keyword, username):
    #salt = "1Ha7"
    salt = "1Ha7" + str(len(username)) + username
    hash = hashlib.md5((salt + keyword).encode('utf-8')).hexdigest()
    return hash

########################################################################
class User(Base):
    """"""
    __tablename__ = "user"

    id = Column(Integer, primary_key=True)
    username = Column(String(80), nullable=False)
    password = Column(String(80), nullable=False)
    # ----------------------------------------------------------------------
    def __init__(self, username, password):
        """"""
        self.username = username
        self.password = salted(password, username)


class Photo(Base):
    __tablename__ = 'photo'

    id = Column(Integer, primary_key=True)
    name = Column(String(250))
    origin = Column(String(250))
    thumbnail = Column(String(250))
    trans_one = Column(String(250))
    trans_two = Column(String(250))
    trans_three = Column(String(250))
    user_id = Column(Integer, ForeignKey('user.id'))
    user = relationship(User)

    @property
    def serialize(self):
        """Return object data in easily serializeable format"""
        return {
            'name': self.name,
            'id': self.id,
        }


engine = create_engine('mysql://ece1779:secret@172.31.40.82:3306')
engine.execute("CREATE DATABASE IF NOT EXISTS cca1") #create db
engine.execute("USE cca1")
# create tables
Base.metadata.create_all(engine)
