import boto3
from boto3.dynamodb.conditions import Attr
import logging
import sys
import json
import traceback
import uuid
from urllib.parse import unquote_plus
import os
from zipfile import ZipFile
import gzip
import shutil
from datetime import datetime


te_progress_db_name = os.environ["MZID_PROGRESS_DB"]
destination_bucket = os.environ["S3_MZID_PARSED"]
te_parts_complete_db_name = os.environ["MZID_PARTS_COMPLETE_DB"]
items_per_page = int(os.environ["ITEMS_PER_PAGE"])

s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
te_progress_db = dynamodb.Table(te_progress_db_name)
te_parts_complete_db = dynamodb.Table(te_parts_complete_db_name)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def get_file_extension(file_name):
    fn = file_name.split(".")
    return fn[len(fn) - 1]
    
def paginate_dic(dic, items_per_page):
    items = list(dic.items())
    return [dict(items[i:i+350]) for i in range(0, len(items), 350)]

def parse_mzid(f):
    dic = {}
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
    return dic

def parse_zip(download_path):
    dic = {}
    with ZipFile(download_path, 'r') as z:
        with z.open(z.namelist()[0], 'r') as f:
            return parse_mzid(f)

def parse_gz(download_path):
    with gzip.open(download_path, 'rb') as f:
        return parse_mzid(f)
        
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
    
def update_progress(user_id, key, attribute, value, logger):
    try:
        te_progress_db.update_item(
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
        raise(error)
        logger.info("Item missing in progress table. Active process likely deleted by client.")
        return False

    

def lambda_handler(event, context):
    logger.info(event)
    try:
        submitted = datetime.today().strftime('%Y-%m-%d %H:%M:%S')
        for record in event['Records']:
            bucket = record['s3']['bucket']['name']
            key = unquote_plus(record['s3']['object']['key'])
            download_path = '/tmp/{}{}'.format(uuid.uuid4(), key)

            header = s3_client.head_object(Bucket=bucket, Key=key)
            metadata = header['Metadata']
            print(metadata)
            metadata["data_location"] = f"s3://{bucket}/{key}"
            metadata["file_id"] = key
            metadata["validated"] = "false"
            
            te_progress_db.put_item(Item={
                "user_id": metadata["user_id"],
                "file_name": metadata["file_name"],
                "file_id": key,
                "progress": "active",
                "stage": "parse_mzid",
                "num_peptides": 0,
                "submitted": submitted
            })

            s3_client.download_file(bucket, key, download_path)
            logger.info(f'Downloaded file {key} from s3 bucket {bucket}')

            extension = get_file_extension(metadata["file_name"])
            if extension == "zip":
                dic = parse_gz(download_path)
            elif extension == "gz":
                dic = parse_gz(download_path)
            else:
                logger.error("File is not gz or zip")
                update_progress(metadata["user_id"], key, "progress", "failed", logger)
                os.remove(download_path)
                return
            os.remove(download_path)
            logger.info(f'{len(dic)} peptides found in file')
            
            if not len(dic) > 0:
                logger.info("No peptides in file.")
                update_progress(metdata["user_id"], key, "progress", "complete", logger)
                return
            
            if len(dic) > items_per_page:
                pages = paginate_dic(dic, items_per_page=items_per_page)
            else:
                pages = [dic]

            #check if process has been deleted by user
            if not process_exists(metadata["user_id"], key, logger):
                return
            
            for i in range(len(pages)):
                page = pages[i]
                parsed_json = json.dumps(page)
                with open("/tmp/newfile", "w") as newfile:
                    newfile.write(parsed_json)
                new_key = f'{key}/{i}/{len(pages)}'
                s3_client.upload_file('/tmp/newfile', destination_bucket, new_key,
                    ExtraArgs={'Metadata': metadata}
                )
                os.remove("/tmp/newfile")
                te_parts_complete_db.put_item(Item={
                    "user_id": metadata["user_id"],
                    "file_id": new_key,
                    "complete": "False",
                    "total_pages": len(pages),
                    "page": i
                })
            logger.info(f'Complete. Saved json files to {destination_bucket}')
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

        update_progress(metadata["user_id"], key, "progress", "failed", logger)