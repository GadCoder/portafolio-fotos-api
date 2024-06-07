import os
import boto3
from botocore.exceptions import NoCredentialsError


def create_s3_client():
    aws_access_key_id = os.getenv('s3_key')
    aws_secret_access_key = os.getenv('s3_secret_key')
    cloudflare_endpoint = os.getenv('s3_endpoint')
    s3 = boto3.client('s3', aws_access_key_id=aws_access_key_id,
                      aws_secret_access_key=aws_secret_access_key,
                      endpoint_url=cloudflare_endpoint)
    return s3


s3_client = create_s3_client()

def save_photo_on_bucket(local_file_path, filename):
    bucket_name = os.getenv('s3_bucket_name')
    s3_url = os.getenv('s3_url')
    try:
        s3_client.upload_file(local_file_path, bucket_name, filename)
        print("Upload Successful")
        s3_url = f"{s3_url}/{bucket_name}/{filename}"
        return s3_url
    except FileNotFoundError:
        print("The file was not found")
        return None
    except NoCredentialsError:
        print("Credentials not available")
        return None


def delete_from_s3(filename: str):
    bucket_name = os.getenv('s3_bucket_name')
    try:
        s3_client.delete_object(Bucket=bucket_name, Key=filename)
        print(f"File deleted successfully: {filename}")
    except Exception as e:
        print(f"Error deleting file: {e}")
