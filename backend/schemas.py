from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


# === Registration ===

class RegistrationRequest(BaseModel):
    provider: str = "outlook"  # gmail, outlook, yahoo, aol, hotmail
    quantity: int = 1
    threads: int = 1
    proxy_id: Optional[int] = None  # If None, auto-rotate
    sms_service: str = "grizzly"
    country: str = "US"
    gender: str = "random"  # male, female, random
    language: str = "en"
    farm_id: Optional[int] = None  # assign to farm on birth


# === Proxy ===

class ProxyImportRequest(BaseModel):
    proxies: List[str]  # "ip:port:user:pass" or "ip:port"
    protocol: str = "http"  # http, socks5
    proxy_type: str = "residential"  # mobile, residential, isp, datacenter
    geo: Optional[str] = None
    expires_at: Optional[datetime] = None


# === Farm ===

class FarmCreate(BaseModel):
    name: str
    description: Optional[str] = None

class FarmMerge(BaseModel):
    source_farm_ids: List[int]
    target_name: str

class FarmSplit(BaseModel):
    farm_id: int
    split_by: str = "provider"  # provider, geo, status
    new_farm_name_prefix: str = "Split"

class FarmMoveAccounts(BaseModel):
    account_ids: List[int]
    target_farm_id: int

class FarmRemoveAccounts(BaseModel):
    account_ids: List[int]


# === Template ===

class TemplateCreate(BaseModel):
    name: str
    subject: str
    body: str
    content_type: str = "html"  # html, plain
    language: str = "en"
    niche: str = ""



# === Recipient Database ===

class DatabaseEntry(BaseModel):
    email: str
    first_name: str = ""
    last_name: str = ""

class DatabaseUpload(BaseModel):
    name: str
    entries: List[DatabaseEntry]


# === Link ===

class LinkCreate(BaseModel):
    name: str
    url: str

class LinkUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    active: Optional[bool] = None


# === Warmup ===

class WarmupStart(BaseModel):
    farm_ids: List[int]
    threads: int = 5
    custom_schedule: Optional[dict] = None  # override default schedule


# === Work / Sending ===

class WorkStart(BaseModel):
    farm_ids: List[int]
    database_id: int
    template_id: int
    link_ids: Optional[List[int]] = None
    per_account_daily_limit: int = 50
    delay_min_sec: int = 30
    delay_max_sec: int = 120
    threads: int = 10
    schedule_start_hour: int = 8   # send window start
    schedule_end_hour: int = 22    # send window end
    rotate_links: bool = True


# === Generic ===

class SMSRequest(BaseModel):
    service: str  # "gmail", "outlook"
    country: str = "any"

class CaptchaRequest(BaseModel):
    website_url: str
    website_key: str
    task_type: str = "RecaptchaV2TaskProxyless"
