from pydantic import BaseModel
from typing import Optional


class CategoryCreate(BaseModel):
    name: str
    sort_order: int = 0


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    sort_order: Optional[int] = None


class CategoryOut(BaseModel):
    id: int
    name: str
    sort_order: int
    created_at: str


class LogUpdate(BaseModel):
    category_id: Optional[int] = None
    description: Optional[str] = None
    external_link: Optional[str] = None


class StatusUpdate(BaseModel):
    status: str


class ImageOut(BaseModel):
    id: int
    log_id: int
    filename: str
    original_name: str
    created_at: str


class LogOut(BaseModel):
    id: int
    category_id: int
    category_name: str = ""
    description: str
    external_link: str
    status: str
    created_at: str
    updated_at: str
    images: list[ImageOut] = []


class LogListOut(BaseModel):
    items: list[LogOut]
    total: int
    page: int
    size: int
