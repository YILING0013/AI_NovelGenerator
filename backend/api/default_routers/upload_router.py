import os
import hashlib
from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/upload", tags=["upload"])

COVER_DIR = "static/covers"
os.makedirs(COVER_DIR, exist_ok=True)

@router.post("/cover")
async def upload_cover(file: UploadFile = File(...)):
    """上传小说封面图片，返回图片的URL地址。"""
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File provided is not an image.")

    content = await file.read()
    
    file_hash = hashlib.sha256(content).hexdigest()
    
    ext = ".jpg"
    if file.filename:
        _, original_ext = os.path.splitext(file.filename)
        if original_ext:
            ext = original_ext.lower()
    
    filename = f"{file_hash}{ext}"
    filepath = os.path.join(COVER_DIR, filename)
    
    if not os.path.exists(filepath):
        with open(filepath, "wb") as f:
            f.write(content)
            
    cover_url = f"/static/covers/{filename}"
    return {"url": cover_url, "message": "Image uploaded successfully"}
