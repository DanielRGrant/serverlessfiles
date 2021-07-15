import json
import boto3
import os
import logging
import sys
import traceback
from boto3.dynamodb.conditions import Key

upload_bucket = os.environ["S3_MZID_UPLOAD"]
te_progress_db_name = os.environ["MZID_PROGRESS_DB"]
te_db_name = os.environ["MZID_TE_DB"]

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
te_progress_db = dynamodb.Table(te_progress_db_name)
te_db = dynamodb.Table(te_db_name)


def lambda_handler(event, context):
    logging.info(f"Event: {event}")

    file_id = event["file_id"]
    user_id = event["user_id"]

    logging.info(f'Deleting file_id: {file_id}; from user: {user_id}')


    try:
        te_progress_db.update_item(
            Key={
                'user_id': user_id,
                'file_id': file_id
            },
            UpdateExpression="set progress=:p",
            ExpressionAttributeValues={
                ':p': "deleting"
            }
        )
        
        delete_keys = te_db.query(
            IndexName = "get_keys_by_file_id-index",
            KeyConditionExpression = Key("file_id").eq(file_id)
        )["Items"]
        
        dk_batches = [delete_keys[i:i+25] for i in range(0, len(delete_keys), 25)]
        
        for dk_batch in dk_batches:
            with te_db.batch_writer() as batch:
                for dk in dk_batch:
                    batch.delete_item(Key={"file_id#peptide_id#prot_id": dk["file_id#peptide_id#prot_id"]})

        s3_client.delete_object(
            Bucket=upload_bucket,
            Key=file_id
        )

        te_progress_db.delete_item(
            Key={
                'user_id': user_id,
                'file_id': file_id
            }
        )

        return {
            'statusCode': 200
        }

    except:
        exception_type, exception_value, exception_traceback = sys.exc_info()
        traceback_string = traceback.format_exception(exception_type, exception_value, exception_traceback)
        err_msg = json.dumps({
            "errorType": exception_type.__name__,
            "errorMessage": str(exception_value),
            "stackTrace": traceback_string
        })
        logger.error(err_msg)

        te_progress_db.update_item(
            Key={
                "user_id": user_id,
                "file_id": file_id
            },
            UpdateExpression="set progress=:p",
            ExpressionAttributeValues={
                ':p': "delete_failed"
            },
            ReturnValues="UPDATED_NEW"
        )
