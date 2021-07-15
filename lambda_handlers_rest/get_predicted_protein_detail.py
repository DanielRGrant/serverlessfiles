import json
import boto3
from boto3.dynamodb.conditions import Key
import os
import sys
import traceback
import logging

query_table_name = os.environ["QUERY_DB"]
prot_table_name = os.environ["PROT_DB"]

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
query_db = dynamodb.Table(query_table_name)
prot_db = dynamodb.Table(prot_table_name)

def lambda_handler(event, context):
    try:
        logger.info(f'Event: {event}')
        prot_id = event["prot_id"]
    
        response = query_db.query(
            IndexName="prot_id-index",
            KeyConditionExpression=Key('prot_id').eq(prot_id)
        )
        try:
            pred_prot = response["Items"][0]
            proteins = pred_prot["protein"].split("#")
    
            known_prot = []
            for protein in proteins:
                response = prot_db.get_item(
                    Key={"protein": protein}
                )
                known_prot.append(response["Item"])
        
            pred_prot["known_prot"] = known_prot
            
            status_code = 200
            body = pred_prot
            
        except KeyError:
            status_code = 204
            body = "InvalidKeyError"
        except Exception as error:
            raise error
        
        logger.info(f'Finished with statusCode: {status_code}')    
        
        return {
            'status_code': 200,
            'body': pred_prot
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
        
    

    
    
        