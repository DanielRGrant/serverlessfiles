import json
import boto3
from boto3.dynamodb.conditions import Key
import os
import logging
import sys
import traceback

te_db_name = os.environ["MZID_TE_DB"]

dynamodb = boto3.resource("dynamodb")
te_db = dynamodb.Table(te_db_name)
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    logger.info(f'Event: {event}')
    try:
        file_id = event["file_id"]
        
        items = te_db.query(
            IndexName="file_id-index",
            KeyConditionExpression=Key("file_id").eq(file_id)
        )["Items"]
        
        return {
            'statusCode': 200,
            'body': items
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