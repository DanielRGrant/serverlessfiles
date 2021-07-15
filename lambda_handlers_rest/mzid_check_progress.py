import json
import boto3
import os
import logging
import sys
import traceback
from boto3.dynamodb.conditions import Key

te_progress_db_name = os.environ["MZID_PROGRESS_DB"]

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")

te_progress_db = dynamodb.Table(te_progress_db_name)


def lambda_handler(event, context):
    try:
        logger.info(f'Event: {event}')

        user_id = event["user_id"]
        
        items = te_progress_db.query(
            IndexName = "user_id-index",
            KeyConditionExpression = Key("user_id").eq(user_id)
            
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