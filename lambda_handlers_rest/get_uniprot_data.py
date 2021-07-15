import json
import boto3
import urllib3
import xml.etree.ElementTree as ET
import sys
import logging
import traceback
import os
from urllib.parse import unquote_plus
import uuid


logger = logging.getLogger()
logger.setLevel(logging.INFO)

prot_db_name = os.environ["PROT_DB"]
bucket = os.environ["UPLOAD_BUCKET"]

dynamodb = boto3.resource("dynamodb")
s3_client = boto3.client('s3')

prot_db = dynamodb.Table(prot_db_name)



def GetUniprotData(ID):
    #Collect data from Uniprot
    http = urllib3.PoolManager()
    url = "https://www.uniprot.org/uniprot/{}.xml".format(ID)
    r = http.request('GET', url)

    urllib3_status_report = {200: "The request was processed successfully.",
    400: "Bad request. There is a problem with your input.",
    404: "Not found. The resource you requested doesn't exist.",
    410: "Gone. The resource you requested was removed.",
    500: "Internal server error. Most likely a temporary problem, but if the problem persists please contact us.",
    503: "Service not available. The server is being updated, try again later."}


    #if GET request fails, raise exception
    if(r.status!= 200):
        report = urllib3_status_report[r.status]
        raise Exception(report)

    data = r.data

    root = ET.fromstring(data)

    #get function text
    el = root.findall(".//{http://uniprot.org/uniprot}entry/{http://uniprot.org/uniprot}comment/[@type='function']/{http://uniprot.org/uniprot}text")
    functiontext = el[0].text

    #get sequence
    el = root.findall(".//{http://uniprot.org/uniprot}entry/{http://uniprot.org/uniprot}sequence")
    sequencetext = el[0].text
    
    output= {"function": functiontext, "sequence": sequencetext}
    return output


def lambda_handler(event, context):
    logger.info(f'Event: {event}')
    try:
        for record in event['Records']:
            
            bucket = record['s3']['bucket']['name']
            key = unquote_plus(record['s3']['object']['key'])
            tmpkey = key.replace('/', '')
            download_path = '/tmp/{}{}'.format(uuid.uuid4(), tmpkey)
            new_key = tmpkey.split(".")[0]

            s3_client.download_file(bucket, key, download_path)
            logger.info(f'Downloaded file {key} from s3 bucket {bucket}')
        
        with open(download_path, 'r') as file:
            data = json.load(file)
        
        
        
        prot_data = data["protein_data"]
        rt_class = data["class"]

        items = []
        
        for item in prot_data:
            accession = item["accession"]
            prot_name = item["protein"]
            
            #get uniprot data
            uniprotData = GetUniprotData(accession)

            item = {
                "class": rt_class,
                "protein": prot_name,
                "accession": accession,
                "function": uniprotData["function"],
                "sequence": uniprotData["sequence"]
            }
            
            items.append(item)
        
        logger.info(f"Writing items to database: {prot_db_name}")

        with prot_db.batch_writer() as batch:
            for item in items:
                batch.put_item(Item=item)

        return {
            'statusCode': 200
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
