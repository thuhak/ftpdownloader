from sqlalchemy import create_engine, Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from contextlib import contextmanager
from .conf import config


__all__ = ['session_scope', 'FileMapper', 'History']


dbconfig = config['database']
engine_path = 'mysql+pymysql://{user}:{password}@{host}:{port}/{db}'.format(**dbconfig)
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


class BaseModel(Base):
    __abstract__ = True

    def to_dict(self):
        columns = self.__table__.columns.keys()
        ret = {}
        for k in columns:
            ret[k] = getattr(self, k)
        return ret


class FileMapper(BaseModel):
    __tablename__ = 'mapper'

    id = Column(Integer, primary_key=True, autoincrement=True)
    localdir = Column(String(128), nullable=False)
    basedir = Column(String(48), nullable=False)
    remotedir = Column(String(128), nullable=False)
    processeddir = Column(String(48), nullable=True)
    regex = Column(String(64), nullable=True)


class History(BaseModel):
    __tablename__ = 'history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(128), nullable=False, index=True)
    size = Column(Integer, nullable=False)
    mtime = Column(DateTime, nullable=False)
    md5sum = Column(String(32), nullable=False, index=True)
    mapperid = Column(Integer, ForeignKey('mapper.id'))


BaseModel.metadata.create_all(engine)
