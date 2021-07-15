import boto3
import uuid
from urllib.parse import unquote_plus
import json
import os
import csv
import logging
import traceback
import sys

logger = logging.getLogger()
logger.setLevel(logging.INFO)

query_db = os.environ["QUERY_DB"]

s3_client = boto3.client('s3')
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(query_db)


def lambda_handler(event, context):
    logger.info(f'Event: {event}')
    try:
        for record in event['Records']:
            bucket = record['s3']['bucket']['name']
            key = unquote_plus(record['s3']['object']['key'])
            download_path = '/tmp/{}.json'.format(uuid.uuid4())
            s3_client.download_file(bucket, key, download_path)

            logger.info(f'Key: {key}')

            f = open(download_path, 'r')
            data = json.load(f)
            
            dna_ids = list( data.keys() )

            di_batches = [dna_ids[i:i+25] for i in range(0, len(dna_ids), 25)]

            logger.info(f"uploading {len(dna_ids)} dna records")
            for di_batch in di_batches:
                with table.batch_writer() as batch:
                    for dna_id in di_batch:
                        item = {}
                        item_data = data[dna_id]
                        item["dna_id"] = dna_id
                        item["coords"] = item_data["coords"]
                        item["dna_seq"] = item_data["dna_seq"]
                        item["class"] = item_data["superfam"]
                        item["family"] = item_data["family"]
                        item["dna_id"] = dna_id.lower()
                        item["fam_lc"] = item_data["family"].lower()
                        if item_data["protdata"]:
                            prot_data = item_data["protdata"]
                            prot_ids = list( prot_data.keys() )
                            
                            for prot_id in prot_ids:
                                for protein in prot_data[prot_id]:
                                    item["prot_id"] = prot_id
                                    item["prot_id_lc"] = prot_id.lower()
                                    item["prot_seq"] = protein["pep_seq"]
                                    try:
                                        item["protein"] = "#".join( item["protein"], protein["protname"] )
                                        item["protein"] = "#".join( item["protein"], protein["protname"].lower() )
                                    except:
                                        item["protein"] = protein["protname"]
                                        item["protein_lc"] = protein["protname"].lower()
                    
                                batch.put_item(
                                    Item=item
                                )
                        else:
                            item["prot_id"] = "null"
                            table.put_item(
                                Item=item
                            )

        logger.info("complete")
    
    except:
        exception_type, exception_value, exception_traceback = sys.exc_info()
        traceback_string = traceback.format_exception(exception_type, exception_value, exception_traceback)
        err_msg = json.dumps({
            "errorType": exception_type.__name__,
            "errorMessage": str(exception_value),
            "stackTrace": traceback_string
        })
        logger.error(err_msg)