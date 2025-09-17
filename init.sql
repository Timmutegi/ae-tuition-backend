-- Initialize AE Tuition Database
-- This file is automatically executed when the PostgreSQL container starts

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Set timezone
SET timezone = 'UTC';

-- Create initial database user if needed
-- (User creation is handled by environment variables in docker-compose)