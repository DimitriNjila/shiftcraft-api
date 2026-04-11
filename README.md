# ShiftCraft API

> A modern restaurant scheduling backend built with FastAPI, Supabase, and Python.

ShiftCraft API provides a robust backend for restaurant managers to efficiently schedule staff, manage employees, and automate shift generation with intelligent algorithms.

## 🚀 Features

- **Employee Management**: Complete CRUD operations for staff members
- **Schedule Management**: Create and manage weekly schedules
- **Shift Management**: Assign shifts with overlap detection and validation
- **Auto-Generation**: Intelligent schedule generation with fair hour distribution
- **Shift Templates**: Reusable shift patterns for quick schedule creation
- **Operating Hours**: Configurable restaurant hours per day
- **Authentication**: Supabase Auth integration (ready for multi-tenant)

## 🛠️ Tech Stack

- **Framework**: [FastAPI](https://fastapi.tiangolo.com/) (Python 3.11+)
- **Database**: [Supabase](https://supabase.com/) (PostgreSQL)
- **ORM**: Supabase Python Client
- **Validation**: Pydantic v2
- **Testing**: Pytest with Supabase local development

## 📋 Prerequisites

- Python 3.11 or higher
- Supabase account and project
- Docker (optional, for containerized deployment)

## 🏃 Quick Start

### Local Development

1. **Clone the repository**
```bash
   git clone https://github.com/yourusername/shiftcraft-api.git
   cd shiftcraft-api
```

2. **Create virtual environment**
```bash
   python -m venv venv
   source venv/bin/activate  
```

3. **Install dependencies**
```bash
   uv install
```

4. **Set up environment variables**
```bash
   cp .env.example .env
```
   
   Edit `.env` with your credentials:
```env
   ENVIRONMENT=development
   SUPABASE_URL=https://your-project.supabase.co
   SUPABASE_SERVICE_KEY=your-service-role-key
```

5. **Run the development server**
```bash
   uvicorn app.main:app --reload
```

6. **Access the API**
   - API: http://localhost:8000
   - Interactive docs: http://localhost:8000/docs
   - Alternative docs: http://localhost:8000/redoc

### Docker Deployment

1. **Build the image**
```bash
   docker build -t shiftcraft-api .
```

2. **Run the container**
```bash
   docker run -d \
     -p 8000:8000 \
     -e SUPABASE_URL=your-url \
     -e SUPABASE_SERVICE_KEY=your-key \
     --name shiftcraft-api \
     shiftcraft-api
```

3. **Or use Docker Compose**
```bash
   docker-compose up -d
```

## 📚 API Documentation

### Core Endpoints

#### Employees
- `GET /api/employees` - List all employees
- `GET /api/employees/{id}` - Get employee by ID
- `POST /api/employees` - Create new employee
- `PATCH /api/employees/{id}` - Update employee
- `DELETE /api/employees/{id}` - Delete employee

#### Schedules
- `GET /api/schedules` - List schedules
- `GET /api/schedules/{id}` - Get schedule with shifts
- `POST /api/schedules` - Create empty schedule
- `POST /api/schedules/generate` - Auto-generate schedule
- `DELETE /api/schedules/{id}` - Delete schedule

#### Shifts
- `GET /api/shifts` - List shifts (with filters)
- `GET /api/shifts/{id}` - Get shift by ID
- `POST /api/shifts` - Create shift
- `PATCH /api/shifts/{id}` - Update shift
- `DELETE /api/shifts/{id}` - Delete shift


### Example Requests

**Create Employee**
```bash
curl -X POST http://localhost:8000/api/employees \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Alice Johnson",
    "role": "Server",
    "restaurant_id": "550e8400-e29b-41d4-a716-446655440000"
  }'
```

**Generate Schedule**
```bash
curl -X POST http://localhost:8000/api/schedules/generate \
  -H "Content-Type: application/json" \
  -d '{
    "week_start": "2026-03-16",
    "restaurant_id": "550e8400-e29b-41d4-a716-446655440000",
    "shift_templates": [
      {
        "day_of_week": 1,
        "start_time": "11:00:00",
        "end_time": "15:00:00",
        "role": "Server",
        "count": 2
      }
    ]
  }'
```



