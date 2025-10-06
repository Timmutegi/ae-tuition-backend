import boto3
import uuid
from typing import Optional, BinaryIO
from botocore.exceptions import NoCredentialsError, ClientError
from app.core.config import settings
import mimetypes
import os


class S3Service:
    def __init__(self):
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY,
            aws_secret_access_key=settings.AWS_SECRET_KEY,
            region_name=settings.AWS_REGION
        )
        self.bucket_name = settings.AWS_S3_BUCKET
        self.cloudfront_url = settings.CLOUDFRONT_URL

    async def upload_file(
        self,
        file: BinaryIO,
        file_name: str,
        folder: str = "questions"
    ) -> Optional[dict]:
        """
        Upload file to S3 bucket

        Args:
            file: File object to upload
            file_name: Original filename
            folder: S3 folder to upload to (e.g., 'questions', 'tests')

        Returns:
            Dict with s3_key and public_url if successful, None if failed
        """
        try:
            # Generate unique file name
            file_extension = os.path.splitext(file_name)[1]
            unique_filename = f"{uuid.uuid4()}{file_extension}"
            s3_key = f"{folder}/{unique_filename}"

            # Determine content type
            content_type, _ = mimetypes.guess_type(file_name)
            if not content_type:
                content_type = 'application/octet-stream'

            # Read file content into memory to avoid file pointer issues
            file_content = file.read()

            # Create BytesIO object from content
            import io
            file_obj = io.BytesIO(file_content)

            # Upload file
            self.s3_client.upload_fileobj(
                file_obj,
                self.bucket_name,
                s3_key,
                ExtraArgs={
                    'ContentType': content_type,
                    'ContentDisposition': f'inline; filename="{file_name}"'
                }
            )

            # Generate public URL using CloudFront
            if self.cloudfront_url:
                # Remove trailing slash to avoid double slashes
                cloudfront_base = self.cloudfront_url.rstrip('/')
                public_url = f"{cloudfront_base}/{s3_key}"
            else:
                public_url = f"https://{self.bucket_name}.s3.{settings.AWS_REGION}.amazonaws.com/{s3_key}"

            return {
                "s3_key": s3_key,
                "public_url": public_url,
                "file_name": file_name,
                "content_type": content_type
            }

        except NoCredentialsError:
            print("AWS credentials not found")
            return None
        except ClientError as e:
            print(f"Error uploading file to S3: {e}")
            return None
        except Exception as e:
            print(f"Unexpected error uploading file: {e}")
            return None

    async def delete_file(self, s3_key: str) -> bool:
        """
        Delete file from S3 bucket

        Args:
            s3_key: S3 key of the file to delete

        Returns:
            True if successful, False otherwise
        """
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            return True
        except ClientError as e:
            print(f"Error deleting file from S3: {e}")
            return False
        except Exception as e:
            print(f"Unexpected error deleting file: {e}")
            return False

    async def generate_presigned_url(
        self,
        s3_key: str,
        expiration: int = 3600
    ) -> Optional[str]:
        """
        Generate presigned URL for file access

        Args:
            s3_key: S3 key of the file
            expiration: URL expiration time in seconds (default 1 hour)

        Returns:
            Presigned URL if successful, None otherwise
        """
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': s3_key},
                ExpiresIn=expiration
            )
            return url
        except ClientError as e:
            print(f"Error generating presigned URL: {e}")
            return None

    async def get_file_info(self, s3_key: str) -> Optional[dict]:
        """
        Get file information from S3

        Args:
            s3_key: S3 key of the file

        Returns:
            File info dict if successful, None otherwise
        """
        try:
            response = self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )

            return {
                "size": response['ContentLength'],
                "last_modified": response['LastModified'],
                "content_type": response.get('ContentType'),
                "etag": response['ETag']
            }
        except ClientError as e:
            print(f"Error getting file info: {e}")
            return None

    async def list_files(self, prefix: str = "", max_keys: int = 1000) -> list:
        """
        List files in S3 bucket with given prefix

        Args:
            prefix: S3 key prefix to filter by
            max_keys: Maximum number of keys to return

        Returns:
            List of file information
        """
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix,
                MaxKeys=max_keys
            )

            files = []
            if 'Contents' in response:
                for obj in response['Contents']:
                    files.append({
                        "key": obj['Key'],
                        "size": obj['Size'],
                        "last_modified": obj['LastModified'],
                        "etag": obj['ETag']
                    })

            return files
        except ClientError as e:
            print(f"Error listing files: {e}")
            return []

    def validate_file(self, file_name: str, file_size: int) -> tuple[bool, str]:
        """
        Validate file for upload

        Args:
            file_name: Name of the file
            file_size: Size of the file in bytes

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check file extension
        allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.svg', '.pdf', '.webp'}
        file_extension = os.path.splitext(file_name)[1].lower()

        if file_extension not in allowed_extensions:
            return False, f"File type not allowed. Allowed types: {', '.join(allowed_extensions)}"

        # Check file size (max 10MB)
        max_size = 10 * 1024 * 1024  # 10MB in bytes
        if file_size > max_size:
            return False, f"File size too large. Maximum size: {max_size // (1024 * 1024)}MB"

        return True, ""

    def get_public_url(self, s3_key: str) -> str:
        """
        Get public URL for an S3 object

        Args:
            s3_key: S3 key of the file

        Returns:
            Public URL
        """
        if self.cloudfront_url:
            # Remove trailing slash to avoid double slashes
            cloudfront_base = self.cloudfront_url.rstrip('/')
            return f"{cloudfront_base}/{s3_key}"
        else:
            return f"https://{self.bucket_name}.s3.{settings.AWS_REGION}.amazonaws.com/{s3_key}"


# Create singleton instance
s3_service = S3Service()