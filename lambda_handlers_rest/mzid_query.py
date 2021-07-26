import boto3
import uuid
from urllib.parse import unquote_plus
import json
import os
import logging
import sys
import traceback
from boto3.dynamodb.conditions import Attr
 
te_progress_db_name = os.environ["MZID_PROGRESS_DB"]
te_parts_complete_db_name = os.environ["MZID_PARTS_COMPLETE_DB"]
query_sequences_s3 = os.environ["QUERY_SEQUENCES"]
results_s3 = os.environ["S3_MZID_QUERY_RESULTS"]
protein_sequences_parquet = os.environ["PROTEIN_SEQUENCES_PARQUET"]

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
te_progress_db = dynamodb.Table(te_progress_db_name)
te_parts_complete_db = dynamodb.Table(te_parts_complete_db_name)


def process_exists(db, user_id, key, logger):
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
            ConditionExpression=Attr("file_id").eq(key)
        )
        return True
    except Exception as error:
        raise(error)
        logger.info("Item missing in progress table. Active process likely deleted by client.")
        return False



def lambda_handler(event, context):
    logger.info(event)    
    try:
        for record in event['Records']:
            inbucket = record['s3']['bucket']['name']
            key = unquote_plus(record['s3']['object']['key'])
            base_key = key.split("/")[0]
            download_path = '/tmp/{}.json'.format(uuid.uuid4())
            header = s3_client.head_object(Bucket=inbucket, Key=key)
            metadata = header['Metadata']
            s3_client.download_file(inbucket, key, download_path)
            logger.info(f'Metadata: {metadata}')

            if not update_item_check_exists(te_progress_db, metadata["user_id"], base_key, "stage", "query-file-sequences", logger):
                return

            f = open(download_path, 'r')
            data = json.load(f)

            logger.info('Beginning querying sequences')
            matches = []
            for seq in data:
                resp = s3_client.select_object_content(
                    Bucket=query_sequences_s3,
                    Key=protein_sequences_parquet,
                    ExpressionType='SQL',
                    Expression="SELECT * FROM S3object s where s.\"prot_seq\" LIKE {}{}{}".format("'%", seq, "%'"),
                    InputSerialization = {'Parquet': {}, 'CompressionType': 'NONE'},
                    OutputSerialization = {'JSON': {}}
                )
    
                for event in resp['Payload']:
                    if 'Records' in event:
                        records = event['Records']['Payload'].decode('utf-8')
                        records = records.split("\n")
    
                        for record in records:
                            try:
                                item = {
                                    "seq_observed": seq,
                                    "peptide_id": data[seq]
                                }                            
                                item = {**item, **json.loads(record), **metadata}
                                
                                matches.append(item)
                            except:
                                pass

        logger.info(f'Number of sequences matched: {len(matches)}')

        if not process_exists(te_progress_db, metadata["user_id"], base_key, logger):
            return

        if matches:
            json_data = json.dumps(matches)
            with open("/tmp/newfile", 'w', newline='\n') as json_file:
                json_file.write(json_data)

            s3_client.upload_file('/tmp/newfile', results_s3, key,
                ExtraArgs={'Metadata': metadata}
            )
            os.remove('/tmp/newfile')

        else:
            logger.info("No matching protein sequences in database")
            if not update_item_check_exists(
                db = te_parts_complete_db,
                user_id = metadata["user_id"],
                key = key,
                attribute = "complete",
                value = "True",
                logger = logger
            ):
                return

        if not update_item_check_exists(te_progress_db, metadata["user_id"], base_key, "num_peptides", len(matches), logger):
            return

        return "complete"
    
    except Exception as error:
        exception_type, exception_value, exception_traceback = sys.exc_info()
        traceback_string = traceback.format_exception(exception_type, exception_value, exception_traceback)
        err_msg = json.dumps({
            "errorType": exception_type.__name__,
            "errorMessage": str(exception_value),
            "stackTrace": traceback_string
        })
        logger.error(err_msg)

        return
        if not update_item_check_exists(te_progress_db, metadata["user_id"], base_key, "progress", "failed", logger):
            return