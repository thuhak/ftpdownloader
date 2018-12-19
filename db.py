from sqlalchemy import create_engine, Column, String, Integer, DateTime
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from contextlib import contextmanager
from conf import config


dbconfig = config['database']
engine_path = 'mysql+pymysql://{user}:{passwd}@{host}:{port}/{db}'.format(**dbconfig)


Base = declarative_base()
engine = create_engine(engine_path, encoding='utf-8', echo=False,
                       pool_size=5, max_overflow=10, pool_recycle=7200)
DBSession = sessionmaker(bind=engine)


@contextmanager
def session_scope():
    session = DBSession()
    try:
        yield session
        session.commit()
    except:
        session.rollback()
        raise
    finally:
        session.close()


class FileMapper(Base):
    __tablename__ = 'mapper'

    id = Column(Integer, primary_key=True, autoincrement=True)
    localdir = Column(String(128), nullable=False)
    basedir = Column(String(48), nullable=False)
    remotedir = Column(String(128), nullable=False)
    processeddir = Column(String(48), nullable=True)
    regex = Column(String(64), nullable=True)


class History(Base):
    __tablename__ = 'history'
    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(128), nullable=False, index=True)
    size = Column(Integer, nullable=False)
    mtime = Column(DateTime, nullable=False)
    md5sum = Column(String(32), nullable=False, index=True)


Base.metadata.create_all(engine)
