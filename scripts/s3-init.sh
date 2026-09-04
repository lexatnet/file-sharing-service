#!/bin/sh

init_s3_bucket() {
    echo "Creating s3 bucket '$SERVICE_S3_FILES_BUCKET'"
    /usr/bin/mc mb myminio/$SERVICE_S3_FILES_BUCKET --region=$SERVICE_S3_FILES_REGION;

    #
    # /usr/bin/mc admin accesskey create myminio --access-key 'CLIENT_ID' --secret-key 'CLIENT_SECRET' || true;

    # Create a specific user (client_id)
    echo "Creating s3 bucket user '$SERVICE_S3_FILES_CLIENT_ID'"
    /usr/bin/mc admin user add myminio $SERVICE_S3_FILES_CLIENT_ID $SERVICE_S3_FILES_CLIENT_SECRET;

    # Define a policy for the user (optional, default gives access to everything)
    # You can create a specific policy file and apply it here if needed
    echo "Attaching s3 bucket user readwrite policy '$SERVICE_S3_FILES_CLIENT_ID'"
    /usr/bin/mc admin policy attach myminio readwrite --user $SERVICE_S3_FILES_CLIENT_ID;
    # cat > myuserbucket-policy.json <<EOF
    # {
    #   "Version": "2012-10-17",
    #   "Statement": [
    #       {
    #       "Action": [
    #           "s3:GetBucketLocation",
    #           "s3:ListBucket"
    #       ],
    #       "Effect": "Allow",
    #       "Resource": ["arn:aws:s3:::$SERVICE_S3_FILES_BUCKE"]
    #       },
    #       {
    #       "Action": [
    #           "s3:PutObject",
    #           "s3:GetObject",
    #           "s3:DeleteObject"
    #       ],
    #       "Effect": "Allow",
    #       "Resource": ["arn:aws:s3:::$SERVICE_S3_FILES_BUCKE/*"]
    #       }
    # ]
    # }
    # EOF
    # /usr/bin/mc admin policy set myminio myuserbucket-policy --user=$SERVICE_S3_FILES_CLIENT_ID;
}

# Set up the mc client alias
/usr/bin/mc alias set myminio http://s3:9000 $MINIO_ROOT_USER $MINIO_ROOT_PASSWORD;

# Create the bucket (use -p for public access if needed, or manage policies)
if /usr/bin/mc ls myminio/$SERVICE_S3_FILES_BUCKET > /dev/null 2>&1; then
    echo "Bucket '$SERVICE_S3_FILES_BUCKET' exists"
else
    echo "Bucket '$SERVICE_S3_FILES_BUCKET' does not exist"
    init_s3_bucket
fi



# Exit the container
exit 0;