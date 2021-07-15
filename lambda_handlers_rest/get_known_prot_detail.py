import json
import boto3
import os
import sys
import traceback
import logging

prot_db_name = os.environ["PROT_DB"]

logger = logging.getLogger()
logger.setLevel(logging.INFO)
dynamodb = boto3.resource("dynamodb")
prot_db = dynamodb.Table(prot_db_name)

def lambda_handler(event, context):
    try:
        logger.info(f"Event: {event}")

        protein = event["protein"]
    
        response = prot_db.get_item(
            Key = {"protein": protein}
        )
        
        try:
            body = item = response["Item"]
            status_code = 200
        except:
            body = "InvalidKeyError"
            status_code = 204
        
        logger.info(f'Finished with statusCode: {status_code}')
        return {
            'status_code': status_code,
            'body': body
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
