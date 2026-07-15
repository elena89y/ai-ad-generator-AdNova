from pydantic import BaseModel


class AdminMeResponse(BaseModel):
    id: int
    username: str
    email: str
    role: str
