import boto3
import logging
import sys
import json
import traceback
import uuid
from urllib.parse import unquote_plus
import os
from zipfile import ZipFile

te_progress_db_name = os.environ["MZID_PROGRESS_DB"]
destination_bucket = os.environ["S3_MZID_PARSED"]

s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
te_progress_db = dynamodb.Table(te_progress_db_name)

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    logger.info(event)
    try:
        for record in event['Records']:
            
            bucket = record['s3']['bucket']['name']
            key = unquote_plus(record['s3']['object']['key'])
            tmpkey = key.replace('/', '')
            download_path = '/tmp/{}{}'.format(uuid.uuid4(), tmpkey)
            new_key = tmpkey.split(".")[0]
            
            header = s3_client.head_object(Bucket=bucket, Key=key)
            metadata = header['Metadata']
            metadata["data_location"] = f"s3://{bucket}/{tmpkey}"
            metadata["file_id"] = new_key
            metadata["validated"] = "false"
            
            te_progress_db.put_item(Item={
                "user_id": metadata["user_id"],
                "file_name": metadata["file_name"],
                "file_id": new_key,
                "progress": "active",
                "stage": "parse_mzid",
                "num_peptides": 0
            })
            
            s3_client.download_file(bucket, key, download_path)
            logger.info(f'Downloaded file {key} from s3 bucket {bucket}')

            dic = {}
            with ZipFile(download_path, 'r') as z:
                with z.open(z.namelist()[0], 'r') as f:
                    for row in f:

                        row = row.strip().decode("UTF-8")
        
                        if row.startswith("<Peptide id"):
                            row_tmp = row.split("<Peptide id=\"")[1]
                            
                            peptide_id = row_tmp.split("\"")[0]
                        
                        if row.startswith("<PeptideSequence>"):
                            sequence = row.strip("<PeptideSequence>").strip("</PeptideSequence>")
                            dic[sequence] = peptide_id
                        
                        if row.startswith("<PeptideEvidence"):
                            break
                
            if not len(dic) > 0:
                logger.info("No peptides in file.")
                te_progress_db.update_item(
                    Key={
                        "user_id": metadata["user_id"],
                        "file_id": key
                    },
                    UpdateExpression="set progress=:s",
                    ExpressionAttributeValues={
                        ':s': "complete"
                    },
                    ReturnValues="UPDATED_NEW"
                )
                return

            logger.info(f'{len(dic)} peptides found in file')
            os.remove(download_path)
            parsed_json = json.dumps(dic)

            with open("/tmp/newfile", "w") as newfile:
                newfile.write(parsed_json)

            #check if process has been deleted by user
            try:
                item = te_progress_db.get_item(Key={
                    "user_id": metadata["user_id"],
                    "file_id": metadata["file_id"]
                })["Item"]
            except Exception as error:
                logger.info("Item missing in progress table. Active process likely deleted by client.")
                return

            s3_client.upload_file('/tmp/newfile', destination_bucket, new_key,
                ExtraArgs={'Metadata': metadata}
            )
            logger.info(f'Complete. Saved json file to {destination_bucket}')
            os.remove("/tmp/newfile")
            return
    except Exception as error:
        exception_type, exception_value, exception_traceback = sys.exc_info()
        traceback_string = traceback.format_exception(exception_type, exception_value, exception_traceback)
        err_msg = json.dumps({
            "errorType": exception_type.__name__,
            "errorMessage": str(exception_value),
            "stackTrace": traceback_string
        })
        logger.error(err_msg)

        te_progress_db.update_item(
            Key={"file_id": new_key},
            UpdateExpression="set info.progress=:p",
            ExpressionAttributeValues={
                ':p': "failed"
            },
            ReturnValues="UPDATED_NEW"
        )