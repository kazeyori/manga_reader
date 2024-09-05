from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import RedirectResponse, FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from pathlib import Path as PathLib
import uvicorn
import logging
import os
import time
from database import get_db, Library, Comic, Base, engine, get_comic
from pydantic import BaseModel
from sqlalchemy import delete
from urllib.parse import unquote, quote
from fastapi import Path
import zipfile
import rarfile
from io import BytesIO
from sqlalchemy import inspect, Boolean
from sqlalchemy import text as sa_text

app = FastAPI()
logger = logging.getLogger("uvicorn.info")

# 设置静态文件路径
app.mount("/static", StaticFiles(directory="static"), name="static")

# 添加一个新的路由来处理默认缩略图
@app.get("/static/default-thumbnail.png")
async def get_default_thumbnail():
    default_thumbnail_path = os.path.join("static", "default-thumbnail.png")
    if os.path.exists(default_thumbnail_path):
        return FileResponse(default_thumbnail_path)
    else:
        # 如果默认缩略图不存在，返回一个 1x1 像素的透明图片
        return Response(content=b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0bIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82', media_type="image/png")

@app.get("/")
async def read_root():
    return FileResponse('static/series.html')

@app.get("/admin")
async def admin_page():
    return FileResponse('static/admin.html')

@app.get("/reader/{comic_id}")
@app.get("/reader/{comic_id}/{subfolder:path}")
async def reader_page(comic_id: int, subfolder: str = "", db: Session = Depends(get_db)):
    comic = db.query(Comic).filter(Comic.id == comic_id).first()
    if not comic:
        raise HTTPException(status_code=404, detail="Comic not found")
    
    if subfolder:
        # 处理子文件夹
        subfolder_path = os.path.join(comic.path, subfolder)
        if not os.path.exists(subfolder_path) or not os.path.isdir(subfolder_path):
            raise HTTPException(status_code=404, detail="Subfolder not found")
        
        # 查找或创建子文件夹对应的 Comic 记录
        sub_comic = db.query(Comic).filter(Comic.path == subfolder_path).first()
        if not sub_comic:
            sub_comic = Comic(title=os.path.basename(subfolder_path), path=subfolder_path, library_id=comic.library_id, parent_id=comic.id)
            db.add(sub_comic)
            db.commit()
        
        comic_id = sub_comic.id
    
    return FileResponse('static/reader.html')

class LibraryCreate(BaseModel):
    name: str
    folderName: str

@app.post("/admin/add_library")
async def add_library(library: LibraryCreate, db: Session = Depends(get_db)):
    logger.info(f"Received request to add library: {library.name} with folder {library.folderName}")
    
    base_path = "E:/PythonProject/manga_reader/comics"  # 确保这个路径是正确的
    full_path = os.path.normpath(os.path.join(base_path, library.folderName))
    
    logger.info(f"Base path: {base_path}")
    logger.info(f"Folder name: {library.folderName}")
    logger.info(f"Constructed full path: {full_path}")
    
    # 验证基础路径是否存在
    if not os.path.exists(base_path):
        logger.error(f"Base path does not exist: {base_path}")
        raise HTTPException(status_code=400, detail=f"Base path does not exist: {base_path}")
    
    # 如果文件夹不存在，尝试创建
    if not os.path.exists(full_path):
        try:
            os.makedirs(full_path)
            logger.info(f"Created new directory: {full_path}")
        except Exception as e:
            logger.error(f"Failed to create directory: {full_path}. Error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to create directory: {str(e)}")
    
    if not os.path.isdir(full_path):
        logger.warning(f"Path is not a directory: {full_path}")
        raise HTTPException(status_code=400, detail="Path is not a directory")
    
    # 检查是否已存在同名或同路径的库
    existing_library = db.query(Library).filter((Library.name == library.name) | (Library.path == full_path)).first()
    if existing_library:
        logger.warning(f"Library already exists: {library.name} or {full_path}")
        raise HTTPException(status_code=400, detail="Library with this name or path already exists")
    
    db_library = Library(name=library.name, path=full_path)
    db.add(db_library)
    db.commit()
    db.refresh(db_library)
    
    # 立即更新漫画数据库
    update_comics_db(db, db_library)
    
    # 为新添加的库挂载静态文件路径
    try:
        app.mount(f"/comics/{library.name}", StaticFiles(directory=full_path), name=f"comics_{library.name}")
        logger.info(f"Mounted new comic folder: {library.name} at {full_path}")
    except Exception as e:
        logger.error(f"Failed to mount new comic folder: {library.name} at {full_path}. Error: {str(e)}")
        # 如果挂载失败，从数据库中删除这个库
        db.delete(db_library)
        db.commit()
        raise HTTPException(status_code=500, detail="Failed to mount comic folder")
    
    logger.info(f"Successfully added library: {library.name} at {full_path}")
    return {"status": "success", "message": "Library added successfully"}

@app.get("/admin/libraries")
async def get_libraries(db: Session = Depends(get_db)):
    libraries = db.query(Library).all()
    return [{"id": lib.id, "name": lib.name, "path": lib.path} for lib in libraries]

@app.get("/comics")
async def get_comics_list(request: Request, db: Session = Depends(get_db)):
    comics = db.query(Comic).all()
    libraries = db.query(Library).all()
    
    base_url = str(request.base_url).rstrip('/')
    comic_list = []
    for c in comics:
        thumbnail = None
        comic_path = PathLib(c.path)
        if c.is_archive:
            # 处理压缩文件
            archive_contents = get_archive_contents(c.path)
            image_files = [f for f in archive_contents if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp'))]
            if image_files:
                first_image = sorted(image_files)[0]
                thumbnail = f"{base_url}/comic_image/{c.id}/{quote(first_image)}"
        elif comic_path.exists() and comic_path.is_dir():
            # 处理普通目录
            image_files = [f for f in comic_path.iterdir() if f.suffix.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.webp']]
            if image_files:
                first_image = sorted(image_files)[0]
                thumbnail = f"{base_url}/comics/{c.library.name}/{c.title}/{first_image.name}"
        
        comic_list.append({
            "id": c.id,
            "title": c.title,
            "library_id": c.library_id,
            "thumbnail": thumbnail,
            "is_archive": c.is_archive
        })
    
    library_list = [{"id": l.id, "name": l.name, "path": l.path} for l in libraries]
    
    logger.info(f"Retrieved {len(comics)} comics and {len(libraries)} libraries")
    
    return JSONResponse(content={
        "comics": comic_list,
        "libraries": library_list
    })

@app.get("/comic/{comic_id_or_title}")
async def get_comic_contents(
    request: Request,
    comic_id_or_title: str = Path(...),
    db: Session = Depends(get_db)
):
    logger.info(f"Received request for comic_id_or_title: {comic_id_or_title}")
    
    # 尝试将输入转换为整数（ID）
    try:
        comic_id = int(comic_id_or_title)
        comic = db.query(Comic).filter(Comic.id == comic_id).first()
        logger.info(f"Query result for comic_id {comic_id}: {comic}")
    except ValueError:
        # 如果无法转换为整数，则将其视为标题
        comic_title = unquote(comic_id_or_title)
        comic = db.query(Comic).filter(Comic.title == comic_title).first()
        logger.info(f"Query result for comic_title {comic_title}: {comic}")

    if not comic:
        logger.warning(f"Comic not found: {comic_id_or_title}")
        raise HTTPException(status_code=404, detail=f"Comic not found: {comic_id_or_title}")
    
    comic_path = PathLib(comic.path)
    if not comic_path.exists():
        raise HTTPException(status_code=404, detail=f"Item not found: {comic_path}")
    
    base_url = str(request.base_url).rstrip('/')
    contents = []

    if comic.is_archive:
        archive_contents = get_archive_contents(comic.path)
        for item in archive_contents:
            if item.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                contents.append({
                    "type": "image",
                    "path": f"{base_url}/comic_image/{comic.id}/{quote(item)}"
                })
    else:
        for item in sorted(comic_path.iterdir()):
            if item.is_dir():
                sub_comic = db.query(Comic).filter(Comic.path == str(item), Comic.parent_id == comic.id).first()
                if not sub_comic:
                    sub_comic = Comic(title=item.name, path=str(item), library_id=comic.library_id, parent_id=comic.id)
                    db.add(sub_comic)
                    db.commit()
                
                thumbnail = f"{base_url}/static/default-thumbnail.png"
                for subitem in item.iterdir():
                    if subitem.suffix.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
                        thumbnail = f"{base_url}/comics/{quote(comic.library.name)}/{quote(comic.title)}/{quote(item.name)}/{quote(subitem.name)}"
                        break
                contents.append({
                    "type": "folder",
                    "id": sub_comic.id,
                    "name": item.name,
                    "thumbnail": thumbnail
                })
            elif item.suffix.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
                contents.append({
                    "type": "image",
                    "path": f"{base_url}/comics/{quote(comic.library.name)}/{quote(comic.title)}/{quote(item.name)}"
                })
    
    prev_comic = db.query(Comic).filter(Comic.id < comic.id, Comic.parent_id == comic.parent_id).order_by(Comic.id.desc()).first()
    next_comic = db.query(Comic).filter(Comic.id > comic.id, Comic.parent_id == comic.parent_id).order_by(Comic.id.asc()).first()
    
    return JSONResponse(content={
        "id": comic.id,
        "title": comic.title,
        "contents": contents,
        "prev_comic": prev_comic.id if prev_comic else None,
        "next_comic": next_comic.id if next_comic else None,
        "is_first": prev_comic is None,
        "is_last": next_comic is None,
        "parent_id": comic.parent_id
    })

def get_archive_contents(archive_path):
    if archive_path.lower().endswith('.zip'):
        with zipfile.ZipFile(archive_path, 'r') as zip_ref:
            return zip_ref.namelist()
    elif archive_path.lower().endswith('.rar'):
        with rarfile.RarFile(archive_path, 'r') as rar_ref:
            return rar_ref.namelist()
    else:
        return []

@app.get("/comic_image/{comic_id}/{image_path:path}")
async def get_comic_image(comic_id: int, image_path: str, db: Session = Depends(get_db)):
    comic = db.query(Comic).filter(Comic.id == comic_id).first()
    if not comic or not comic.is_archive:
        raise HTTPException(status_code=404, detail="Comic not found or not an archive")

    try:
        image_data = get_image_from_archive(comic.path, image_path)
        if not image_data:
            raise HTTPException(status_code=404, detail="Image not found in archive")
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error reading image from archive: {e}")
        raise HTTPException(status_code=500, detail="Error reading image from archive")

    return Response(content=image_data, media_type="image/jpeg")

def get_image_from_archive(archive_path, image_path):
    if archive_path.lower().endswith('.zip'):
        with zipfile.ZipFile(archive_path, 'r') as zip_ref:
            return zip_ref.read(image_path)
    elif archive_path.lower().endswith('.rar'):
        try:
            with rarfile.RarFile(archive_path, 'r') as rar_ref:
                return rar_ref.read(image_path)
        except rarfile.RarCannotExec as e:
            logger.error(f"Failed to open RAR file: {e}")
            logger.error(f"UnRAR tool path: {rarfile.UNRAR_TOOL}")
            raise HTTPException(status_code=500, detail="Failed to open RAR file")
        except rarfile.Error as e:
            logger.error(f"RAR file error: {e}")
            raise HTTPException(status_code=500, detail="RAR file error")
    else:
        return None

@app.get("/{comic_id}")
async def redirect_to_comic(comic_id: str, request: Request, db: Session = Depends(get_db)):
    # 首先尝试直接查找匹配的 id
    comic = db.query(Comic).filter(Comic.id == comic_id).first()
    
    # 如果没有找到，尝试查找匹配的标题
    if not comic:
        comic = db.query(Comic).filter(Comic.title.contains(comic_id)).first()
    
    if not comic:
        raise HTTPException(status_code=404, detail="Comic not found")
    
    # 重定向到新的 reader 页面
    return RedirectResponse(url=f"/reader/{comic.id}")

def is_archive(file_path):
    return file_path.lower().endswith(('.zip', '.rar'))

def update_comics_db(db: Session, library: Library, parent_id=None, current_path=None):
    if current_path is None:
        current_path = library.path
    
    logger.info(f"Updating comics for path: {current_path}")
    for item in os.listdir(current_path):
        item_path = os.path.join(current_path, item)
        relative_path = os.path.relpath(item_path, library.path)
        
        if os.path.isdir(item_path) or is_archive(item_path):
            existing_comic = db.query(Comic).filter(Comic.title == relative_path, Comic.library_id == library.id).first()
            if not existing_comic:
                comic = Comic(title=relative_path, path=item_path, library_id=library.id, parent_id=parent_id, is_archive=is_archive(item_path))
                db.add(comic)
                db.flush()
                logger.info(f"Added new comic: {relative_path} with id {comic.id}, is_archive: {comic.is_archive}")
            else:
                comic = existing_comic
                comic.is_archive = is_archive(item_path)  # 更新现有记录的 is_archive 字段
                logger.info(f"Updated existing comic: {relative_path} with id {comic.id}, is_archive: {comic.is_archive}")
            
            if os.path.isdir(item_path):
                # 递归处理子文件夹
                update_comics_db(db, library, parent_id=comic.id, current_path=item_path)
    
    db.commit()
    logger.info(f"Finished updating comics for path: {current_path}")

# 在 startup_event 函数之前添加这个函数
def clean_invalid_libraries(db: Session):
    invalid_libraries = db.query(Library).filter(Library.path == '').all()
    for library in invalid_libraries:
        logger.warning(f"Removing invalid library: {library.name}")
        db.delete(library)
    db.commit()

def run_migration(engine):
    inspector = inspect(engine)
    columns = [c['name'] for c in inspector.get_columns('comics')]
    if 'is_archive' not in columns:
        logger.info("Running database migration to add 'is_archive' column")
        with engine.begin() as connection:
            connection.execute(sa_text("ALTER TABLE comics ADD COLUMN is_archive BOOLEAN"))
        logger.info("Migration completed successfully")
    else:
        logger.info("'is_archive' column already exists, skipping migration")

@app.on_event("startup")
async def startup_event():
    global engine  # 确保我们使用的是全局的 engine 变量
    
    # 检查并创建 comics 文件夹
    comics_folder = os.path.join(os.path.dirname(__file__), "comics")
    if not os.path.exists(comics_folder):
        os.makedirs(comics_folder)
        logger.info(f"Created comics folder: {comics_folder}")
    else:
        logger.info(f"Comics folder already exists: {comics_folder}")

    # 关闭所有现有的数据库连接
    engine.dispose()
    
    # 重新创建数据库表（如果不存在）
    Base.metadata.create_all(bind=engine)
    
    # 运行迁移
    run_migration(engine)
    
    db = next(get_db())
    clean_invalid_libraries(db)
    libraries = db.query(Library).all()
    for library in libraries:
        if library.path and os.path.exists(library.path):
            try:
                app.mount(f"/comics/{library.name}", StaticFiles(directory=library.path), name=f"comics_{library.name}")
                logger.info(f"Mounted comic folder: {library.name} at {library.path}")
            except Exception as e:
                logger.error(f"Failed to mount comic folder: {library.name} at {library.path}. Error: {str(e)}")
        else:
            logger.warning(f"Invalid library path for {library.name}: {library.path}")
    logger.info("Finished mounting comic folders for all libraries")

    comic_count = db.query(Comic).count()
    logger.info(f"Total comics in database: {comic_count}")
    if comic_count == 0:
        logger.warning("No comics found in database. Make sure to add libraries and update the database.")

@app.get("/test_path/{folder_name}")
async def test_path(folder_name: str):
    base_path = "E:/PythonProject/manga_reader/comics"
    full_path = os.path.normpath(os.path.join(base_path, folder_name))
    exists = os.path.exists(full_path)
    is_dir = os.path.isdir(full_path)
    return {"base_path": base_path, "full_path": full_path, "exists": exists, "is_dir": is_dir}

@app.get("/admin/check_library/{library_id}")
async def check_library(library_id: int, db: Session = Depends(get_db)):
    library = db.query(Library).filter(Library.id == library_id).first()
    if not library:
        raise HTTPException(status_code=404, detail="Library not found")
    
    folders = [f for f in os.listdir(library.path) if os.path.isdir(os.path.join(library.path, f))]
    comics = db.query(Comic).filter(Comic.library_id == library_id).all()
    
    return JSONResponse(content={
        "library_name": library.name,
        "library_path": library.path,
        "folders_in_path": folders,
        "comics_in_db": [c.title for c in comics]
    })

@app.delete("/admin/delete_library/{library_id}")
async def delete_library(library_id: int, db: Session = Depends(get_db)):
    library = db.query(Library).filter(Library.id == library_id).first()
    if not library:
        raise HTTPException(status_code=404, detail="Library not found")
    
    # 删除与该资料库相关的所有漫画
    db.query(Comic).filter(Comic.library_id == library_id).delete()
    
    # 删除资料库
    db.delete(library)
    db.commit()
    
    # 卸载静态文件路径
    try:
        app.routes = [route for route in app.routes if route.name != f"comics_{library.name}"]
        logger.info(f"Unmounted comic folder: {library.name}")
    except Exception as e:
        logger.error(f"Failed to unmount comic folder: {library.name}. Error: {str(e)}")
    
    logger.info(f"Successfully deleted library: {library.name}")
    return {"status": "success", "message": "Library deleted successfully"}

# 添加一个新的路由来处理子文件夹
@app.get("/comics/{library_name}/{comic_title:path}")
async def get_comic_file(library_name: str, comic_title: str, db: Session = Depends(get_db)):
    library_name = unquote(library_name)
    comic_title = unquote(comic_title)
    
    library = db.query(Library).filter(Library.name == library_name).first()
    if not library:
        raise HTTPException(status_code=404, detail="Library not found")
    
    file_path = os.path.join(library.path, comic_title)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(file_path)

@app.get("/debug/comic/{comic_id}")
async def debug_comic(comic_id: int, db: Session = Depends(get_db)):
    comic = db.query(Comic).filter(Comic.id == comic_id).first()
    if comic:
        return {
            "id": comic.id,
            "title": comic.title,
            "path": comic.path,
            "library_id": comic.library_id,
            "parent_id": comic.parent_id
        }
    else:
        return {"error": "Comic not found"}

@app.get("/debug/all_comics")
async def debug_all_comics(db: Session = Depends(get_db)):
    comics = db.query(Comic).all()
    return [{"id": c.id, "title": c.title, "path": c.path, "library_id": c.library_id, "parent_id": c.parent_id} for c in comics]

# 设置 UnRAR 工具的路径
rarfile.UNRAR_TOOL = r"C:\Program Files\WinRAR\UnRAR.exe"  # 根据你的实际安装路径调整

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    uvicorn.run("comic_main:app", host="0.0.0.0", port=18081, reload=True)


