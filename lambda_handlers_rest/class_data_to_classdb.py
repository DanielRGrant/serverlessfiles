import json
import boto3
from boto3.dynamodb.conditions import Key
import os
import sys
import logging
import traceback

logger = logging.getLogger()
logger.setLevel(logging.INFO)

query_db_name = os.environ["QUERY_DB"]
class_db_name = os.environ["CLASS_DB"]

dynamodb = boto3.resource('dynamodb')
query_db = dynamodb.Table(query_db_name)
class_db = dynamodb.Table(class_db_name)

def lambda_handler(event, context):
    try:
        logger.info(f'Event: {event}')
        logger.info(f'Taking records from query database: {query_db_name}')
        logger.info(f'Inserting class data in database: {class_db_name}')

        rtClass = event["class"]
        response = query_db.query(
            IndexName="class-index",
            KeyConditionExpression=Key('class').eq(rtClass)
        )

        items = response["Items"]
        
        families = []
        proteins = []
        for item in items:
            if not item["family"] in families:
                families.append(item["family"])
            
            if item["prot_id"] == "null":
                continue
            
            protein = item["protein"].split("#")
            for prot in protein:
                if not prot in proteins:            
                    proteins.append(prot)
                    
        families = sorted(families, key=lambda item: (int(item.partition(' ')[0])
                                if item[0].isdigit() else float('inf'), item))
        proteins = sorted(proteins, key=lambda item: (int(item.partition(' ')[0])
                                if item[0].isdigit() else float('inf'), item))
                                
        families = "#".join(families)
        proteins = "#".join(proteins)
        
        item = {
                "class": rtClass,
                "proteins": proteins,
                "families": families
            }
        logger.info(f"Putting item to class_db: {item}")
        class_db.put_item(
            Item=item
        )
        
        return {
            'statusCode': 200,
            'body': "complete"
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
