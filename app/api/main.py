from fastapi import FastAPI
from .routes import employee_router, schedule_router

app = FastAPI()
app.include_router(employee_router.employee_router)
app.include_router(schedule_router.schedule_router)


@app.get("/")
async def read_root():
    return {"Hello": "World"}
