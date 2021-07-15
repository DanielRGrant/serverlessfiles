import json
import boto3
from boto3.dynamodb.conditions import Key
import os
import logging
import traceback
import sys

class_db_name = os.environ["CLASS_DB"]

logger = logging.getLogger()
logger.setLevel(logging.INFO)


dynamodb = boto3.resource("dynamodb")
class_db = dynamodb.Table(class_db_name)

def lambda_handler(event, context):
    try:
        logger.info(f'Event: {event}')
        rtclass = event["class"]
        item = class_db.query(
            KeyConditionExpression=Key("class").eq(rtclass)    
        )["Items"][0]
        
        return {
            'statusCode': 200,
            'body': item
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