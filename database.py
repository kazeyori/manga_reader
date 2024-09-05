from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session, relationship
from sqlalchemy.pool import StaticPool

Base = declarative_base()

class Library(Base):
    __tablename__ = 'libraries'
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    path = Column(String, unique=True)
    comics = relationship("Comic", back_populates="library")

class Comic(Base):
    __tablename__ = "comics"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    path = Column(String)
    library_id = Column(Integer, ForeignKey("libraries.id"))
    parent_id = Column(Integer, ForeignKey("comics.id"), nullable=True)
    is_archive = Column(Boolean, default=False)  # 新增字段

    library = relationship("Library", back_populates="comics")
    parent = relationship("Comic", remote_side=[id], back_populates="children")
    children = relationship("Comic", back_populates="parent")

SQLALCHEMY_DATABASE_URL = "sqlite:///./sql_app.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    echo=True  # 添加这行以输出 SQL 语句，方便调试
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_comic(db: SessionLocal, comic_id: int):
    return db.query(Comic).filter(Comic.id == comic_id).first()

# 确保在应用启动时创建所有表
Base.metadata.create_all(bind=engine)