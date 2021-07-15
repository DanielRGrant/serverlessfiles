import json
import boto3
from boto3.dynamodb.conditions import Key
import os
import logging
import sys
import json
import traceback
import io
import secrets
from operator import itemgetter


logger = logging.getLogger()
logger.setLevel(logging.INFO)

sequences_bucket = os.environ["QUERY_SEQUENCES"]
results_bucket = os.environ["RESULTS_BUCKET"]

s3_client = boto3.client('s3')
s3_res = boto3.resource("s3")

new_key = secrets.token_urlsafe(16)

def stream_data_to_s3(key, items, bucket, metadata):
    buff = io.BytesIO()
    for i in range(len(items)):
        item = items[i]
        tmp = (json.dumps(item)).encode()
        buff.write(tmp)
        if not i == len(items)-1:
            buff.write("\n".encode())

    s3_res.Object(results_bucket, key).put(Body=buff.getvalue(), Metadata=metadata)
    return

def paginate(mylist, n):
    if n>=len(mylist):
        return [mylist]
    return [mylist[i:i+n] for i in range(0, len(mylist), n)]
    
def get_unique(data, keys):
    unique = {k:[] for k in keys}
    for item in data:
        for k in keys:
            if k == "protein":
                prot = item[k].split("#")
                for p in prot:
                    if not p in unique[k]:
                        unique[k].append(p)
            if not item[k] in unique[k]:
                unique[k].append(item[k])
    return unique

def lambda_handler(event, context):
    try:
        logger.info(f'Event: {event}')
        
        seq = event["query"]
        seq_type = event["sequenceType"]

        if event["sequenceType"] == "dna":
            sequences_key = os.environ["DNA_SEQUENCES_PARQUET"]
        elif event["sequenceType"] == "protein":
            sequences_key = os.environ["PROTEIN_SEQUENCES_PARQUET"]
        else:
            return {
                "statusCode": 400,
                "message": "Missing sequenceType parameter"
            }

        logger.info(f'Beginning querying sequence...')

        sequence_header = "prot_seq" if seq_type == "protein" else "dna_seq" # header in parquet

        resp = s3_client.select_object_content(
            Bucket=sequences_bucket,
            Key=sequences_key,
            ExpressionType='SQL',
            Expression=f"SELECT * FROM S3object s where s.\"{sequence_header}\" LIKE '%{seq}%'",
            InputSerialization={'Parquet': {}},
            OutputSerialization = {'JSON': {}},
        )

    # extract data from response            
        records = []
        for event in resp['Payload']:
            if 'Records' in event:
                records_tmp = event['Records']['Payload'].decode('utf-8')
                records.append(records_tmp)
        records = ''.join(records)
        records = records.split('\n')
        items = []
        for record in records:
            try:
                item = json.loads(record)
                items.append(item)
            except:
                logger.info("Following record not json (okay if empty): ")
        
        if len(items):
            sorted_items = sorted(items, key=itemgetter('dna_id'))
            tmp = paginate(sorted_items, n=100)
            paginated = [{"page": str(i+1), "data": tmp[i]} for i in range(0, len(tmp))]

            unique = get_unique(data=items, keys=["class", "family", "protein"])
            metadata={
                "num_items": str(len(items)),
                "num_pages": str(len(paginated)),
                "seq_type": "DNA" if seq_type == "dna" else "Protein"
            }
            stream_data_to_s3(
                key=new_key+"/paginated",
                items=paginated+[{"uniquevals": unique}],
                bucket=results_bucket,
                metadata=metadata
            )
            stream_data_to_s3(
                key=new_key+"/query",
                items=items+[{"uniquevals": unique}],
                bucket=results_bucket,
                metadata=metadata
            )
            data = paginated[0]["data"]
            pages = len(paginated)

        else:
            data = []
            pages = 0
            unique={}
            
        seq_type = "DNA" if seq_type == "dna" else "Protein"

        return {
            "statusCode": 200,
            "body": json.dumps({
                "data": data,
                "key": new_key,
                "page": "1",
                "unique": unique,
                "num_pages": pages,
                "num_items": len(items),
                "seq_type": seq_type
            })
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
