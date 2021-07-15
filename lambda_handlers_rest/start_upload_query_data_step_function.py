import json
import traceback
import sys
import os
import logging
import boto3
import uuid
from urllib.parse import unquote_plus

state_machine_arn = os.environ["STATE_MACHINE_ARN"]

stepfunctions = boto3.client('stepfunctions')
s3 = boto3.client('s3')

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    logging.info(f'Event: {event}')
    try:
        execution_name = str( uuid.uuid4() )

        response = stepfunctions.start_execution(
            stateMachineArn=state_machine_arn,
            name=execution_name
        )

        logger.info(f'State machine execution response: {response}')

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
