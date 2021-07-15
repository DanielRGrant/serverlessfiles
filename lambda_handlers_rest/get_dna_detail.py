import json
import boto3
from boto3.dynamodb.conditions import Key
import os
import logging
import traceback
import sys

query_table_name = os.environ["QUERY_DB"]

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
query_db = dynamodb.Table(query_table_name)

def lambda_handler(event, context):
    try:
        logger.info(f'Event: {event}')
        dna_id = event["dna_id"]
    
        response = query_db.query(
            KeyConditionExpression=Key('dna_id').eq(dna_id)
        )
        
        items = response["Items"]
        protein_data = []
        for item in items:
            if (item["prot_id"] != "null"):
                protein_data.append(
                    {
                        "prot_id": item["prot_id"],
                        "protein": item["protein"],
                        "prot_seq": item["prot_seq"]
                    }
                )
    
        try:
            body = items[0]
            body["protein_data"] = protein_data
            status_code = 200
        except:
            status_code = 204
            body = "InvalidKeyError"

        logger.info(f'Finished with statusCode: {status_code}')

        return {
            'status_code': status_code,
            'body': body
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