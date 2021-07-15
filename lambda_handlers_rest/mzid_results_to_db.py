import json
import boto3
from boto3.dynamodb.conditions import Key
import os
import uuid
from urllib.parse import unquote_plus
import sys
import traceback
import logging

te_progress_db_name = os.environ["MZID_PROGRESS_DB"]
te_db_name = os.environ["MZID_TE_DB"]

s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
lambda_client = boto3.client('lambda')

te_progress_db = dynamodb.Table(te_progress_db_name)
te_db = dynamodb.Table(te_db_name)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

delete_data_lambda = os.environ["REMOVE_DATA_LAMBDA"]

def lambda_handler(event, context):
    logger.info(f"Event: {event}")
    try:
        for record in event['Records']:
            bucket = record['s3']['bucket']['name']
            key = unquote_plus(record['s3']['object']['key'])
            
            download_path = '/tmp/{}'.format(uuid.uuid4())
            s3_client.download_file(bucket, key, download_path)
            header = s3_client.head_object(Bucket=bucket, Key=key)
            metadata = header['Metadata']
    
            te_progress_db.update_item(
                Key={
                    "user_id": metadata["user_id"],
                    "file_id": key
                },
                UpdateExpression="set stage=:s",
                ExpressionAttributeValues={
                    ':s': "put-items-te_db"
                },
                ReturnValues="UPDATED_NEW"
            )
            
            if metadata["uploadte"] == "Yes":
                private = True
            else:
                private = False
    
            with open(download_path, 'r') as f:
                data = json.load(f)
            
            for item in data:
                
                with te_db.batch_writer() as batch:
                    item["file_id#peptide_id#prot_id"] = "#".join([
                        item["file_id"],
                        item["peptide_id"],
                        item["prot_id"]
                    ])
                    
                    item["gsi_protein"] = "#".join([
                        item["protein"],
                        item["class"],
                        item["prot_id"]
                    ])
    
                    item["gsi_family"] = "#".join([
                        item["tissue"],
                        item["family"],
                        item["class"],
                        item["prot_id"]
                    ])     
                    
                    item["private"] = private
    
                    response = batch.put_item(
                        Item=item
                    )
                    
        #check if process has been deleted by user
        try:
            item = te_progress_db.get_item(Key={
                "user_id": metadata["user_id"],
                "file_id": metadata["file_id"]
            })["Item"]
        except Exception as error:
            logger.info("Item missing in progress table. Active process likely deleted by client.")
            logger.info(error)
            #delete data if process was deleted by client
            lambda_client.invoke_async(
                FunctionName = delete_data_lambda,
                InvokeArgs = {
                    "user_id": metadata["user_id"],
                    "file_id": metadata["file_id"]
                }
            )
            return
                    
        te_progress_db.update_item(
            Key={
                "user_id": metadata["user_id"],
                "file_id": key
            },
            UpdateExpression="set progress=:p",
            ExpressionAttributeValues={
                ':p': "complete"
            },
            ReturnValues="UPDATED_NEW"
        )

    
        return {
            'statusCode': 200,
            'body': None
        }
    except Exception as error:
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
                "user_id": metadata["user_id"],
                "file_id": key
            },            
            UpdateExpression="set progress=:p",
            ExpressionAttributeValues={
                ':p': "failed"
            },
            ReturnValues="UPDATED_NEW"
        )