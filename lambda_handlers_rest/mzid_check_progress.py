import json
import boto3
import os
import logging
import sys
import traceback
from boto3.dynamodb.conditions import Key
from boto3.dynamodb.conditions import Attr


te_progress_db_name = os.environ["MZID_PROGRESS_DB"]
te_parts_complete_db_name = os.environ["MZID_PARTS_COMPLETE_DB"]

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")

te_progress_db = dynamodb.Table(te_progress_db_name)
te_parts_complete_db = dynamodb.Table(te_parts_complete_db_name)

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
        print(error)
        logger.info("Item missing in progress table. Active process likely deleted by client.")
        return False

def update_if_active_is_complete(item, user_id):
    if item["progress"] == "active":
        key = item["file_id"]
        items = te_parts_complete_db.query(
            KeyConditionExpression=Key('user_id').eq(user_id) & Key('file_id').begins_with(key)
        )["Items"]
        print(user_id, key)
        if not len(["f" for i in items if not i["complete"] == "True"] ):
            # if no length, all are complete and set progress to complete
            update_item_check_exists(te_progress_db, user_id, key, "progress", "complete", logger)
            logger.info(f"Updated {key} to complete")
            return True
    return False


def lambda_handler(event, context):
    try:
        logger.info(f'Event: {event}')

        user_id = event["user_id"]

        items = te_progress_db.query(
            IndexName = "user_id-index",
            KeyConditionExpression = Key("user_id").eq(user_id)

        )["Items"]

        for i in range(len(items)):
            if update_if_active_is_complete(items[i], user_id):
                items[i]["progress"] = "complete"

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