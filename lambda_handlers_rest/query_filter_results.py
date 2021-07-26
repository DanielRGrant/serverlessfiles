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
            metadata = json.loads(tmp)
    return metadata["metadata"]
    

    
def stream_data_to_s3(key, items, bucket, ):
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
        page = "1"
        tmp = collections.OrderedDict(sorted(filters.items()))
        filters_suffix = urllib.parse.urlencode(tmp)
        query_key = key + "/query"
        metadata = get_metadata(bucket, query_key)
        seq_type = metadata['seq_type']
        sort_by = "dna_id" if seq_type == 'DNA' else 'protein'
        pag_key = f'{key}/paginated/filters/{filters_suffix}/sortby/{sort_by}/descending/False'
        filt_query_key = f'{key}/query/filters/{filters_suffix}'
        try:
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
            metadata = get_metadata(bucket, filt_query_key)


            logger.info('Result already exists. Returning page data.')
            return {
                "statusCode": 200,
                "body": json.dumps({
                    "data": data,
                    "key": key,
                    "page": page,
                    "unique": metadata["unique"],
                    "filters": filters,
                    "num_pages": metadata["num_pages"],
                    "num_items": metadata["num_items"],
                    "seq_type": seq_type
                })
            }
        except ValueError as error:
            return {
                "statusCode": 404,
                "body": None
            }
        except Exception as error:
            pass
        
        family = filters.get("family", 0)
        protein = filters.get("protein", 0)
        rtclass = filters.get("class", 0)
        prot_id = filters.get("prot_id", 0)
        dna_id = filters.get("dna_id", 0)
        

        family_sql = f"s.\"family\" = '{family}'" if family else ""

        protein_sql = f"(s.\"protein\" LIKE '%#{protein}' OR s.\"protein\" = '{protein}' OR s.\"protein\" = '{protein}#%')" if protein else ""

        rtclass_sql = f"s.\"class\" = '{rtclass}'" if rtclass else ""

        prot_id_sql = f"s.\"prot_id\" = '{prot_id}'" if prot_id else ""

        dna_id_sql = f"s.\"dna_id\" = '{dna_id}'" if dna_id else ""

        conditions_tmp = [family_sql, protein_sql, rtclass_sql, prot_id_sql, dna_id_sql]
        conditions_tmp = [val for val in conditions_tmp if val]
        conditions = " AND ".join(conditions_tmp)
        resp = s3_client.select_object_content(
            Bucket=bucket,
            Key=query_key,
            ExpressionType='SQL',
            Expression=f"SELECT * FROM S3object s WHERE " + conditions,
            InputSerialization={'JSON': {'Type': 'LINES'}},
            OutputSerialization = {'JSON': {}}
        )
        # extract data from response            
        items = []
        for event in resp['Payload']:
            if 'Records' in event:
                records = event['Records']['Payload'].decode('utf-8')
                records = records.split("\n")
    
                for record in records:
                    try:
                        item = json.loads(record)
                        items.append(item)
                    except Exception as error:
                        pass

        if len(items):
            #if protein sequence query, sort by prot_id, else dna_id
            sort_by = "prot_id" if items[0].get("prot_id", dna_id) else "dna_id"
            sorted_items = sorted(items, key=itemgetter(sort_by))
            tmp = paginate(sorted_items, n=100)
            paginated = [{"page": str(i+1), "data": tmp[i]} for i in range(0, len(tmp))]

            new_metadata={
                "num_items": len(items),
                "num_pages": len(paginated),
                "seq_type": "DNA" if seq_type == "dna" else "Protein",
                "unique": metadata["unique"]
            }

            stream_data_to_s3(
                key=pag_key,
                items=paginated+[{"metadata": metadata}],
                bucket=bucket
            )
            stream_data_to_s3(
                key=key + "/query/filters/" + filters_suffix,
                items=items+[{"metadata": metadata}],
                bucket=bucket
            )
            data = paginated[0]["data"] #return first page
            num_pages = len(paginated)
        else:
            data = []
            num_pages = 0
        return {
            "statusCode": 200,
            "body": json.dumps({
                "data": data,
                "key": key,
                "page": page,
                "unique": metadata["unique"],
                "num_pages": num_pages,
                "num_items": len(items),
                "filters": filters,
                "seq_type": seq_type
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
