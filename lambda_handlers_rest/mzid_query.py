import boto3
import uuid
from urllib.parse import unquote_plus
import json
import os
import logging
import sys
import traceback
 
te_progress_db_name = os.environ["MZID_PROGRESS_DB"]
query_sequences_s3 = os.environ["QUERY_SEQUENCES"]
results_s3 = os.environ["S3_MZID_QUERY_RESULTS"]
protein_sequences_parquet = os.environ["PROTEIN_SEQUENCES_PARQUET"]

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
te_progress_db = dynamodb.Table(te_progress_db_name)


def lambda_handler(event, context):
    logger.info(event)    
    try:
        for record in event['Records']:
            inbucket = record['s3']['bucket']['name']
            key = unquote_plus(record['s3']['object']['key'])
    
            tmpkey = key.replace('/', '')
            download_path = '/tmp/{}.json'.format(uuid.uuid4())
            
            header = s3_client.head_object(Bucket=inbucket, Key=key)
            metadata = header['Metadata']
            s3_client.download_file(inbucket, key, download_path)
            logger.info(f'Metadata: {metadata}')

            te_progress_db.update_item(
                Key={
                    "user_id": metadata["user_id"],
                    "file_id": key
                },
                UpdateExpression="set stage=:s",
                ExpressionAttributeValues={
                    ':s': "query-file-sequences"
                },
                ReturnValues="UPDATED_NEW"
            )
    
            f = open(download_path, 'r')
            data = json.load(f)
    
            sequences = list(data.keys())
            print('Beginning querying sequences')
            matches = []
            for seq in sequences:
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
        
        #check if process has been deleted by user
        try:
            item = te_progress_db.get_item(Key={
                "user_id": metadata["user_id"],
                "file_id": key
            })["Item"]
        except Exception as error:
            logger.info("Item missing in progress table. Active process likely deleted by client.")
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

        te_progress_db.update_item(
            Key={
                "user_id": metadata["user_id"],
                "file_id": key
            },
            UpdateExpression="set num_peptides=:n",
            ExpressionAttributeValues={
                ':n': len(matches)
            },
            ReturnValues="UPDATED_NEW"
        )

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

        te_progress_db.update_item(
            Key={
                "user_id": metadata["user_id"],
                "file_id": key
            },
            UpdateExpression="set progress=:p",
            ExpressionAttributeValues={
                ':p': "failed"
            },
            ReturnValues="UPDATED_NEW"
        )