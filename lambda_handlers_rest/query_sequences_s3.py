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

def stream_data_to_s3(key, items, bucket):
    buff = io.BytesIO()
    for i in range(len(items)):
        item = items[i]
        tmp = (json.dumps(item)).encode()
        buff.write(tmp)
        if not i == len(items)-1:
            buff.write("\n".encode())

    s3_res.Object(results_bucket, key).put(Body=buff.getvalue())
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

def s3_select(bucket, key, sql):
    resp = s3_client.select_object_content(
        Bucket=bucket,
        Key=key,
        ExpressionType='SQL',
        Expression=sql,
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
            pass
    return items

def lambda_handler(event, context):
    try:
        logger.info(f'Event: {event}')
        key = secrets.token_urlsafe(16)
        logger.info(f'Key: {key}')
        seq = event["query"]
        seq_type = event["sequenceType"]
        sort_by = "dna_id" if seq_type == "dna" else "protein"
        filters = "class=&family=&protein="
        
        query_key = key + "/query"
        pag_key = f'{key}/paginated/filters/{filters}/sortby/{sort_by}/descending/False'
        print(query_key)
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
        sql = f"SELECT * FROM S3object s where s.\"{sequence_header}\" LIKE '%{seq}%'"
        items = s3_select(sequences_bucket, sequences_key, sql)

        if len(items):
            sorted_items = sorted(items, key=itemgetter(sort_by))
            tmp = paginate(sorted_items, n=100)
            paginated = [{"page": str(i+1), "data": tmp[i]} for i in range(0, len(tmp))]

            unique = get_unique(data=items, keys=["class", "family", "protein"])
            metadata={
                "num_items": str(len(items)),
                "num_pages": str(len(paginated)),
                "seq_type": "DNA" if seq_type == "dna" else "Protein",
                "unique": unique
            }
            stream_data_to_s3(
                key=pag_key,
                items=paginated+[{"metadata": metadata}],
                bucket=results_bucket
            )
            stream_data_to_s3(
                key=query_key,
                items=items+[{"metadata": metadata}],
                bucket=results_bucket
            )
            data = paginated[0]["data"]
            pages = len(paginated)

        else:
            data = []
            pages = 0
            unique= {}    
            
        seq_type = "DNA" if seq_type == "dna" else "Protein"

        return {
            "statusCode": 200,
            "body": json.dumps({
                "data": data,
                "key": key,
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
