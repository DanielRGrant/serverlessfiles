import json
import boto3
import botocore
from boto3.dynamodb.conditions import Key
import os
import logging
import sys
import json
import traceback
import io
import secrets
import urllib.parse
import collections
from operator import itemgetter


logger = logging.getLogger()
logger.setLevel(logging.INFO)

bucket = os.environ["RESULTS_BUCKET"]

s3_client = boto3.client('s3')


def get_metadata(bucket, key):
    resp = s3_client.select_object_content(
        Bucket=bucket,
        Key=key,
        ExpressionType='SQL',
        Expression="SELECT * FROM S3object s where s.\"metadata\" IS NOT MISSING",
        InputSerialization={'JSON': {'Type': 'LINES'}},
        OutputSerialization = {'JSON': {}},
    )

    for event in resp['Payload']:
        if 'Records' in event:
            tmp = event['Records']['Payload'].decode('utf-8')
            metadata = json.loads(tmp)
    return metadata["metadata"]

def lambda_handler(event, context):
    try:
        logger.info(f'Event: {event}')
        
        key = event['key']
        filters = event['filters']
        page = event["page"]
        sort_by = event["sort_by"]
        desc = True if event["desc"].lower() == "true" else False

        tmp = collections.OrderedDict(sorted(filters.items()))
        filters_suffix = urllib.parse.urlencode(tmp)
        is_filters = all(v=="" for v in filters.values())
        query_key = (
            key+"/query" 
            if is_filters
            else f'{key}/query/filters/{filters_suffix}'
        )
        metadata = get_metadata(bucket, query_key)
        seq_type = metadata['seq_type']        
        if not sort_by:
            sort_by = "dna_id" if seq_type == 'DNA' else 'protein'

        pag_key = f'{key}/paginated/filters/{filters_suffix}/sortby/{sort_by}/descending/{desc}'

        resp = s3_client.select_object_content(
            Bucket=bucket,
            Key=pag_key,
            ExpressionType='SQL',
            Expression=f"SELECT * FROM S3object s where s.\"page\" = '{page}'",
            InputSerialization={'JSON': {'Type': 'LINES'}},
            OutputSerialization = {'JSON': {}},
        )

    # extract data from response            
        records = []
        for event in resp['Payload']:
            if 'Records' in event:
                records_tmp = event['Records']['Payload'].decode('utf-8')
                records.append(records_tmp)
        records = ''.join(records)
        records = records.strip('\n')
        records = json.loads(records)
        data = records["data"]
        return {
            "statusCode": 200,
            "body": json.dumps({
                "data": data,
                "key": key,
                "page": page,
                "unique": metadata["unique"],
                "num_pages": metadata["num_pages"],
                "num_items": metadata["num_items"],
                "seq_type": seq_type
            })
        }

    except (ValueError, botocore.exceptions.ClientError) as error:
        return {
            "statusCode": 404,
            "body": None
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
