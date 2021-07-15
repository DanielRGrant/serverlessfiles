import json
import boto3
from boto3.dynamodb.conditions import Key
import os
import sys
import traceback
import logging

query_db_name = os.environ["QUERY_DB"]

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
query_db = dynamodb.Table(query_db_name)

def lambda_handler(event, context):
    try:
        logger.info(f'Event: {event}')

        family = event["family"]
        response = query_db.query(
            IndexName="family-index",
            KeyConditionExpression=Key('family').eq(family)
        )
    
    
        if response["Items"]:
            body = response["Items"]
            status_code=200
        else:
            body="InvalidKeyError"
            status_code=204
            
            logger.info(f'Finished with status code: {status_code}')
        
        return {
            "status_code": status_code,
            "body": body
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
    