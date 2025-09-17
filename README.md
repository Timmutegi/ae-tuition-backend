# AE Tuition Backend

An Ed-Tech platform backend API for managing online tests, student assessments, and educational content delivery.

## Features

- 🔐 **Admin Authentication**: Secure admin login with role-based access control
- 👥 **Student Management**: Bulk student creation via CSV upload with automated email notifications
- 📝 **Test Management**: Create and assign tests to student classes with scheduling
- ❓ **Question Bank**: Manage test questions with support for image uploads to AWS S3
- 🎓 **Student Portal**: Students can view assigned tests and track their scores
- ⏱️ **Timed Testing**: Time-tracked test sessions with automatic submission
- 📊 **Analytics**: Comprehensive scoring system with performance tracking

## Tech Stack

- **Framework**: FastAPI (Python)
- **Database**: PostgreSQL
- **Email Service**: Resend
- **File Storage**: AWS S3
- **CDN**: AWS CloudFront
- **Containerization**: Docker

## Prerequisites

- Python 3.11+
- PostgreSQL 14+
- Docker and Docker Compose
- AWS Account (for S3 storage)
- Resend Account (for email notifications)

## Installation

### 1. Clone the repository
```bash
git clone https://github.com/your-org/ae-tuition-backend.git
cd ae-tuition-backend
```

### 2. Set up environment variables
```bash
cp .env.example .env
```

Edit `.env` with your configuration:
```env
# Application
SECRET_KEY=your-secret-key-here
API_HOST=0.0.0.0
API_PORT=9000

# Database
POSTGRES_USER=ae
POSTGRES_PASSWORD=your-password
POSTGRES_DB=ae_tuition
POSTGRES_PORT=5440

# AWS
AWS_ACCESS_KEY=your-access-key
AWS_SECRET_KEY=your-secret-key
AWS_S3_BUCKET=ae-tuition
AWS_REGION=eu-west-2

# Email
RESEND_API_KEY=your-resend-api-key
FROM_EMAIL=noreply@ae-tuition.com

# Admin
DEFAULT_ADMIN_EMAIL=admin@ae-tuition.com
DEFAULT_ADMIN_USERNAME=admin
DEFAULT_ADMIN_PASSWORD=secure-password
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

## Running the Application

### Development Mode

#### Using Python directly:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 9000
```

#### Using Docker Compose:
```bash
docker-compose -f docker-compose-dev.yml up --build
```

The API will be available at `http://localhost:9000`

### Production Mode

```bash
docker-compose -f docker-compose-prod.yml up --build -d
```

The API will be available at `http://your-domain.com` (port 80)

## API Documentation

Once running, access the interactive API documentation:
- Swagger UI: `http://localhost:9000/docs`
- ReDoc: `http://localhost:9000/redoc`

## Project Structure

```
ae-tuition-backend/
├── app/
│   ├── api/           # API endpoints
│   ├── core/          # Core configuration
│   ├── models/        # Database models
│   ├── schemas/       # Pydantic schemas
│   ├── services/      # Business logic
│   ├── middleware/    # Custom middleware
│   ├── utils/         # Utility functions
│   └── main.py        # Application entry point
├── tests/             # Test suite
├── alembic/           # Database migrations
├── docker-compose-dev.yml
├── docker-compose-prod.yml
├── Dockerfile
├── requirements.txt
└── README.md
```

## Key API Endpoints

### Authentication
- `POST /api/v1/auth/login` - User login
- `POST /api/v1/auth/logout` - User logout
- `GET /api/v1/auth/me` - Get current user

### Admin Operations
- `POST /api/v1/admin/students/upload` - Upload CSV for bulk student creation
- `GET /api/v1/admin/students` - List all students
- `POST /api/v1/admin/tests` - Create new test
- `GET /api/v1/admin/tests` - List all tests
- `POST /api/v1/admin/tests/{test_id}/assign` - Assign test to class
- `GET /api/v1/admin/results` - View all test results

### Student Operations
- `GET /api/v1/student/dashboard` - Student dashboard data
- `GET /api/v1/student/tests` - List assigned tests
- `GET /api/v1/student/tests/{test_id}` - Get test details
- `POST /api/v1/student/tests/{test_id}/start` - Start test attempt
- `POST /api/v1/student/tests/{test_id}/submit` - Submit test answers
- `GET /api/v1/student/results` - View own test results

## Database Schema

The application uses PostgreSQL with the following main tables:
- `users` - Admin and student accounts
- `classes` - Student class groups
- `tests` - Test definitions
- `questions` - Question bank
- `test_assignments` - Test-to-class mappings
- `test_results` - Student scores and completion times
- `test_attempts` - Individual test sessions

## CSV Upload Format

For bulk student upload, use CSV with these columns:
```csv
class,year_group,email_address,name
7A,7,john.doe@school.com,John Doe
8B,8,jane.smith@school.com,Jane Smith
```

## Testing

Run the test suite:
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app

# Run specific test
pytest tests/test_auth.py
```

## Development Guidelines

1. Follow PEP 8 style guide
2. Write tests for new features
3. Update API documentation
4. Use type hints
5. Handle errors gracefully
6. Log important operations

## Security

- JWT tokens for authentication
- Password hashing with bcrypt
- Role-based access control
- Input validation
- SQL injection prevention via ORM
- XSS protection
- CORS configuration

## Support

For issues or questions, please contact the development team or raise an issue in the repository.

## License

Proprietary - AE Tuition. All rights reserved.