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
        return [mylist]
    return [mylist[i:i+n] for i in range(0, len(mylist), n)]
    
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
            tmpstr = json.loads(tmp)
    return tmpstr["metadata"]
    
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
        sort_by = event['sort_by']
        query_key = event['key'] + "/query"
        desc = True if event["desc"].lower() == "true" else False
        is_filters = all(v=="" for v in filters.values())
        tmp = collections.OrderedDict(sorted(filters.items()))
        filters_suffix = urllib.parse.urlencode(tmp)
        metadata = get_metadata(bucket, query_key)
        seq_type = "DNA" if metadata["seq_type"].lower() == "dna" else "Protein"
 
        query_key = (
            key + '/query' if is_filters 
            else f"{key}/query/filters/{filters_suffix}"
        )
        sorted_key = f"{key}/paginated/filters/{filters_suffix}/sortby/{sort_by}/descending/{desc}"
        try:
            #if sorted response exists, return page data
            resp = s3_client.select_object_content(
                Bucket=bucket,
                Key=sorted_key,
                ExpressionType='SQL',
                Expression=f"SELECT * FROM S3object s where s.\"page\" = '1'",
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
                    "page": "1",
                    "filters": filters,
                    "unique": metadata["unique"],
                    "num_pages": metadata["num_pages"],
                    "num_items": metadata["num_items"],
                    "seq_type": metadata["seq_type"]
                })
            }
            
        except ValueError as error:
            #if sorted response doesn't exist, check if unsorted response exists
            try:
                s3_res.Object(bucket, query_key).load()
            except Exception as error:
                return {
                    "statusCode": "404",
                    "body": None
                }
        except Exception as error:
            pass
        obj = s3_client.get_object(Bucket=bucket, Key=query_key)
        items_str = obj['Body'].read().decode('utf-8')
        items = []
        for item_str in items_str.split("\n"):
            item = json.loads(item_str)
            if 'dna_id' in item.keys():
                items.append(item)

        try:
            if len(items):
                sorted_items = sorted(items, key=itemgetter(sort_by), reverse=(not desc))
                tmp = paginate(sorted_items, n=100)
                paginated = [{"page": str(i+1), "data": tmp[i]} for i in range(0, len(tmp))]

        except KeyError as error:
            return {
                "statusCode": 400,
                "body": None
            }
        except Exception as error:
            raise(error)

        stream_data_to_s3(
            key=sorted_key,
            items=paginated,
            bucket=bucket
        )
        return {
            "statusCode": 200,
            "body": json.dumps({
                "data": paginated[0]["data"],
                "key": key,
                "page": "1",
                "filters": filters,
                "unique": metadata["unique"],
                "num_pages": len(paginated),
                "num_items": metadata["num_items"],
                "seq_type": metadata["seq_type"]
            })
        }


    except botocore.exceptions.ClientError as error:
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
        return {
            "statusCode": 400,
            "body": None
        }