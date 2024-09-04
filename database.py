from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

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

engine = create_engine('sqlite:///comics.db')
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_comic(db: SessionLocal, comic_id: int):
    return db.query(Comic).filter(Comic.id == comic_id).first()