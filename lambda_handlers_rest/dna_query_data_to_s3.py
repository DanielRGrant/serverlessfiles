import json
import os
import boto3
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from botocore.client import Config
import logging
import sys
import traceback

logger = logging.getLogger()
logger.setLevel(logging.INFO)

query_db_name = os.environ["QUERY_DB"]
key = os.environ["DNA_SEQUENCES_PARQUET"]
bucket = os.environ["QUERY_SEQUENCES"]

dynamodb = boto3.resource("dynamodb")
query_db = dynamodb.Table(query_db_name)
config = Config(connect_timeout=5, retries={'max_attempts': 0})
s3_client = boto3.client('s3', config=config)
tmpkey = "/tmp/file.parquet"

def lambda_handler(event, context):
    logging.info(f'Event: {event}')
    try:
        items = query_db.scan(
            AttributesToGet=[
                "dna_id", "class", "family", "prot_id", "protein", "coords", "dna_seq"
            ]
        )["Items"]
        
        all_prot_per_rec = {}
        data = []
        for i in range(len(items)):
            item = items[i]
        
            if item["prot_id"] == "null":
                item["protein"] = "None"
            data.append( item )        
                
            # collect all proteins for dna record for one field. 
            # Will be used for filtering on front end.
            dna_id = item["dna_id"]
            try:
                proteins = item["protein"].split("#")
                for p in proteins:
                    
                    if not p in all_prot_per_rec[ dna_id ]:
                        all_prot_per_rec[ dna_id ] += "#" + p

            except Exception as e:
                all_prot_per_rec[ dna_id ] = item[ "protein" ]



        for i in range(len(data)):
            record = data[i]
            dna_id = record["dna_id"]
            try:
                record[ "all_rec_prots" ] = all_prot_per_rec[ dna_id ]
                data[i] = record
                
            except:
                pass

        df = pd.DataFrame(data)
        
        parquet_schema = pa.Table.from_pandas(df=df).schema
        parquet_writer = pq.ParquetWriter(tmpkey, parquet_schema, compression='snappy')
        table = pa.Table.from_pandas(df, schema=parquet_schema)
        parquet_writer.write_table(table)
        
        parquet_writer.close()



        logging.info("uploading dna data to s3")
        s3_client.upload_file(tmpkey, bucket, key)

        os.remove(tmpkey)

        return {
            'statusCode': 200
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
