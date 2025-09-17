# AE Tuition Backend

An Ed-Tech platform backend API for managing online tests, student assessments, and educational content delivery.

## Features

### ✅ Implemented
- 🔐 **Admin Authentication**: Secure admin login with JWT tokens and role-based access control
- 🗄️ **Database Schema**: Complete PostgreSQL schema with all necessary tables
- 🐳 **Docker Support**: Full containerization with dev and production environments
- 📖 **API Documentation**: Automatic OpenAPI/Swagger documentation

### 🚧 In Development
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

Copy the example environment file and configure your settings:

```bash
cp .env.example .env
```

Edit `.env` with your configuration. The Docker Compose files will automatically load these variables:

```env
# Application settings
SECRET_KEY=your-secret-key-here  # Generate a secure random key for production
API_HOST=0.0.0.0
API_PORT=9000

# Database settings
POSTGRES_USER=ae
POSTGRES_PASSWORD=your-secure-password  # Use a strong password
POSTGRES_DB=ae_tuition
POSTGRES_PORT=5440  # External port for PostgreSQL

# AWS settings (for file storage)
AWS_ACCESS_KEY=your-aws-access-key
AWS_SECRET_KEY=your-aws-secret-key
AWS_S3_BUCKET=your-bucket-name
AWS_REGION=eu-west-2

# CloudFront CDN
CLOUDFRONT_URL=https://your-cloudfront-url.cloudfront.net/

# Email service (Resend)
RESEND_API_KEY=your-resend-api-key
FROM_EMAIL=noreply@your-domain.com

# Frontend URL (for CORS)
FRONTEND_URL=http://localhost:4200

# Default admin account (created on first startup)
DEFAULT_ADMIN_EMAIL=admin@your-domain.com
DEFAULT_ADMIN_USERNAME=admin
DEFAULT_ADMIN_PASSWORD=ChangeThisPassword123!!  # MUST change in production
DEFAULT_ADMIN_FULL_NAME=Admin User
```

⚠️ **Important**:
- Never commit the `.env` file to version control
- Use strong, unique passwords in production
- Generate a secure `SECRET_KEY` for JWT signing
- Update AWS credentials with appropriate permissions

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

## Running the Application

### Development Mode

#### Using Docker Compose (Recommended):

The Docker Compose files now automatically load environment variables from your `.env` file:

```bash
# Start all services
docker-compose -f docker-compose-dev.yml up --build

# Run in background
docker-compose -f docker-compose-dev.yml up --build -d

# View logs
docker-compose -f docker-compose-dev.yml logs -f

# Stop services
docker-compose -f docker-compose-dev.yml down
```

The API will be available at `http://localhost:9000`

#### Using Python directly (Alternative):
```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
uvicorn app.main:app --reload --host 0.0.0.0 --port 9000
```

### Production Mode

```bash
# Start all services with nginx
docker-compose -f docker-compose-prod.yml up --build -d

# View logs
docker-compose -f docker-compose-prod.yml logs -f

# Stop services
docker-compose -f docker-compose-prod.yml down
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

### ✅ Implemented Endpoints

#### Authentication
- `POST /api/v1/auth/login` - Unified login for admin and student users
- `POST /api/v1/auth/logout` - User logout (client-side token removal)
- `GET /api/v1/auth/me` - Get current authenticated user info
- `POST /api/v1/auth/refresh` - Refresh JWT token
- `GET /api/v1/auth/admin/me` - Admin-only endpoint for admin info

#### System
- `GET /` - API information and status
- `GET /health` - Health check endpoint

### 🚧 Planned Endpoints (Not Yet Implemented)

#### Admin Operations
- `POST /api/v1/admin/students/upload` - Upload CSV for bulk student creation
- `GET /api/v1/admin/students` - List all students
- `POST /api/v1/admin/tests` - Create new test
- `GET /api/v1/admin/tests` - List all tests
- `POST /api/v1/admin/tests/{test_id}/assign` - Assign test to class
- `GET /api/v1/admin/results` - View all test results

#### Student Operations
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