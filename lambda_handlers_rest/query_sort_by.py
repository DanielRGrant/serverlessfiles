import json
import boto3
import botocore
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
import uuid


logger = logging.getLogger()
logger.setLevel(logging.INFO)

bucket = os.environ["RESULTS_BUCKET"]

s3_client = boto3.client('s3')
s3_res = boto3.resource("s3")

def paginate(mylist, n):
    if n>=len(mylist):
        return mylist
    return [mylist[i:i+n] for i in range(0, len(mylist), n)]
    
def stream_data_to_s3(key, items, bucket):
    buff = io.BytesIO()
    for i in range(len(items)):
        item = items[i]
        tmp = (json.dumps(item)).encode()
        buff.write(tmp)
        if not i == len(items)-1:
            buff.write("\n".encode())

    s3_res.Object(bucket, key).put(Body=buff.getvalue())
    return

def lambda_handler(event, context):
    try:
        logger.info(f'Event: {event}')
        
        key = event['key']
        filters = event['filters']
        page = event['page']
        sort_by = event["sort_by"]
        query_key = event['key'] + "/query"


        if filters:
            tmp = collections.OrderedDict(sorted(filters.items()))
            filters_suffix = urllib.parse.urlencode(tmp)
            sorted_key = f"{key}/paginated/{filters_suffix}/sorted/{sort_by}"
            unsorted_key = f"{key}/query/{filters_suffix}"
        else:
            sorted_key = f"{key}/paginated/sorted/{sort_by}"
            unsorted_key = f"{key}/query"
            
        try:
            #if sorted response exists, return page data
            resp = s3_client.select_object_content(
                Bucket=bucket,
                Key=sorted_key,
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
            
            logger.info('Sorted result already exists. Returning page data.')
            return {
                "statusCode": 200,
                "body": json.dumps({
                    "data": data,
                    "key": key,
                    "page": page
                })
            }
        except ValueError as error:
            #if sorted response doesn't exist, check if unsorted response exists
            try:
                s3_res.Object(bucket, unsorted_key).load()
            except Exception as error:
                raise(error)
                return {
                    "statusCode": "404",
                    "body": None
                }
        except Exception as error:
            pass
        obj = s3_client.get_object(Bucket=bucket, Key=unsorted_key)
        items_str = obj['Body'].read().decode('utf-8')
        items = []
        for item_str in items_str.split("\n"):
            items.append(json.loads(item_str))
        
        try:
            if len(items):
                sorted_items = sorted(items, key=itemgetter(sort_by))
                tmp = paginate(sorted_items, n=100)
                paginated = [{"page": str(i), "data": tmp[i]} for i in range(0, len(tmp))]
        except KeyError as error:
            return {
                "statusCode": 400,
                "body": None
            }
        except Exception as error:
            raise(error)

        stream_data_to_s3(
            key=f'{key}/paginated/{filters_suffix}/sorted/{sort_by}',
            items=paginated,
            bucket=bucket
        )

        return {
            "statusCode": 200,
            "body": json.dumps({
                "data": paginated[0]["data"],
                "key": key,
                "page": "1"
            })
        }


    except botocore.exceptions.ClientError as error:
        #raise(error)
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
