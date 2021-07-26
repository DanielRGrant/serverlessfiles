import json
import boto3
from boto3.dynamodb.conditions import Key
from boto3.dynamodb.conditions import Attr
import os
import uuid
from urllib.parse import unquote_plus
import sys
import traceback
import logging


te_progress_db_name = os.environ["MZID_PROGRESS_DB"]
te_db_name = os.environ["MZID_TE_DB"]
te_parts_complete_db_name = os.environ["MZID_PARTS_COMPLETE_DB"]
delete_data_lambda = os.environ["REMOVE_DATA_LAMBDA"]

s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
lambda_client = boto3.client('lambda')

te_progress_db = dynamodb.Table(te_progress_db_name)
te_parts_complete_db = dynamodb.Table(te_parts_complete_db_name)
te_db = dynamodb.Table(te_db_name)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def process_exists(user_id, key, logger):
    try:
        item = te_progress_db.get_item(Key={
            "user_id": user_id,
            "file_id": key
        })["Item"]
        return True
    except Exception as error:
        logger.info("Item missing in progress table. Active process likely deleted by client.")
        return False

def update_item_check_exists(db, user_id, key, attribute, value, logger):
    try:
        db.update_item(
            Key={
                "user_id": user_id,
                "file_id": key
            },
            UpdateExpression=f"set {attribute}=:s",
            ExpressionAttributeValues={
                ':s': value
            },
            ReturnValues="UPDATED_NEW",
            ConditionExpression=Attr("user_id").eq(user_id)
        )
        return True
    except Exception as error:
        logger.info("Item missing in progress table. Active process likely deleted by client.")
        return False
        
def check_all_parts_complete(user_id, key, logger):
    items = te_parts_complete_db.query(
        
        KeyConditionExpression=Key('user_id').eq(user_id) & Key('file_id').begins_with(key)
    )["Items"]
    
    if not len(["f" for i in items if not i["complete"] == "True"] ):
        # if no length, all are complete and set progress to complete
        update_item_check_exists(te_progress_db, user_id, key, "progress", "complete", logger)
        logger.info("All parts complete")
    return


def lambda_handler(event, context):
    logger.info(f"Event: {event}")
    try:
        for record in event['Records']:
            bucket = record['s3']['bucket']['name']
            key = unquote_plus(record['s3']['object']['key'])
            base_key = key.split("/")[0]

            download_path = '/tmp/{}'.format(uuid.uuid4())
            s3_client.download_file(bucket, key, download_path)
            header = s3_client.head_object(Bucket=bucket, Key=key)
            metadata = header['Metadata']
    
            if not update_item_check_exists(
                te_progress_db,
                metadata["user_id"], 
                base_key, "stage", 
                "put-items-dynamodb",
                logger
            ):
                return

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
                    
        update_item_check_exists(
            db = te_parts_complete_db,
            user_id = metadata["user_id"],
            key = key,
            attribute = "complete",
            value = "True",
            logger = logger
        )
                    
        #check if process has been deleted by user
        if not process_exists(metadata["user_id"], base_key, logger):
            #delete data if process was deleted by client
            lambda_client.invoke_async(
                FunctionName = delete_data_lambda,
                InvokeArgs = json.dumps({
                    "user_id": metadata["user_id"],
                    "file_id": metadata["file_id"]
                })
            )
            return

        check_all_parts_complete(metadata["user_id"], base_key, logger)

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

        update_item_check_exists(
            te_progress_db, 
            metadata["user_id"], 
            base_key, 
            "progress", 
            "failed",
            logger
        )
        print(error)