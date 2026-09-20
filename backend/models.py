from pydantic import BaseModel
from typing import Any, Optional


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
    field_values: Optional[dict[str, Any]] = None


FIELD_TYPES = ("text", "textarea", "number", "date", "select", "multiselect")
OPTION_TYPES = ("select", "multiselect")


class FieldOptionOut(BaseModel):
    id: int
    field_id: int
    label: str
    sort_order: int


class FieldOptionCreate(BaseModel):
    label: str
    sort_order: int = 0


class FieldOptionUpdate(BaseModel):
    label: Optional[str] = None
    sort_order: Optional[int] = None


class CategoryFieldCreate(BaseModel):
    name: str
    type: str
    required: bool = False
    show_in_list: bool = False
    sort_order: int = 0


class CategoryFieldUpdate(BaseModel):
    # 刻意不含 type：字段类型创建后不可修改，改类型会让已存的值落在错误的列上
    name: Optional[str] = None
    required: Optional[bool] = None
    show_in_list: Optional[bool] = None
    sort_order: Optional[int] = None


class CategoryFieldOut(BaseModel):
    id: int
    category_id: int
    name: str
    type: str
    required: bool
    show_in_list: bool
    sort_order: int
    options: list[FieldOptionOut] = []


class FieldValueOut(BaseModel):
    field_id: int
    name: str
    type: str
    sort_order: int
    show_in_list: bool
    value: Any = None          # 标量值 / select 的 option_id / multiselect 的 option_id 列表
    option_labels: list[str] = []


class UsageOut(BaseModel):
    log_count: int


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
    field_values: list[FieldValueOut] = []


class LogListOut(BaseModel):
    items: list[LogOut]
    total: int
    page: int
    size: int
