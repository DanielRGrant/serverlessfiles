import json
import boto3
import os
from datetime import datetime, timedelta
import logging

time_delta = int(os.environ["TIME_DELTA"])

s3_client = boto3.client("s3")

bucket = os.environ["BUCKET"]

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    logger.info(f"Event: {event}")
    try:
        while True:
            objects = s3_client.list_objects(Bucket=bucket)
            to_delete = []
            try:
                for obj in objects["Contents"]:
                    houragotmp = datetime.now() - timedelta(hours=time_delta)
                    hourago = houragotmp.astimezone().isoformat()
                    lastmodtmp = obj["LastModified"]
                    lastmod = lastmodtmp.astimezone().isoformat()
            
                    if hourago > lastmod:
                        key = obj["Key"]
                        to_delete.append({"Key": key})
                logger.info(f"Deleting {len(to_delete)} objects")
                resp = s3_client.delete_objects(
                    Bucket=bucket,
                    Delete={
                        'Objects': to_delete
                    }
                )
            except KeyError:
                pass
            if len(objects) != 1000:
                break

    except Exception as error:
        exception_type, exception_value, exception_traceback = sys.exc_info()
        traceback_string = traceback.format_exception(exception_type, exception_value, exception_traceback)
        err_msg = json.dumps({
            "errorType": exception_type.__name__,
            "errorMessage": str(exception_value),
            "stackTrace": traceback_string
        })
        logger.error(err_msg)