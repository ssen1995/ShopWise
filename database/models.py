from dataclasses import dataclass
from typing import Optional

@dataclass
class Product:
    id: str
    name: str
    category: str
    image_url: Optional[str] = None
    mrp: Optional[float] = None
    average_price: Optional[float] = None
    lowest_price: Optional[float] = None
