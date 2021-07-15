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


def get_unique(bucket, key):
    resp = s3_client.select_object_content(
        Bucket=bucket,
        Key=key,
        ExpressionType='SQL',
        Expression="SELECT * FROM S3object s where s.\"uniquevals\" IS NOT MISSING",
        InputSerialization={'JSON': {'Type': 'LINES'}},
        OutputSerialization = {'JSON': {}},
    )

    for event in resp['Payload']:
        if 'Records' in event:
            tmp = event['Records']['Payload'].decode('utf-8')
            unique = json.loads(tmp)
    return unique["uniquevals"]

def lambda_handler(event, context):
    try:
        logger.info(f'Event: {event}')
        
        key = event['key']
        filters = event['filters']
        page = event["page"]


        #check if a filter value is submitted
        isfilters = False
        for f in filters:
            if filters[f]:
                isfilters = True
        if isfilters:
            tmp = collections.OrderedDict(sorted(filters.items()))
            filters_suffix = urllib.parse.urlencode(tmp)
            pag_key = key + "/paginated/" + filters_suffix
            
        else:
            pag_key = key + "/paginated"

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
        logger.info(len(records))
        records = ''.join(records)
        records = records.strip('\n')
        logger.info(records)
        records = json.loads(records)
        data = records["data"]

        unique = get_unique(bucket, pag_key)
        
        metadata = s3_client.head_object(Bucket=bucket, Key=pag_key)['Metadata']
        num_pages = metadata["num_pages"]
        num_items = metadata["num_items"]
        seq_type = metadata["seq_type"]
        
        return {
            "statusCode": 200,
            "body": json.dumps({
                "data": data,
                "key": key,
                "page": page,
                "unique": unique,
                "num_pages": num_pages,
                "num_items": num_items,
                "seq_type": seq_type
            })
        }

    except (ValueError, botocore.exceptions.ClientError) as error:
        raise(error)
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
